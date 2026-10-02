"""V8 双模型评估汇总（1001-v8-post-evaluation-gl-plan.md 第一部分 §1 第 5、7 条、§4；契约 C4 第一段）。纯 CPU、只用标准库。

    python scripts/eval-official/v8_report.py --manifest <manifest.json> --stage <运行根> \
        --policies smvla,mme --out <dir> [--videos <本机视频根>] [--partial] [--expect-total 1070] [--cap 1600]

输入（契约 C1～C3）：
- ``--manifest``：``v8_manifest.py`` 产出的 ``manifest.json``（``rows`` 为执行身份行，``key = f"{task}_{tier}_{seed}"``）；
  分片归属取行内 ``shard`` 字段，没有就读同目录 ``shard-NN.json``。
- ``--stage``：运行根，逐席 ``sNN/<policy>/results.jsonl`` 与账本 ``sNN/<policy>/<policy>.ledger.jsonl``
  （也兼容 ``sNN/<policy>.ledger.jsonl``）；录像目录 ``sNN/<policy>/rec/<key>.a<n>/``。
- ``--videos``（可选）：``eval_video_mover.py --mode v8`` 的本机目的根 ``<videos>/<policy>/<tier>/<task>/<key>.a<n>/``，
  已搬走的录像在这里找。

口径：
- 每身份唯一权威终态 = 账本 ``accept`` 行的 ``accepted_attempt_id`` 对应的结果行；不是「最后一条」。
- 合法权威结局：success／fail／timeout，或「非 infra 错误终局」（status=error、infra=false、非 budget_exhausted、
  非 run_blocked；记 error 列、占分母、不算成功，判定行追加 error_final=）。
- 迟到终态（同一身份 accept 之后再来的终态）与废弃尝试（未被接受的 error／infra 尝试；账本有 attempt_end 而
  results.jsonl 无对应行的悬空尝试也算）单列，不入分数。金丝雀行（canary）不进终态分母。
- 同一身份两条不同 ``accepted_attempt_id``、accept 指向 infra 错误或其他非终态行、或同一 attempt_id 的结果行自相矛盾
  → conflicting_terminal。
- 分母固定为 manifest 身份数（默认核对 1070）／模型；没有 accept 的身份一律记 missing（不进成功、照样占分母）。
- ``exec_steps`` 大于 ``--cap``（1600）的结果行计入 exec_over_cap，>0 即 FAIL。

产出 ``<out>/report.json``、``<out>/report.md``（中文）、``<out>/video-index.jsonl``；末两行判定：
``V8_EVAL_COVERAGE=PASS|FAIL policies= missing= extra= duplicate= conflicting_terminal= late_ignored= error_final=``（error_final 为契约字段后的追加字段：非 infra 错误终局数）
``V8_EVAL_REPORT=PASS|FAIL count_mismatch= media_unexplained= exec_over_cap=``
``--partial``：中途进度，不因缺失／媒体未就位判 FAIL（冲突、越限照判），另报已完成数、各格已完成与按已完成局墙钟估算的各席剩余时间。
退出码：两行都 PASS 为 0，否则 1。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TERMINAL = ("success", "fail", "timeout")
DEFAULT_CAP = 1600
DEFAULT_TOTAL = 1070
MEDIA_FILES = ("front.mkv", "wrist.mkv")


# ---------------------------------------------------------------- 读入

def read_jsonl(path: Path) -> list[dict]:
    """逐行读 JSONL；评估进程正在追加的半行（解析失败）跳过。"""
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def key_of(row: dict) -> str:
    if row.get("key"):
        return str(row["key"])
    return f"{row.get('task')}_{row.get('tier')}_{row.get('seed')}"


def seat_dirs(stage: Path) -> list[Path]:
    return sorted(p for p in stage.glob("s*") if p.is_dir() and p.name[1:].isdigit())


def ledger_files(seat_dir: Path, policy: str) -> list[Path]:
    cands = [seat_dir / policy / f"{policy}.ledger.jsonl", seat_dir / f"{policy}.ledger.jsonl"]
    cands += sorted((seat_dir / policy).glob("*.ledger.jsonl"))
    seen, out = set(), []
    for p in cands:
        if p.exists() and p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p)
    return out


def load_policy(stage: Path, policy: str) -> dict:
    """读一个模型全部席位的结果行与账本行。每行补 ``_seat``（目录名）与 ``_seat_dir``。"""
    results: list[dict] = []
    ledger: list[dict] = []
    for sd in seat_dirs(stage):
        for row in read_jsonl(sd / policy / "results.jsonl"):
            if row.get("policy") not in (None, policy):
                continue
            row["_seat"], row["_seat_dir"] = sd.name, str(sd)
            results.append(row)
        for lp in ledger_files(sd, policy):
            for row in read_jsonl(lp):
                if row.get("policy") not in (None, policy):
                    continue
                row["_seat"] = sd.name
                ledger.append(row)
    return {"results": results, "ledger": ledger}


def rec_name(row: dict) -> str | None:
    if row.get("rec_dir"):
        return Path(str(row["rec_dir"])).name
    if row.get("attempt_no") is not None and (row.get("key") or row.get("task")):
        return f"{key_of(row)}.a{int(row['attempt_no'])}"
    return None


def is_error_final(row: dict) -> bool:
    """非 infra 错误是该身份的最终结局（E-A 会写 accept）：status=error、infra=false、非额度耗尽、非运行阻塞。"""
    return (row.get("status") == "error" and not row.get("infra") and not row.get("budget_exhausted")
            and not row.get("run_blocked"))


def error_reason(row: dict) -> str | None:
    why = row.get("error") or row.get("infra_reason")
    return str(why) if why else None


def error_final_video_class(row: dict, has_media: bool) -> str | None:
    """非 infra 错误终局的录像判定（报告与搬运脚本共用）：
    None = 不是错误终局或有录像（照常核对）；"explained" = 无录像但写明原因（不计缺失）；"unexplained" = 无录像无原因。"""
    if not is_error_final(row) or has_media:
        return None
    return "explained" if error_reason(row) else "unexplained"


def analyze_attempts(state: dict) -> dict:
    """按账本 accept 决定每身份唯一权威终态（与 manifest 无关的部分；搬运脚本也复用）。

    返回：
      by_attempt: attempt_id -> [结果行]（v8 行）
      accepted:   key -> 结果行（accept 指向且唯一、终态、无自相矛盾）
      conflicts:  [{key, reason, ...}]
      accept_no_row: [{key, attempt_id}]   accept 指向的结果行尚未出现
      duplicate:  重复计数（同 attempt_id 多条结果行、同一 accept 重复写）
      late:       [结果行]  accept 之外的终态行（迟到）
      abandoned:  [结果行]  非终态（error 等）且未被接受的尝试
    """
    # 金丝雀尝试（rec 目录 <key>.canary.a<n>）不进终态分母、不算迟到／废弃；录像仍由搬运脚本照搬
    rows = [r for r in state["results"] if r.get("v8") and not r.get("canary")]
    by_attempt: dict[str, list[dict]] = defaultdict(list)
    no_id: list[dict] = []
    for r in rows:
        if r.get("attempt_id"):
            by_attempt[str(r["attempt_id"])].append(r)
        else:
            no_id.append(r)
    duplicate = 0
    conflicts: list[dict] = []
    for aid, lst in by_attempt.items():
        if len(lst) > 1:
            duplicate += len(lst) - 1
    accepts: dict[str, list[str]] = defaultdict(list)
    for lr in state["ledger"]:
        if lr.get("kind") == "accept":
            aid = lr.get("accepted_attempt_id") or lr.get("attempt_id")
            accepts[str(lr.get("key"))].append(str(aid))
    late_ids = {str(lr.get("attempt_id")) for lr in state["ledger"]
                if lr.get("kind") == "attempt_end" and lr.get("late")}
    accepted: dict[str, dict] = {}
    accept_no_row: list[dict] = []
    for key, ids in accepts.items():
        uniq = sorted(set(ids))
        duplicate += len(ids) - len(uniq)
        if len(uniq) > 1:
            conflicts.append({"key": key, "reason": "multiple_accept", "attempt_ids": uniq})
            continue
        aid = uniq[0]
        lst = by_attempt.get(aid, [])
        if not lst:
            accept_no_row.append({"key": key, "attempt_id": aid})
            continue
        statuses = {r.get("status") for r in lst}
        if len(statuses) > 1:
            conflicts.append({"key": key, "reason": "attempt_rows_disagree", "attempt_id": aid,
                              "statuses": sorted(map(str, statuses))})
            continue
        row = lst[-1]
        if row.get("status") not in TERMINAL and not is_error_final(row):
            reason = "accept_infra_error" if row.get("status") == "error" and row.get("infra") else "accept_not_terminal"
            conflicts.append({"key": key, "reason": reason, "attempt_id": aid, "status": row.get("status")})
            continue
        if key_of(row) != key:
            conflicts.append({"key": key, "reason": "accept_key_mismatch", "attempt_id": aid, "row_key": key_of(row)})
            continue
        accepted[key] = row
    accepted_ids = {str(r["attempt_id"]) for r in accepted.values()}
    conflict_keys = {c["key"] for c in conflicts}
    late: list[dict] = []
    abandoned: list[dict] = []
    for aid, lst in by_attempt.items():
        if aid in accepted_ids:
            continue
        r = lst[-1]
        if r.get("status") in TERMINAL:
            if key_of(r) in conflict_keys:
                continue
            late.append(r)  # 未被接受的终态：迟到（账本 late=true）或尚未写 accept
        else:
            abandoned.append(r)
    for r in no_id:
        (late if r.get("status") in TERMINAL else abandoned).append(r)
    # 悬空尝试恢复：账本有 attempt_end 而 results.jsonl 无对应行 → 计入废弃尝试，不报错
    ended: dict[str, dict] = {}
    for lr in state["ledger"]:
        if lr.get("kind") == "attempt_end" and lr.get("attempt_id"):
            ended[str(lr["attempt_id"])] = lr
    pending_accept_ids = {a["attempt_id"] for a in accept_no_row}  # accept 已写、结果行未出现：只计冲突，不算废弃
    for aid, lr in ended.items():
        if aid in by_attempt or aid in accepted_ids or aid in pending_accept_ids:
            continue
        abandoned.append({"key": lr.get("key"), "attempt_id": aid, "attempt_no": lr.get("attempt_no"),
                          "status": lr.get("status") or "error", "infra": lr.get("infra"),
                          "infra_reason": lr.get("infra_reason") or lr.get("reason") or "ledger_only_attempt_end",
                          "ledger_only": True, "_seat": lr.get("_seat")})
    return {"rows": rows, "by_attempt": by_attempt, "accepted": accepted, "conflicts": conflicts,
            "accept_no_row": accept_no_row, "duplicate": duplicate, "late": late, "late_ids": late_ids,
            "abandoned": abandoned}


# ---------------------------------------------------------------- 媒体

def find_media(row: dict, policy: str, videos: Path | None) -> dict:
    """在运行根（尚未搬走）与本机视频根（已搬走）里找录像目录。"""
    name = rec_name(row)
    if not name:
        return {"location": "absent", "path": None, "files": []}
    cands: list[tuple[str, Path]] = []
    if videos is not None:
        cands.append(("local", videos / policy / str(row.get("tier") or "_notier") / str(row.get("task")) / name))
    if row.get("_seat_dir"):
        cands.append(("stage", Path(row["_seat_dir"]) / policy / "rec" / name))
    for loc, p in cands:
        if p.is_dir():
            files = sorted(f.name for f in p.iterdir() if f.is_file())
            return {"location": loc, "path": str(p), "files": files}
    return {"location": "absent", "path": None, "files": []}


def media_ok(m: dict) -> bool:
    return all(f in m["files"] for f in MEDIA_FILES) and "summary.json" in m["files"]


# ---------------------------------------------------------------- 主体

def load_manifest(path: Path) -> tuple[dict, list[dict], dict[str, str]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = list(doc.get("rows") or [])
    for r in rows:
        r["key"] = key_of(r)
    shard_of: dict[str, str] = {}
    for r in rows:
        if r.get("shard") is not None:
            shard_of[r["key"]] = f"{int(r['shard']):02d}" if str(r["shard"]).isdigit() else str(r["shard"])
    if not shard_of:
        for sp in sorted(path.parent.glob("shard-*.json")):
            sid = sp.stem.split("-", 1)[1]
            try:
                items = json.loads(sp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for it in items:
                shard_of[key_of(it)] = sid
    return doc, rows, shard_of


def load_shard_files(pattern: str | None) -> dict[str, str]:
    """shard-NN.json → {key: "NN"}；pattern 为空返回空表。"""
    out: dict[str, str] = {}
    if not pattern:
        return out
    import glob as _glob

    for sp in sorted(_glob.glob(pattern)):
        p = Path(sp)
        sid = p.stem.split("-", 1)[1] if "-" in p.stem else p.stem
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for it in items:
            out[key_of(it)] = sid
    return out


def cell_of(r: dict) -> str:
    return f"{r['task']}@{r['tier']}"


def _fmt_s(sec: float | None) -> str:
    if sec is None:
        return "未观测"
    h, rem = divmod(int(round(sec)), 3600)
    return f"{h}h{rem // 60:02d}m"


def wall_of(row: dict) -> float | None:
    t = row.get("timing") or {}
    v = t.get("episode_wall_s") if isinstance(t, dict) else None
    if v is None:
        v = row.get("wall_s")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def build_report(manifest_path: Path, stage: Path, policies: list[str], videos: Path | None, *,
                 partial: bool, expect_total: int, cap: int, shard_files: str | None = None) -> dict:
    doc, mrows, shard_of = load_manifest(manifest_path)
    mkeys = {r["key"]: r for r in mrows}
    count_mismatch: list[str] = []
    if len(mrows) != expect_total:
        count_mismatch.append(f"manifest rows={len(mrows)} != expect_total={expect_total}")
    if doc.get("total") is not None and int(doc["total"]) != len(mrows):
        count_mismatch.append(f"manifest total={doc['total']} != rows={len(mrows)}")
    if len(mkeys) != len(mrows):
        count_mismatch.append(f"manifest key 重复 {len(mrows) - len(mkeys)}")
    cell_den = Counter(cell_of(r) for r in mkeys.values())
    if doc.get("cells") and dict(doc["cells"]) != dict(cell_den):
        count_mismatch.append("manifest cells 与 rows 逐格计数不一致")
    task_den = Counter(r["task"] for r in mkeys.values())

    cov = Counter()
    exec_over_cap: list[dict] = []
    media_unexplained: list[dict] = []
    index: list[dict] = []
    per_policy: dict[str, Any] = {}
    observed_seat: dict[str, str] = {}

    for pol in policies:
        st = load_policy(stage, pol)
        # 实际所在席位以运行根里观测到的目录为准（分片可能重分到别的 sNN），不依赖 manifest 的 shard 字段
        for r in st["results"] + st["ledger"]:
            if r.get("key") and r.get("_seat"):
                observed_seat[str(r["key"])] = r["_seat"][1:]
        an = analyze_attempts(st)
        acc = an["accepted"]
        conflict_n = len(an["conflicts"]) + (0 if partial else len(an["accept_no_row"]))
        seen_keys = {key_of(r) for r in an["rows"]} | {str(l.get("key")) for l in st["ledger"] if l.get("key")}
        extra = sorted(k for k in seen_keys if k not in mkeys)
        conflict_keys = {c["key"] for c in an["conflicts"]}
        if not partial:  # accept 已写、结果行未出现：正式汇总只计 conflicting_terminal，不重复计 missing
            conflict_keys |= {a["key"] for a in an["accept_no_row"]}
        outcome: dict[str, str] = {}
        for k in mkeys:
            if k in acc:
                outcome[k] = acc[k]["status"]  # success／fail／timeout，或非 infra 错误终局 error
            elif k in conflict_keys:
                outcome[k] = "conflict"
            else:
                outcome[k] = "missing"  # 无 accept：只有 infra 错误尝试或一次都没跑，错误尝试另列废弃
        missing = [k for k in mkeys if k not in acc and k not in conflict_keys]  # 冲突身份只计 conflicting_terminal
        cov["missing"] += 0 if partial else len(missing)
        cov["error_final"] += sum(1 for k in mkeys if k in acc and acc[k].get("status") == "error")
        cov["extra"] += len(extra)
        cov["duplicate"] += an["duplicate"]
        cov["conflicting_terminal"] += conflict_n
        cov["late_ignored"] += len(an["late"])

        # 一致性：成功字段、身份字段
        for k, r in acc.items():
            if k not in mkeys:
                continue
            if bool(r.get("task_success")) != (r.get("status") == "success"):
                count_mismatch.append(f"{pol} {k} task_success={r.get('task_success')} status={r.get('status')}")
            m = mkeys[k]
            ident = dict(r.get("identity") or {})
            for f in ("tier", "seed", "candidate", "spec_sha256"):
                mv = m.get(f)
                rv = r.get(f, ident.get(f))
                if mv is not None and rv is not None and str(mv) != str(rv):
                    count_mismatch.append(f"{pol} {k} {f} manifest={mv} result={rv}")
        oc = Counter(outcome.values())
        if sum(oc.values()) != len(mkeys):
            count_mismatch.append(f"{pol} 结局计数和 {sum(oc.values())} != 分母 {len(mkeys)}")

        # 必备字段：缺 exec_steps 或身份字段（tier／seed／spec_sha256）的 V8 结果行不静默放过
        for r in an["rows"]:
            ident = dict(r.get("identity") or {})
            lacks = [f for f in ("tier", "seed", "spec_sha256") if r.get(f, ident.get(f)) is None]
            if "exec_steps" not in r or (r.get("status") in TERMINAL and r.get("exec_steps") is None):
                lacks.append("exec_steps")
            if lacks:
                count_mismatch.append(f"{pol} {key_of(r)} "
                                      f"attempt_id={r.get('attempt_id')} 缺字段 {','.join(lacks)}")

        # 越限
        for r in an["rows"]:
            es = r.get("exec_steps")
            if es is not None and int(es) > cap:
                exec_over_cap.append({"policy": pol, "key": key_of(r), "attempt_id": r.get("attempt_id"),
                                      "exec_steps": int(es)})

        # 媒体与视频索引（每次尝试一行）
        accepted_ids = {str(r.get("attempt_id")) for r in acc.values()}
        late_ids = {str(r.get("attempt_id")) for r in an["late"]}
        no_video_errors: list[dict] = []
        for aid, lst in sorted(an["by_attempt"].items(), key=lambda kv: (key_of(kv[1][-1]), kv[0])):
            r = lst[-1]
            m = find_media(r, pol, videos)
            is_acc = aid in accepted_ids
            reason = None
            efc = error_final_video_class(r, media_ok(m)) if is_acc else None
            if efc is not None:
                # 非 infra 错误终局无录像：写明原因即可（与搬运脚本 error_final_no_video 同一判定）
                why = error_reason(r)
                no_video_errors.append({"key": key_of(r), "attempt_id": aid, "status": "error",
                                        "reason": str(why)[:200] if why else None, "location": m["location"]})
                if efc == "unexplained" and not partial:
                    reason = "error_final_without_video_and_reason"
                    media_unexplained.append({"policy": pol, "key": key_of(r), "attempt_id": aid, "reason": reason,
                                              "path": m["path"]})
            elif is_acc:
                if not media_ok(m):
                    reason = "accepted_terminal_media_absent" if m["location"] == "absent" else "accepted_terminal_media_incomplete"
                    if not partial:
                        media_unexplained.append({"policy": pol, "key": key_of(r), "attempt_id": aid, "reason": reason,
                                                  "path": m["path"]})
                elif r.get("recorder_verify") not in (None, "PASS"):
                    reason = f"recorder_verify={r.get('recorder_verify')}"
                    media_unexplained.append({"policy": pol, "key": key_of(r), "attempt_id": aid, "reason": reason,
                                              "path": m["path"]})
            elif r.get("status") not in TERMINAL and not media_ok(m):
                why = r.get("infra_reason") or r.get("error")
                no_video_errors.append({"key": key_of(r), "attempt_id": aid, "status": r.get("status"),
                                        "reason": str(why)[:200] if why else None, "location": m["location"]})
                if not why and not partial:
                    media_unexplained.append({"policy": pol, "key": key_of(r), "attempt_id": aid,
                                              "reason": "error_without_video_and_reason", "path": m["path"]})
            index.append({"policy": pol, "key": key_of(r), "task": r.get("task"), "tier": r.get("tier"),
                          "seat": r.get("_seat"), "attempt_id": aid, "attempt_no": r.get("attempt_no"),
                          "status": r.get("status"), "accepted": is_acc, "late": aid in late_ids,
                          "infra": r.get("infra"), "rec_name": rec_name(r), "location": m["location"],
                          "path": m["path"], "files": m["files"], "recorder_verify": r.get("recorder_verify"),
                          "media_ok": media_ok(m), "issue": reason})

        # 分数
        cells: dict[str, dict] = {}
        for c, den in sorted(cell_den.items()):
            ks = [k for k in mkeys if cell_of(mkeys[k]) == c]
            cc = Counter(outcome[k] for k in ks)
            cells[c] = {"denominator": den, "done": sum(cc[s] for s in (*TERMINAL, "error")), "success": cc["success"],
                        "fail": cc["fail"], "timeout": cc["timeout"], "error": cc["error"], "missing": cc["missing"],
                        "conflict": cc["conflict"], "success_rate": cc["success"] / den if den else None}
        tasks: dict[str, dict] = {}
        for t, den in sorted(task_den.items()):
            s = sum(1 for k in mkeys if mkeys[k]["task"] == t and outcome[k] == "success")
            tasks[t] = {"denominator": den, "success": s, "success_rate": s / den if den else None}
        tiers: dict[str, dict] = {}
        for tier in sorted({str(r["tier"]) for r in mkeys.values()}):
            ks = [k for k in mkeys if str(mkeys[k]["tier"]) == tier]
            s = sum(1 for k in ks if outcome[k] == "success")
            tiers[tier] = {"denominator": len(ks), "success": s, "success_rate": s / len(ks) if ks else None}
        micro = oc["success"] / len(mkeys) if mkeys else None
        macro = statistics.fmean(v["success_rate"] for v in tasks.values()) if tasks else None

        # 预算（逐席）
        seats: dict[str, dict] = defaultdict(lambda: {"reset_claim": 0, "attempts": 0, "infra_retries": 0,
                                                     "reset_budget": None, "infra_retry_budget": None,
                                                     "budget_raise": [], "budget_exhausted": 0, "run_blocked": 0,
                                                     "infra_error_attempts": 0})
        for l in st["ledger"]:
            s = seats[l["_seat"]]
            kind = l.get("kind")
            if kind == "reset_claim":
                s["reset_claim"] += 1
            elif kind == "attempt_start":
                s["attempts"] += 1
                if int(l.get("attempt_no") or 1) >= 2:
                    s["infra_retries"] += 1
            elif kind == "budget":
                for f in ("reset_budget", "infra_retry_budget"):
                    if l.get(f) is not None:
                        s[f] = max(int(l[f]), s[f] or 0)
            elif kind == "budget_raise":
                s["budget_raise"].append({"from": l.get("from"), "to": l.get("to"), "reason": l.get("reason")})
        for r in an["rows"]:
            s = seats[r["_seat"]]
            s["budget_exhausted"] += bool(r.get("budget_exhausted"))
            s["run_blocked"] += bool(r.get("run_blocked"))
            s["infra_error_attempts"] += bool(r.get("infra")) and r.get("status") == "error"
        budget = {"seats": dict(sorted(seats.items())),
                  "reset_claim_total": sum(s["reset_claim"] for s in seats.values()),
                  "infra_retries_total": sum(s["infra_retries"] for s in seats.values()),
                  "attempts_total": sum(s["attempts"] for s in seats.values()),
                  "budget_raise_total": sum(len(s["budget_raise"]) for s in seats.values())}

        per_policy[pol] = {
            "denominator": len(mkeys), "outcomes": {s: oc[s] for s in (*TERMINAL, "error", "missing", "conflict")},
            "accepted": len(acc), "micro_success_rate": micro, "task_macro_success_rate": macro,
            "cells": cells, "tasks": tasks, "tiers": tiers, "budget": budget,
            "extra_keys": extra, "conflicts": an["conflicts"], "accept_without_row": an["accept_no_row"],
            "duplicate": an["duplicate"],
            "late": [{"key": key_of(r), "attempt_id": r.get("attempt_id"), "attempt_no": r.get("attempt_no"),
                      "status": r.get("status"), "ledger_late": str(r.get("attempt_id")) in an["late_ids"]}
                     for r in an["late"]],
            "abandoned": [{"key": key_of(r), "attempt_id": r.get("attempt_id"), "attempt_no": r.get("attempt_no"),
                           "status": r.get("status"), "infra": r.get("infra"),
                           "reason": str(r.get("infra_reason") or r.get("error") or "")[:200]} for r in an["abandoned"]],
            "errors_without_video": no_video_errors,
            "_acc": acc, "_outcome": outcome,
        }

    # 中途进度：按已完成局墙钟估算各席剩余
    progress = None
    if partial:
        seat_of = {**shard_of, **load_shard_files(shard_files), **observed_seat}
        progress = estimate_progress(mkeys, seat_of, per_policy, policies, cell_den)
    for p in per_policy.values():
        p.pop("_acc")
        p.pop("_outcome")

    coverage_pass = all(cov[k] == 0 for k in ("missing", "extra", "duplicate", "conflicting_terminal"))
    report_pass = not count_mismatch and not media_unexplained and not exec_over_cap
    return {
        "schema": "v8-eval-report/1", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "manifest": str(manifest_path), "stage": str(stage), "videos": str(videos) if videos else None,
        "partial": partial, "cap": cap, "expect_total": expect_total, "policies": policies,
        "coverage": {"pass": coverage_pass, **{k: cov[k] for k in
                                              ("missing", "extra", "duplicate", "conflicting_terminal", "late_ignored", "error_final")}},
        "report": {"pass": report_pass, "count_mismatch": len(count_mismatch),
                   "media_unexplained": len(media_unexplained), "exec_over_cap": len(exec_over_cap)},
        "count_mismatch_detail": count_mismatch, "media_unexplained_detail": media_unexplained,
        "exec_over_cap_detail": exec_over_cap, "per_policy": per_policy, "progress": progress,
        "_index": index,
    }


def estimate_progress(mkeys: dict, shard_of: dict, per_policy: dict, policies: list[str], cell_den: Counter) -> dict:
    """各席剩余 = Σ 模型 Σ 该席未完成身份 × 该模型该任务已完成局平均墙钟（无观测时退回该模型全局平均并标出）。
    每席按 policies 顺序串行跑两个模型，总剩余 = 最慢席位剩余。"""
    out: dict[str, Any] = {"policies": {}, "seats": {}, "unobserved_cells": {}}
    est_task: dict[str, dict[str, float]] = {}
    est_pol: dict[str, float | None] = {}
    for pol in policies:
        acc = per_policy[pol]["_acc"]
        walls: dict[str, list[float]] = defaultdict(list)
        for k, r in acc.items():
            w = wall_of(r)
            if w is not None and k in mkeys:
                walls[mkeys[k]["task"]].append(w)
        est_task[pol] = {t: statistics.fmean(v) for t, v in walls.items()}
        allw = [w for v in walls.values() for w in v]
        est_pol[pol] = statistics.fmean(allw) if allw else None
        done = per_policy[pol]["accepted"]
        out["policies"][pol] = {"done": done, "denominator": len(mkeys),
                                "cells_done": {c: v["done"] for c, v in per_policy[pol]["cells"].items()},
                                "mean_wall_s": est_pol[pol]}
        out["unobserved_cells"][pol] = sorted(c for c, v in per_policy[pol]["cells"].items() if v["done"] == 0)
    seats = sorted(set(shard_of.values())) or ["?"]
    for sid in seats:
        total = 0.0
        unknown = False
        detail = {}
        for pol in policies:
            outcome = per_policy[pol]["_outcome"]
            rem = [k for k in mkeys if shard_of.get(k, "?") == sid and outcome[k] not in (*TERMINAL, "error")]
            secs = 0.0
            fallback = 0
            for k in rem:
                t = mkeys[k]["task"]
                if t in est_task[pol]:
                    secs += est_task[pol][t]
                elif est_pol[pol] is not None:
                    secs += est_pol[pol]
                    fallback += 1
                else:
                    unknown = True
            detail[pol] = {"remaining": len(rem), "est_s": None if (rem and est_pol[pol] is None) else secs,
                           "fallback_mean_used": fallback}
            total += secs
        out["seats"][sid] = {"est_remaining_s": None if unknown else total, "detail": detail}
    known = [v["est_remaining_s"] for v in out["seats"].values()]
    out["est_remaining_s"] = None if any(v is None for v in known) else (max(known) if known else 0.0)
    out["slowest_seat"] = (max(out["seats"], key=lambda s: out["seats"][s]["est_remaining_s"] or 0)
                           if out["seats"] and out["est_remaining_s"] is not None else None)
    return out


# ---------------------------------------------------------------- 输出

def pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def render_md(rep: dict, cov_line: str, rep_line: str) -> str:
    L: list[str] = []
    L.append("# V8 双模型评估汇总" + ("（中途进度）" if rep["partial"] else ""))
    L.append("")
    L.append(f"- 生成时间：{rep['generated_at']}")
    L.append(f"- manifest：`{rep['manifest']}`；运行根：`{rep['stage']}`；本机视频根：`{rep['videos']}`")
    L.append(f"- 口径：每身份唯一权威终态取账本 `accept` 行的 `accepted_attempt_id`；迟到终态与废弃尝试单列、不入分数；"
             f"分母固定为 manifest 身份数（{rep['expect_total']}／模型）；执行步上限 {rep['cap']}，超过即判 FAIL。"
             + ("中途进度下「缺失」即尚未完成，不判 FAIL；判定行的 missing 不计。" if rep["partial"] else ""))
    L.append("")
    L.append("```")
    L.append(cov_line)
    L.append(rep_line)
    L.append("```")
    L.append("")
    L.append("## 总表")
    L.append("")
    L.append("| 模型 | 分母 | 已定终态 | 成功 | 失败 | timeout | error | 缺失 | 冲突 | 全局微平均 | 任务宏平均 | 迟到 | 废弃尝试 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for pol, p in rep["per_policy"].items():
        o = p["outcomes"]
        L.append(f"| {pol} | {p['denominator']} | {p['accepted']} | {o['success']} | {o['fail']} | {o['timeout']} | "
                 f"{o['error']} | {o['missing']} | {o['conflict']} | {pct(p['micro_success_rate'])} | "
                 f"{pct(p['task_macro_success_rate'])} | {len(p['late'])} | {len(p['abandoned'])} |")
    L.append("")
    pols = list(rep["per_policy"])
    L.append("## 任务×档成功率（成功／分母；括号内 timeout／error／缺失）")
    L.append("")
    L.append("| 格 | " + " | ".join(pols) + " |")
    L.append("|---|" + "---:|" * len(pols))
    cells = sorted(next(iter(rep["per_policy"].values()))["cells"]) if pols else []
    for c in cells:
        cols = []
        for pol in pols:
            v = rep["per_policy"][pol]["cells"][c]
            cols.append(f"{v['success']}/{v['denominator']} {pct(v['success_rate'])} "
                        f"({v['timeout']}/{v['error']}/{v['missing']})")
        L.append(f"| {c} | " + " | ".join(cols) + " |")
    L.append("")
    L.append("## 按任务（跨档）与按档（跨任务）")
    L.append("")
    L.append("| 任务 | " + " | ".join(pols) + " |")
    L.append("|---|" + "---:|" * len(pols))
    tasks = sorted(next(iter(rep["per_policy"].values()))["tasks"]) if pols else []
    for t in tasks:
        L.append(f"| {t} | " + " | ".join(
            f"{rep['per_policy'][p]['tasks'][t]['success']}/{rep['per_policy'][p]['tasks'][t]['denominator']} "
            f"{pct(rep['per_policy'][p]['tasks'][t]['success_rate'])}" for p in pols) + " |")
    L.append("")
    L.append("| 档 | " + " | ".join(pols) + " |")
    L.append("|---|" + "---:|" * len(pols))
    tiers = sorted(next(iter(rep["per_policy"].values()))["tiers"]) if pols else []
    for t in tiers:
        L.append(f"| {t} | " + " | ".join(
            f"{rep['per_policy'][p]['tiers'][t]['success']}/{rep['per_policy'][p]['tiers'][t]['denominator']} "
            f"{pct(rep['per_policy'][p]['tiers'][t]['success_rate'])}" for p in pols) + " |")
    L.append("")
    L.append("## 预算（逐席）")
    L.append("")
    for pol, p in rep["per_policy"].items():
        b = p["budget"]
        L.append(f"**{pol}**：reset_claim 总数 {b['reset_claim_total']}，尝试 {b['attempts_total']}，"
                 f"infra 重试 {b['infra_retries_total']}，额度提升 {b['budget_raise_total']} 次。")
        L.append("")
        L.append("| 席 | reset_claim | reset 额度 | 尝试 | infra 重试 | infra 重试额度 | infra 错误尝试 | 额度耗尽 | 运行阻塞 | 额度提升 |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for sid, s in b["seats"].items():
            raises = "；".join(f"{x['from']}→{x['to']}（{x['reason']}）" for x in s["budget_raise"]) or "—"
            L.append(f"| {sid} | {s['reset_claim']} | {s['reset_budget']} | {s['attempts']} | {s['infra_retries']} | "
                     f"{s['infra_retry_budget']} | {s['infra_error_attempts']} | {s['budget_exhausted']} | "
                     f"{s['run_blocked']} | {raises} |")
        L.append("")
    L.append("## 迟到终态与废弃尝试（不入分数）")
    L.append("")
    any_side = False
    for pol, p in rep["per_policy"].items():
        for x in p["late"]:
            any_side = True
            L.append(f"- {pol} 迟到 `{x['key']}` attempt_no={x['attempt_no']} status={x['status']} "
                     f"账本 late={x['ledger_late']}")
        for x in p["abandoned"]:
            any_side = True
            L.append(f"- {pol} 废弃 `{x['key']}` attempt_no={x['attempt_no']} status={x['status']} infra={x['infra']} "
                     f"原因：{x['reason'] or '（无）'}")
    if not any_side:
        L.append("- 无")
    L.append("")
    L.append("## 异常明细")
    L.append("")
    lines = []
    for pol, p in rep["per_policy"].items():
        for c in p["conflicts"]:
            lines.append(f"- {pol} 冲突终态 `{c['key']}`：{c['reason']} {json.dumps({k: v for k, v in c.items() if k not in ('key', 'reason')}, ensure_ascii=False)}")
        for c in p["accept_without_row"]:
            lines.append(f"- {pol} accept 指向的结果行未出现 `{c['key']}` attempt_id={c['attempt_id']}")
        if p["extra_keys"]:
            lines.append(f"- {pol} manifest 之外的身份 {len(p['extra_keys'])} 个：{', '.join(p['extra_keys'][:20])}")
        for e in p["errors_without_video"]:
            lines.append(f"- {pol} 无录像的错误尝试 `{e['key']}` status={e['status']}：{e['reason'] or '（未说明）'}")
    for x in rep["exec_over_cap_detail"]:
        lines.append(f"- exec_steps 越限 {x['policy']} `{x['key']}` exec_steps={x['exec_steps']} > {rep['cap']}")
    for x in rep["count_mismatch_detail"]:
        lines.append(f"- 计数不一致：{x}")
    for x in rep["media_unexplained_detail"]:
        lines.append(f"- 媒体无法解释 {x['policy']} `{x['key']}`：{x['reason']}")
    L.extend(lines or ["- 无"])
    L.append("")
    pr = rep.get("progress")
    if pr:
        L.append("## 中途进度")
        L.append("")
        for pol, v in pr["policies"].items():
            L.append(f"- {pol}：已完成 {v['done']}/{v['denominator']}，已完成局平均墙钟 {_fmt_s(v['mean_wall_s'])}")
            un = pr["unobserved_cells"][pol]
            L.append(f"  - 未观测格（尚无完成局，用该模型全局平均估算）{len(un)} 个：{', '.join(un) if un else '无'}")
        L.append("")
        L.append(f"预计剩余（最慢席位）：**{_fmt_s(pr['est_remaining_s'])}**（席 {pr['slowest_seat']}）")
        L.append("")
        L.append("| 席 | 预计剩余 | " + " | ".join(f"{p} 剩余局" for p in pols) + " |")
        L.append("|---|---:|" + "---:|" * len(pols))
        for sid, s in pr["seats"].items():
            L.append(f"| {sid} | {_fmt_s(s['est_remaining_s'])} | " +
                     " | ".join(str(s["detail"][p]["remaining"]) for p in pols) + " |")
        L.append("")
    L.append("视频索引见同目录 `video-index.jsonl`（每次尝试一行，含终态、迟到、错误尝试）。")
    return "\n".join(L) + "\n"


def lines_of(rep: dict) -> tuple[str, str]:
    c, r = rep["coverage"], rep["report"]
    cov_line = (f"V8_EVAL_COVERAGE={'PASS' if c['pass'] else 'FAIL'} policies={len(rep['policies'])} "
                f"missing={c['missing']} extra={c['extra']} duplicate={c['duplicate']} "
                f"conflicting_terminal={c['conflicting_terminal']} late_ignored={c['late_ignored']} error_final={c['error_final']}")
    rep_line = (f"V8_EVAL_REPORT={'PASS' if r['pass'] else 'FAIL'} count_mismatch={r['count_mismatch']} "
                f"media_unexplained={r['media_unexplained']} exec_over_cap={r['exec_over_cap']}")
    return cov_line, rep_line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--stage", required=True, help="运行根（含 sNN/<policy>/）")
    ap.add_argument("--policies", default="smvla,mme")
    ap.add_argument("--out", required=True)
    ap.add_argument("--videos", default=None, help="本机视频根（eval_video_mover --mode v8 的 --dest）")
    ap.add_argument("--partial", action="store_true", help="中途进度：不因缺失／媒体未就位判 FAIL")
    ap.add_argument("--expect-total", type=int, default=DEFAULT_TOTAL)
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--shard-files", default=None,
                    help="--partial 估算用：实际分片文件 glob（shard-NN.json → 席 NN），覆盖 manifest 的 shard 字段；"
                         "已观测到的身份一律以运行根里实际所在 sNN 为准")
    args = ap.parse_args(argv)
    policies = [p for p in args.policies.split(",") if p]
    rep = build_report(Path(args.manifest), Path(args.stage), policies,
                       Path(args.videos) if args.videos else None,
                       partial=args.partial, expect_total=args.expect_total, cap=args.cap,
                       shard_files=args.shard_files)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index = rep.pop("_index")
    cov_line, rep_line = lines_of(rep)
    rep["verdict_lines"] = [cov_line, rep_line]
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                     encoding="utf-8")
    with (out / "video-index.jsonl").open("w", encoding="utf-8") as fh:
        for row in index:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "report.md").write_text(render_md(rep, cov_line, rep_line), encoding="utf-8")
    if rep.get("progress"):
        pr = rep["progress"]
        done = " ".join(f"{p}={v['done']}/{v['denominator']}" for p, v in pr["policies"].items())
        print(f"V8_EVAL_PROGRESS {done} est_remaining_s="
              f"{'unobserved' if pr['est_remaining_s'] is None else round(pr['est_remaining_s'])} "
              f"slowest_seat={pr['slowest_seat']}", flush=True)
    print(cov_line, flush=True)
    print(rep_line, flush=True)
    return 0 if rep["coverage"]["pass"] and rep["report"]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
