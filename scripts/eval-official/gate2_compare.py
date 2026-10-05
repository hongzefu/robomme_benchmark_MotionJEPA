"""第二档对比：原侧（官方原版入口）对新侧（本仓库改后入口）的逐身份差异表（计划第二部分 1.7）。

输入：两侧的结果行（jsonl，可多份分片文件）与轨迹根目录（递归找 ``trace.jsonl``，格式见 ``trace_writer.py``）。

配对：按 ``(task, source_episode, seed)``。每侧每个身份取「最终结果行」：``canary``、``infra``、``late`` 为真的行不算；
同一侧同一身份有多于一条最终行记 ``duplicate``。轨迹先用结果行的 ``trace_path``（若有）；否则在轨迹根下按轨迹
header 的 ``identity`` 三元组找，同一身份多份时按 ``identity.attempt`` 对上结果行的 ``attempt``，仍不唯一时取
所在目录名以 ``.a<attempt>`` 结尾的那份。

逐身份输出：两侧终态（结果行 ``status``）、是否同终态、两侧执行步数、是否逐项相同、首个分叉步与分叉类型。
分叉类型按时间线依次比较：演示（画面／状态／文本）→ 每步之前的请求与历史边界（``request``）→ 模型返回的
动作块（``action``）→ 第 k 步行：子目标文本（``text``）、执行动作（``action``）、执行后画面（``obs``）、
状态（``state``）、``terminated``／``truncated``／``status``（``stop``）；公共步都相同而步数不同记 ``stop``。
``identical_trace`` 的覆盖范围只限这些字段。

判定行（``GATE2`` 恒为 INFO 或 INCOMPLETE，不阻塞任何流程）::

    GATE2=INFO policy=<p> compared=<n> same_terminal=<n> identical_trace=<n> first_diverge_obs=<n>
          first_diverge_state=<n> first_diverge_text=<n> first_diverge_action=<n> missing=0
          [first_diverge_stop=<n> first_diverge_request=<n> duplicate=0 missing_trace=0 bad_trace=0]
          [first_episode_identical=<n>/<服务启动次数> first_episode_aligned=<n>] [site=local]

两侧身份不齐（``missing``）、重复（``duplicate``）、完整模式下缺轨迹或轨迹结构不合规、``--expect-total`` 与
配上的身份数不符时，判定为 ``GATE2=INCOMPLETE``。

``--mode astra``：规划来自在线模型，两侧不会逐步相同；只比终态与子任务序列（结果行 ``subtasks`` 字段优先，
否则取轨迹逐步 ``subgoal`` 去重后的序列），另报两侧请求次数（按请求名）。判定行
``GATE2=INFO policy=… mode=astra compared=… same_terminal=… same_subtasks=… missing=0 …``。

``--groundsg``：GroundSG 服务端随机数跨局累积，只有每次服务启动后的第一局能逐步对拍。服务启动边界取结果行
字段 **``server_epoch``**（整数，同一结果文件、同一席位内每次（重新）起服务加 1；由席位脚本或驱动写入）；
同一 ``(结果文件, seat, server_epoch)`` 内按文件行序的第一行即该次启动的第一局。缺该字段时每个结果文件
（分片）视为一次启动，取文件第一行。分母为新侧的启动次数；分子为「该局在原侧也是某次启动的第一局，且两侧
轨迹逐项相同」的个数；``first_episode_aligned`` 为两侧都是启动第一局的个数。

用法::

    python scripts/eval-official/gate2_compare.py --policy mmesg-oracle \
        --orig-results <原侧结果 jsonl>... --new-results <新侧结果 jsonl>... \
        --orig-traces <原侧轨迹根> --new-traces <新侧轨迹根> [--groundsg] [--mode astra] \
        [--expect-total 192] [--site local] [--out-json gate2.json] [--out-md gate2.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import trace_writer as tw  # 同目录模块（脚本目录在 sys.path 头部；测试经 load_script 加载时同样）

DIVERGE_KINDS = ("obs", "state", "text", "action", "stop", "request")
EPOCH_FIELD = "server_epoch"


# ── 结果行 ───────────────────────────────────────────────────────────────────


def ident_of(row: dict) -> tuple:
    ident = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    task = row.get("task", ident.get("task"))
    se = row.get("source_episode", ident.get("source_episode"))
    seed = row.get("seed", ident.get("seed"))
    return (task, None if se is None else int(se), None if seed is None else int(seed))


def is_final(row: dict) -> bool:
    return not (row.get("canary") or row.get("infra") or row.get("late"))


def read_rows(paths: list[str | Path]) -> list[dict]:
    """读多份结果 jsonl；每行附加 ``_file``（来源文件）与 ``_line``（文件内行序）。"""
    rows: list[dict] = []
    for p in paths:
        with Path(p).open(encoding="utf-8") as fh:
            for i, line in enumerate(x for x in fh if x.strip()):
                r = json.loads(line)
                r["_file"] = str(p)
                r["_line"] = i
                rows.append(r)
    return rows


def final_rows(rows: list[dict]) -> tuple[dict[tuple, dict], Counter]:
    """每身份唯一最终行；返回 (身份→行, 身份→最终行数)。"""
    finals: dict[tuple, dict] = {}
    count: Counter = Counter()
    for r in rows:
        if not is_final(r):
            continue
        k = ident_of(r)
        count[k] += 1
        finals.setdefault(k, r)
    return finals, count


def epoch_firsts(rows: list[dict]) -> tuple[set[tuple], int]:
    """每次服务启动的第一局身份集合与启动次数（见模块说明的 ``server_epoch`` 约定）。"""
    seen: dict[tuple, tuple] = {}
    for r in sorted(rows, key=lambda x: (x["_file"], x["_line"])):
        if r.get("canary"):
            continue
        ep = (r["_file"], r.get("seat"), r.get(EPOCH_FIELD, 0))
        seen.setdefault(ep, ident_of(r))
    return set(seen.values()), len(seen)


# ── 轨迹索引 ─────────────────────────────────────────────────────────────────


class TraceIndex:
    def __init__(self, root: str | Path | None):
        self.by_ident: dict[tuple, list[tuple[Path, dict]]] = defaultdict(list)
        if root is None or not Path(root).exists():
            return
        for p in tw.find_traces(root):
            try:
                with p.open(encoding="utf-8") as fh:
                    head = json.loads(fh.readline())
            except Exception:  # noqa: BLE001 坏文件不进索引，按缺轨迹计
                continue
            ident = head.get("identity") or {}
            self.by_ident[ident_of(ident)].append((p, ident))

    def lookup(self, row: dict) -> Path | None:
        if row.get("trace_path"):
            p = Path(row["trace_path"])
            if p.exists():
                return p
            # 结果行记的是节点本地路径（如 /tmp/<run>/…），轨迹发布到 NFS／本机 media 后本地副本已删：退回按身份索引查
        cands = self.by_ident.get(ident_of(row), [])
        if len(cands) <= 1:
            return cands[0][0] if cands else None
        att = row.get("attempt")
        hit = [p for p, ident in cands if ident.get("attempt") is not None and ident.get("attempt") == att]
        if len(hit) == 1:
            return hit[0]
        hit = [p for p, _ in cands if p.parent.name.endswith(f".a{att}")]
        return hit[0] if len(hit) == 1 else None


# ── 轨迹逐项比较 ─────────────────────────────────────────────────────────────


def _sha(rec: Any) -> Any:
    """array_record → (dtype, shape, sha256)；其他原样。"""
    if isinstance(rec, dict) and "sha256" in rec:
        return (rec.get("dtype"), tuple(rec.get("shape") or ()), rec["sha256"])
    return rec


def _pre_step(rows: list[dict]) -> tuple[dict[int, list], dict[int, list]]:
    """按 step 分组的请求（含历史边界）与动作块。"""
    req: dict[int, list] = defaultdict(list)
    resp: dict[int, list] = defaultdict(list)
    for r in rows:
        k = r.get("kind")
        if k == "request":
            req[int(r["step"])].append(("request", r.get("name"), r.get("sha256"), r.get("nbytes")))
        elif k == "history":
            req[int(r.get("end", r.get("start", 0)))].append(("history", r.get("start"), r.get("end")))
        elif k == "response":
            resp[int(r["step"])].append(_sha(r.get("actions")))
    return req, resp


def compare_traces(a: list[dict], b: list[dict]) -> dict:
    """返回 ``{"identical": bool, "diverge_step": int|None, "diverge_kind": str|None, "field": str|None}``。

    ``diverge_step`` 为 0 表示演示阶段或第一步之前的请求就分叉。"""
    def out(step, kind, field):
        return {"identical": False, "diverge_step": step, "diverge_kind": kind, "field": field}

    da = next((r for r in a if r.get("kind") == "demo"), {}) or {}
    db = next((r for r in b if r.get("kind") == "demo"), {}) or {}
    if da.get("frames") != db.get("frames") or da.get("front_sha256") != db.get("front_sha256") \
            or da.get("wrist_sha256") != db.get("wrist_sha256"):
        return out(0, "obs", "demo.frames")
    if [_sha(x) for x in da.get("states") or []] != [_sha(x) for x in db.get("states") or []]:
        return out(0, "state", "demo.states")
    if (da.get("texts") or []) != (db.get("texts") or []):
        return out(0, "text", "demo.texts")

    req_a, resp_a = _pre_step(a)
    req_b, resp_b = _pre_step(b)
    steps_a = [r for r in a if r.get("kind") == "step"]
    steps_b = [r for r in b if r.get("kind") == "step"]
    n = max(len(steps_a), len(steps_b))
    for i in range(n + 1):
        # 第 i 步执行后、第 i+1 步执行前发出的请求与收到的动作块（i=0 即首个请求）
        if req_a.get(i, []) != req_b.get(i, []):
            return out(i, "request", "request")
        if resp_a.get(i, []) != resp_b.get(i, []):
            return out(i, "action", "response")
        if i == n:
            break
        if i >= len(steps_a) or i >= len(steps_b):
            return out(i + 1, "stop", "exec_steps")
        sa, sb = steps_a[i], steps_b[i]
        step = i + 1
        if sa.get("subgoal") != sb.get("subgoal"):
            return out(step, "text", "subgoal")
        if _sha(sa.get("action")) != _sha(sb.get("action")):
            return out(step, "action", "action")
        if sa.get("front_sha256") != sb.get("front_sha256") or sa.get("wrist_sha256") != sb.get("wrist_sha256"):
            return out(step, "obs", "front_sha256" if sa.get("front_sha256") != sb.get("front_sha256") else "wrist_sha256")
        if _sha(sa.get("state")) != _sha(sb.get("state")):
            return out(step, "state", "state")
        for f in ("terminated", "truncated", "status"):
            if sa.get(f) != sb.get(f):
                return out(step, "stop", f)
    ea = next((r for r in reversed(a) if r.get("kind") == "end"), {}) or {}
    eb = next((r for r in reversed(b) if r.get("kind") == "end"), {}) or {}
    if ea.get("status") != eb.get("status") or ea.get("exec_steps") != eb.get("exec_steps"):
        return out(n, "stop", "end")
    return {"identical": True, "diverge_step": None, "diverge_kind": None, "field": None}


# ── 主流程 ───────────────────────────────────────────────────────────────────


def _subtasks(row: dict, trace: list[dict] | None) -> list | None:
    if isinstance(row.get("subtasks"), list):
        return list(row["subtasks"])
    return tw.subgoal_sequence(trace) if trace is not None else None


def _request_counts(trace: list[dict] | None) -> dict:
    if trace is None:
        return {}
    return dict(Counter(r.get("name") for r in trace if r.get("kind") == "request"))


def compare(orig_rows: list[dict], new_rows: list[dict], orig_traces: str | Path | None, new_traces: str | Path | None,
            *, mode: str = "full", groundsg: bool = False, expect_total: int | None = None) -> dict:
    of, oc = final_rows(orig_rows)
    nf, nc = final_rows(new_rows)
    dup = sorted({k for k, v in oc.items() if v > 1} | {k for k, v in nc.items() if v > 1}, key=str)
    only_o = sorted(set(of) - set(nf), key=str)
    only_n = sorted(set(nf) - set(of), key=str)
    both = sorted(set(of) & set(nf), key=str)
    oi, ni = TraceIndex(orig_traces), TraceIndex(new_traces)

    table: list[dict] = []
    kinds: Counter = Counter()
    missing_trace = bad_trace = identical = same_term = same_sub = 0
    traces: dict[tuple, tuple] = {}
    for k in both:
        ro, rn = of[k], nf[k]
        po, pn = oi.lookup(ro), ni.lookup(rn)
        to = tw.read_trace(po) if po else None
        tn = tw.read_trace(pn) if pn else None
        row = {"task": k[0], "source_episode": k[1], "seed": k[2],
               "orig_status": ro.get("status"), "new_status": rn.get("status"),
               "orig_exec_steps": ro.get("exec_steps"), "new_exec_steps": rn.get("exec_steps"),
               "orig_trace": str(po) if po else None, "new_trace": str(pn) if pn else None}
        row["same_terminal"] = ro.get("status") == rn.get("status")
        same_term += row["same_terminal"]
        if mode == "astra":
            so, sn = _subtasks(ro, to), _subtasks(rn, tn)
            row.update(orig_subtasks=so, new_subtasks=sn, same_subtasks=(so is not None and so == sn),
                       orig_requests=_request_counts(to), new_requests=_request_counts(tn))
            same_sub += row["same_subtasks"]
        else:
            if to is None or tn is None:
                missing_trace += 1
                row.update(identical_trace=False, diverge_step=None, diverge_kind="missing_trace")
            else:
                probs = tw.validate_trace(to) + tw.validate_trace(tn)
                if probs:
                    bad_trace += 1
                    row["trace_problems"] = probs
                c = compare_traces(to, tn)
                row.update(identical_trace=c["identical"] and not probs, diverge_step=c["diverge_step"],
                           diverge_kind=c["diverge_kind"], diverge_field=c["field"])
                identical += row["identical_trace"]
                if c["diverge_kind"]:
                    kinds[c["diverge_kind"]] += 1
                traces[k] = (to, tn)
        table.append(row)

    missing = len(only_o) + len(only_n)
    summary: dict[str, Any] = {"mode": mode, "compared": len(both), "same_terminal": same_term, "missing": missing,
                               "missing_orig": [list(x) for x in only_n], "missing_new": [list(x) for x in only_o],
                               "duplicate": len(dup), "duplicates": [list(x) for x in dup]}
    if mode == "astra":
        summary["same_subtasks"] = same_sub
    else:
        summary.update(identical_trace=identical, missing_trace=missing_trace, bad_trace=bad_trace,
                       **{f"first_diverge_{x}": kinds.get(x, 0) for x in DIVERGE_KINDS})
    if groundsg:
        firsts_n, epochs_n = epoch_firsts(new_rows)
        firsts_o, _ = epoch_firsts(orig_rows)
        aligned = firsts_n & firsts_o
        ident_ok = {(r["task"], r["source_episode"], r["seed"]): bool(r.get("identical_trace")) for r in table}
        ok = sum(1 for k in aligned if ident_ok.get(k))
        summary.update(first_episode_identical=ok, server_epochs=epochs_n, first_episode_aligned=len(aligned))
        for r in table:
            k = (r["task"], r["source_episode"], r["seed"])
            r["epoch_first_new"] = k in firsts_n
            r["epoch_first_orig"] = k in firsts_o
    incomplete = missing > 0 or len(dup) > 0 or (expect_total is not None and len(both) != expect_total)
    if mode != "astra":
        incomplete = incomplete or missing_trace > 0 or bad_trace > 0
    summary["verdict"] = "INCOMPLETE" if incomplete else "INFO"
    summary["expect_total"] = expect_total
    return {"summary": summary, "table": table}


def verdict_line(res: dict, policy: str, site: str | None = None) -> str:
    s = res["summary"]
    parts = [f"GATE2={s['verdict']}", f"policy={policy}"]
    if s["mode"] == "astra":
        parts += ["mode=astra", f"compared={s['compared']}", f"same_terminal={s['same_terminal']}",
                  f"same_subtasks={s['same_subtasks']}", f"missing={s['missing']}", f"duplicate={s['duplicate']}"]
    else:
        parts += [f"compared={s['compared']}", f"same_terminal={s['same_terminal']}",
                  f"identical_trace={s['identical_trace']}"]
        parts += [f"first_diverge_{x}={s[f'first_diverge_{x}']}" for x in ("obs", "state", "text", "action")]
        parts += [f"missing={s['missing']}", f"first_diverge_stop={s['first_diverge_stop']}",
                  f"first_diverge_request={s['first_diverge_request']}", f"duplicate={s['duplicate']}",
                  f"missing_trace={s['missing_trace']}", f"bad_trace={s['bad_trace']}"]
    if "first_episode_identical" in s:
        parts += [f"first_episode_identical={s['first_episode_identical']}/{s['server_epochs']}",
                  f"first_episode_aligned={s['first_episode_aligned']}"]
    if s.get("expect_total") is not None:
        parts.append(f"expect_total={s['expect_total']}")
    if site:
        parts.append(f"site={site}")
    return " ".join(parts)


def to_markdown(res: dict, policy: str) -> str:
    s = res["summary"]
    lines = [f"# 第二档差异表：{policy}", "", f"- 判定：`{s['verdict']}`；配对 {s['compared']} 个身份，同终态 {s['same_terminal']}。"]
    if s["mode"] == "astra":
        lines += ["", "| 任务 | 原 episode | seed | 原侧终态 | 新侧终态 | 同终态 | 子任务序列相同 |", "|---|---|---|---|---|---|---|"]
        for r in res["table"]:
            lines.append(f"| {r['task']} | {r['source_episode']} | {r['seed']} | {r['orig_status']} | {r['new_status']} | "
                         f"{int(r['same_terminal'])} | {int(r['same_subtasks'])} |")
    else:
        lines.append("- `identical_trace` 只覆盖轨迹字段：演示画面哈希／状态／文本、逐请求规范化字节哈希、历史边界、"
                     "动作块、逐步画面哈希／状态／动作／子目标／终止标志与终态；不覆盖视频字节。")
        lines += ["", "| 任务 | 原 episode | seed | 原侧终态 | 新侧终态 | 同终态 | 逐项相同 | 首个分叉步 | 分叉类型 |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in res["table"]:
            lines.append(f"| {r['task']} | {r['source_episode']} | {r['seed']} | {r['orig_status']} | {r['new_status']} | "
                         f"{int(r['same_terminal'])} | {int(bool(r.get('identical_trace')))} | {r.get('diverge_step')} | "
                         f"{r.get('diverge_kind')} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="第二档：原侧对新侧逐身份差异表")
    ap.add_argument("--policy", required=True, help="报告用的模型标签，如 mmesg-oracle、pp、astra")
    ap.add_argument("--orig-results", nargs="+", required=True)
    ap.add_argument("--new-results", nargs="+", required=True)
    ap.add_argument("--orig-traces", default=None)
    ap.add_argument("--new-traces", default=None)
    ap.add_argument("--mode", choices=["full", "astra"], default="full")
    ap.add_argument("--groundsg", action="store_true", help="另出 first_episode_identical（服务启动边界见 server_epoch）")
    ap.add_argument("--expect-total", type=int, default=None)
    ap.add_argument("--site", default=None, help="如 local：判定行附 site=local")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    res = compare(read_rows(args.orig_results), read_rows(args.new_results), args.orig_traces, args.new_traces,
                  mode=args.mode, groundsg=args.groundsg, expect_total=args.expect_total)
    res["summary"].update(policy=args.policy, site=args.site)
    line = verdict_line(res, args.policy, args.site)
    res["summary"]["line"] = line
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(to_markdown(res, args.policy), encoding="utf-8")
    print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
