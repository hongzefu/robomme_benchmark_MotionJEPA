#!/usr/bin/env python3
"""v7.5eval 第 6 步：出结论的汇总器（纯 CPU、benchmark ``.venv``、幂等，可随时重跑）。

口径见 0929-v7.5eval-restructure-plan.md §3.1、§3.2（2.1～第 6 步）、第二部分 §2 判定行总表与 §6 留档。

做什么：

- 扫描当前已有的全部产物，凡输入齐全的比较就算出来并打印判定行；输入不全的打印
  ``<NAME>=PENDING ... have=<已有>/<应有>``，不报错、不中断。
- 统计一律复用现成工具，不另写：闭环比较、官方噪声带、主比较、相对标准、测速汇总调用
  ``compare.py``（按路径导入，直接调它的 ``cmd_*`` 并截下判定行）；环境逐层对拍调用
  ``scripts/parity/hard_regression.py`` 的 ``env-digest-compare``；策略回放的确定性默认值调用
  ``policy_replay.py`` 的 ``det_rule`` 复核；队列核对调用 ``claim_queue.py`` 的 ``ClaimQueue.check``。
- 写 ``artifacts/v7.5eval/summary/``：``summary.json``（全部条目与明细路径）、``verdicts.txt``（全部判定行）、
  ``detail/*.json``（各比较完整明细）、``merged/*.jsonl``（新接口各格合并后的逐局记录，金丝雀单列）、
  ``fragments/*.md``（中文留档片段，供主会话贴进 ``docs/validation/v7.5eval/*.md``）。

各部分：

- 2.1 ``ENV_DIGEST_PARITY``：C1:C2、C1:C3、C1:C5、C5:C6、C5:C7；已有 ``env/parity-<a>-<b>.json`` 且不旧于两格
  ``rows.jsonl`` 就复用，否则重算到 ``summary/detail/``（不覆盖 ``env/`` 下的原文件）。
- 旧新环境栈 ``ENV_STACK=INFO``：官方重跑一（及 R1）录下的 reset 原始数据 vs 2.1 同卡型格子（O1→C5、C7；R1→C1），
  逐身份比演示帧数（官方 reset 帧 = 演示帧 + 初始帧）、逐帧图像 MAD、reset 状态最大绝对差。
- 2.2 ``OBSERVER_SMOKE=INFO``：不加录制器的 SMVLA 1 局 vs 官方重跑一同一身份（视频文件 sha、逐帧解码 sha、终态、步数）。
- 2.3／第 6 步：``E0_SELF``（E0 自比健全性）、``OFFICIAL_RERUN``（进度）、``OFFICIAL_NOISE``、``PROD_VS_OFFICIAL``、
  ``RELATIVE_ACCEPT``（身份不全且 ``--final`` 时按运行阻塞输出）、``EXTRA_SAMPLE``（追加样本触发）。
- 第 3 步 ``STEP3=INFO``；第 4 步 ``POLICY_REPLAY``／``DET_RULE``／``IFACE_OPEN``（P2 并入 P1、P6 并入 P5）。
- 5.1 ``EVAL_PARITY``：E1:E2、E1:E3、E1:E5、E5:E6、E5:E7、R1:E1（同卡新旧接口闭环）、O1:E5（小样本 48）；
  ``EVAL_VS_E0``（各条件 vs 官方历史成绩，只报转移）。
- 5.2 ``QUEUE_CLAIM``、``CANARY=INFO``（金丝雀不进 192 比较，单独与同身份正式局、官方重跑一比）。
- 测速 ``ENV_SPEED``／``EVAL_SPEED``（``compare.summarize_speed``）；预算 ``BUDGET=INFO``（对照 §3.4 上限，估计值标 est）。

用法::

    uv run --no-sync python scripts/eval-official/step6_summary.py [--final] [--partial] [--no-decode]

``--partial``：输入不全时也在已有身份的交集上算（行里带 ``partial=yes``，仅供开发期观察）；
``--final``：第 6 步正式出结论，身份不全的相对标准按运行阻塞输出（``blocked=yes``）而非 PENDING。
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_ART = REPO / "artifacts" / "v7.5eval"
DEFAULT_NFS = Path("/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval")

POLICIES = ("smvla", "mme")
ENV_PAIRS = (("C1", "C2"), ("C1", "C3"), ("C1", "C5"), ("C5", "C6"), ("C5", "C7"))
EVAL_PAIRS = (("E1", "E2"), ("E1", "E3"), ("E1", "E5"), ("E5", "E6"), ("E5", "E7"))
E_CONDS = ("E1", "E2", "E3", "E5", "E6", "E7")
REPLAY_CONDS = ("P1", "P3", "P5", "P7")  # 用户决定：P2 并入 P1、P6 并入 P5
ENV_STACK_PAIRS = (("O1", "C5"), ("O1", "C7"), ("R1", "C1"))
OFFICIAL_DIRS = {"O1": ("O1",), "O2": ("O2",), "R1": ("R1", "R1smoke")}
NOREC_IDENTITY = ("PickXtimes", 510300)

# §3.4 预算表（跑前写死）：(条目, 轨迹尝试上限, 基础设施重试上限)
BUDGET_CAPS = (
    ("2.1 环境检测", 288, 6),
    ("2.2 录制器验证", 1, None),
    ("2.3 官方重跑两遍", 768, 12),
    ("2.4 本机旧官方小样本", 96, 4),
    ("3.1 跑通", 2, None),
    ("5.1 换条件评估", 576, 12),
    ("5.2 正式跑法", 384, 8),
    ("5.2 金丝雀", 16, None),
    ("其他 杀server测试", 3, None),
)
BUDGET_OTHER_RETRY_CAP = 2  # 「其他 2」：2.2、3.1、金丝雀共用
BUDGET_TOTAL_CAP = 2271

ENV_SPEED_KEYS = ("wall_s", "make_env_s", "gym_make_s", "eval_reset_s", "inner_reset_s", "demo_s", "demo_s_per_frame", "close_s")
EVAL_SPEED_KEYS = ("episode_wall_s", "env.env_build_s", "env.reset_s", "env.step_mean_s", "policy.infer.server_steady_mean_s",
                   "policy.infer.rtt_mean_s", "recorder.encode_cpu_s", "recorder.finalize_s", "elapsed_s")

SECTION_TITLES = {
    "env_parity": "2.1 环境本身稳不稳定（ENV_DIGEST_PARITY）",
    "env_stack": "旧环境栈 vs 新环境栈（ENV_STACK）",
    "observer": "2.2 录制器会不会改结果（OBSERVER_SMOKE）",
    "official": "2.3 官方自己重跑两遍与官方噪声带（OFFICIAL_NOISE）",
    "step3": "第 3 步 新接口跑通（STEP3）",
    "replay": "第 4 步 策略本身稳不稳定（POLICY_REPLAY／DET_RULE／IFACE_OPEN）",
    "eval_conditions": "5.1 新接口换条件还一致吗（EVAL_PARITY）",
    "prod": "5.2 正式跑法与第 6 步相对标准（PROD_VS_OFFICIAL／RELATIVE_ACCEPT）",
    "killtest": "5.2 杀 server 续跑测试（KILLTEST）",
    "infra": "基础设施失败统计（INFRA；infra=True 永不算策略结果）",
    "incident": "GPU 计算模式事故（INCIDENT；*-vulkanfail-* 留档不进比较）",
    "speed": "测速（ENV_SPEED／EVAL_SPEED）",
    "budget": "预算核算（§3.4）",
}
# 留档文件 → 该文件收的部分（§6 留档）
FRAGMENTS = {
    "env-parity": ("env_parity", "env_stack"),
    "official-rerun": ("observer", "official"),
    "policy-replay": ("replay",),
    "eval-conditions": ("step3", "eval_conditions"),
    "prod-vs-official": ("prod", "killtest", "incident", "infra"),
    "summary": tuple(SECTION_TITLES),
}


# ---------------------------------------------------------------------------
# 按路径导入复用模块
# ---------------------------------------------------------------------------

_MODS: dict[str, Any] = {}


def load_module(alias: str, path: Path):
    """按文件路径导入模块（缓存）；本目录与 scripts/parity 均不是包。"""
    if alias in _MODS:
        return _MODS[alias]
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    _MODS[alias] = mod
    return mod


def cmp_mod():
    return load_module("v75_compare", HERE / "compare.py")


def hr_mod():
    return load_module("v75_hard_regression", REPO / "scripts" / "parity" / "hard_regression.py")


def pr_mod():
    return load_module("v75_policy_replay", HERE / "policy_replay.py")


def cq_mod():
    return load_module("v75_claim_queue", HERE / "claim_queue.py")


def rec_mod():
    return load_module("v75_recorder", HERE / "recorder.py")


def call_cmd(fn: Callable, **kw) -> tuple[int, list[str]]:
    """调现成工具的 cmd_* 函数并截下它打印的判定行。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(argparse.Namespace(**kw))
    return int(rc or 0), [l for l in buf.getvalue().splitlines() if l.strip()]


def dumps(obj: Any, indent: int | None = None) -> str:
    return cmp_mod().dumps(obj, indent=indent)


def fmt(x: Any, nd: int = 4) -> str:
    return cmp_mod().fmt(x, nd)


def read_jsonl_tolerant(path: Path) -> tuple[list[dict], int]:
    """读 jsonl，半行（进程被杀）跳过并计数。"""
    rows, bad = [], 0
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return rows, bad
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return rows, bad


def kv_line(name: str, level: str, fields: dict[str, Any]) -> str:
    return cmp_mod().verdict(name, level, fields)


# ---------------------------------------------------------------------------
# 汇总容器
# ---------------------------------------------------------------------------


class Report:
    """全部条目：section / name / status（INFO|PASS|FAIL|PENDING|BLOCKED|ERROR）/ line / data。"""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add(self, section: str, name: str, status: str, line: str, data: Any = None) -> None:
        self.entries.append({"section": section, "name": name, "status": status, "line": line, "data": data})
        print(line, flush=True)

    def pending(self, section: str, name: str, fields: dict[str, Any]) -> None:
        self.add(section, name, "PENDING", kv_line(name, "PENDING", fields))

    def lines(self, section: str, name: str, lines: list[str], data: Any = None, status: str | None = None) -> None:
        for l in lines:
            head = l.split(" ", 1)[0]
            nm, _, lvl = head.partition("=")
            if head == "BLOCKING":
                self.add(section, name, "BLOCKED", l, data)
                continue
            self.add(section, nm or name, status or (lvl or "INFO"), l, data)


# ---------------------------------------------------------------------------
# 数据源
# ---------------------------------------------------------------------------


class Layout:
    """产物位置。测试里整体指向合成目录。"""

    def __init__(self, art: Path, nfs: Path, out: Path, e0: dict[str, str]):
        self.art, self.nfs, self.out, self.e0 = Path(art), Path(nfs), Path(out), e0
        self.small48 = self.art / "identities-small48.json"
        self.full192 = self.art / "identities-full192.json"

    def keys(self, which: str) -> list[tuple[str, int]]:
        path = self.small48 if which == "small48" else self.full192
        return [(e["task"], int(e["seed"])) for e in json.loads(path.read_text(encoding="utf-8"))]

    def ident_path(self, which: str) -> Path:
        return self.small48 if which == "small48" else self.full192

    # 官方（旧代码）结果：NFS official/<run>/<policy>/
    def official_dir(self, run: str, policy: str) -> Path | None:
        for d in OFFICIAL_DIRS.get(run, (run,)):
            p = self.nfs / "official" / d / policy
            if p.is_dir():
                return p
        return None

    def official_rec_roots(self, run: str, policy: str) -> list[Path]:
        roots = []
        for d in OFFICIAL_DIRS.get(run, (run,)):
            roots += [self.art / "official-rec" / d / policy, self.nfs / "stage" / d / policy]
        return [r for r in roots if r.is_dir()]

    # 新接口结果：本机 newiface/<cond>/，GL 暂存 stage/<cond>/<policy>/s-*/，搬运后 official-rec/<cond>/<policy>/s-*/
    def new_roots(self, cond: str, policy: str) -> list[Path]:
        if cond == "S3":
            roots = [self.art / "newiface" / "step3"]
        else:
            local = self.art / "newiface" / cond / policy
            roots = [local if local.is_dir() else self.art / "newiface" / cond,
                     self.art / "official-rec" / cond / policy, self.nfs / "stage" / cond / policy]
        return [r for r in roots if r.is_dir()]


    QUEUES = {"N": "prod", "N2": "prod2", "N3": "prod3"}

    def queue_done(self, cond: str, policy: str) -> list[Path]:
        q = self.QUEUES.get(cond)
        if not q:
            return []
        return sorted((self.nfs / "queue" / q / policy / "done").glob("*.json"))

    def incident_dirs(self) -> list[Path]:
        out = []
        for base in (self.art / "official-rec", self.nfs / "stage"):
            out += [Path(p) for p in glob.glob(str(base / "*" / "*" / "*-vulkanfail-*")) if Path(p).is_dir()]
        return sorted(out)


class Sources:
    """按 (代号, 策略) 取逐局结果表，带缓存与加载统计。"""

    def __init__(self, lay: Layout):
        self.lay = lay
        self._cache: dict[tuple[str, str], dict | None] = {}

    def get(self, code: str, policy: str) -> dict | None:
        """返回 {"src": 给 compare.py 的源说明, "table": {(task,seed): rec}, "stats": {...}, "canary": [...]}；无数据 → None。"""
        if code == "NP":
            return self.prod(policy, self.lay.keys("full192"))
        k = (code, policy)
        if k not in self._cache:
            try:
                self._cache[k] = self._load(code, policy)
            except FileNotFoundError:
                self._cache[k] = None
        return self._cache[k]

    def _load(self, code: str, policy: str) -> dict | None:
        C = cmp_mod()
        if code == "E0":
            src = self.lay.e0[policy]
            table, stats = C.load_results(src)
            return {"src": src, "table": table, "stats": stats, "canary": [], "kind": "official"}
        if code in OFFICIAL_DIRS:
            d = self.lay.official_dir(code, policy)
            if d is None:
                return None
            # 旧官方启动器把 0 步的 Vulkan 设备创建失败也写成 status=error 行（GPU 计算模式事故）：
            # 这些行不是策略结果，先剔除再交给 compare.py（按原文件顺序拼接，「最后一条终态胜出」语义不变）
            keep, infra = [], []
            n_lines = 0
            for f in C.expand_source(str(d)):
                for r in read_jsonl_tolerant(f)[0]:
                    n_lines += 1
                    if r.get("status") == "error" and is_incident_record(r):
                        infra.append(infra_row(dict(r, infra=True, seat=f"s{r.get('shard')}"), str(f)))
                    else:
                        keep.append(r)
            mdir = self.lay.out / "merged"
            mdir.mkdir(parents=True, exist_ok=True)
            mpath = mdir / f"{code}-{policy}-official.jsonl"
            mpath.write_text("".join(dumps(r) + "\n" for r in keep), encoding="utf-8")
            if not keep:
                return None
            table, stats = C.load_results(str(mpath))
            stats.update(lines=n_lines, incident=len(infra), source_dir=str(d))
            return {"src": str(mpath), "table": table, "stats": stats, "canary": [], "kind": "official", "infra": infra,
                    "rec_roots": [str(r) for r in self.lay.official_rec_roots(code, policy)]}
        return self._load_new(code, policy)

    def _load_new(self, cond: str, policy: str) -> dict | None:
        """合并新接口各席位结果（含队列 done/ 里的终态副本）：
        - 目录名含 ``-vulkanfail-`` 的事故留档一律不进比较（另在 INCIDENT 部分报告）；
        - 去重：有 claim_token 按它，否则按记录内容（搬运期间两处各一份、队列 done 副本）；
        - 金丝雀单列；``infra=True``／``run_blocked`` 的记录永不算策略结果，只进 INFRA 统计；
        - 失效的 rec_dir（节点 /tmp、已搬走的暂存）置空以便按目录索引。"""
        roots = self.lay.new_roots(cond, policy)
        files: list[Path] = []
        for r in roots:
            files += sorted(Path(p) for p in glob.glob(str(r / "**" / "results*.jsonl"), recursive=True))
        files = [f for f in files if not is_incident_path(f)]
        qdone = self.lay.queue_done(cond, policy)
        if not files and not qdone:
            return None
        seen: set[str] = set()
        main: dict[tuple[str, int], dict] = {}
        canary: list[dict] = []
        canary_infra: list[dict] = []
        infra: list[dict] = []
        st = {"files": len(files), "queue_done_docs": len(qdone), "lines": 0, "bad_lines": 0, "exact_dup": 0, "canary": 0,
              "infra": 0, "dup_final": 0, "other_policy": 0, "attempts": 0, "incident": 0}

        def records():
            for f in files:
                rows, bad = read_jsonl_tolerant(f)
                st["bad_lines"] += bad
                for rec in rows:
                    yield rec, str(f)
            for f in qdone:
                try:
                    yield json.loads(f.read_text(encoding="utf-8")), str(f)
                except (OSError, json.JSONDecodeError):
                    st["bad_lines"] += 1

        for rec, fsrc in records():
            st["lines"] += 1
            if rec.get("policy") not in (None, policy):
                st["other_policy"] += 1
                continue
            h = dedup_key(rec)
            if h in seen:
                st["exact_dup"] += 1
                continue
            seen.add(h)
            st["attempts"] += 1
            rec = {k: v for k, v in rec.items() if not k.startswith("_")}
            rd = rec.get("rec_dir")
            if rd and (not Path(rd).is_dir() or is_incident_path(rd)):
                # 节点 /tmp 路径已失效：优先同一席位 results.jsonl 旁的 rec/<同名目录>（搬运后的位置）
                hint = Path(fsrc).parent / "rec" / Path(rd).name
                rec = dict(rec, rec_dir_stale=rd,
                           rec_dir=str(hint) if hint.is_dir() and not is_incident_path(hint) and fsrc.endswith(".jsonl") else None)
            if (rec.get("infra") or rec.get("run_blocked")) and rec.get("canary"):
                # 金丝雀的 infra 失败：单列（CANARY 另报），不进 INFRA／事故计数
                st["canary_infra"] = st.get("canary_infra", 0) + 1
                canary_infra.append(rec)
                continue
            if rec.get("infra") or rec.get("run_blocked"):
                st["infra"] += 1
                st["incident"] += is_incident_record(rec)
                infra.append(infra_row(rec, fsrc))
                continue
            if rec.get("canary"):
                st["canary"] += 1
                canary.append(rec)
                continue
            key = rec_key(rec)
            if key in main:
                st["dup_final"] += 1
            main[key] = rec
        # 仍无录制目录的：按目录索引补（跳过事故留档、多个候选取步数与结果相符且最新的一个）；
        # 实在找不到就写一个不存在的占位路径，使 compare.first_divergence 记 missing 而不回退到可能指向失败尝试的索引
        index = None
        for key, rec in list(main.items()) + [(rec_key(c), c) for c in canary]:
            if rec.get("rec_dir"):
                continue
            if index is None:
                index = build_rec_index(roots)
            d = pick_rec(index.get(key, []), rec.get("steps"))
            rec["rec_dir"] = str(d) if d else f"MISSING:{rec.get('rec_dir_stale') or key}"
        out = self._finish_merged(cond, policy, main, canary, st, infra, [str(r) for r in roots])
        out["canary_infra"] = canary_infra
        return out

    def _finish_merged(self, cond, policy, main, canary, st, infra, rec_roots) -> dict:
        mdir = self.lay.out / "merged"
        mdir.mkdir(parents=True, exist_ok=True)
        mpath = mdir / f"{cond}-{policy}.jsonl"
        mpath.write_text("".join(dumps(r) + "\n" for r in main.values()), encoding="utf-8")
        (mdir / f"{cond}-{policy}-canary.jsonl").write_text("".join(dumps(r) + "\n" for r in canary), encoding="utf-8")
        base = {"stats": st, "canary": canary, "kind": "new", "rec_roots": rec_roots, "infra": infra}
        if not main:
            return {"src": None, "table": {}, **base}
        table, lstats = cmp_mod().load_results(str(mpath))
        st.update({"records": lstats["records"], "non_final": lstats["non_final"]})
        return {"src": str(mpath), "table": table, **base}

    def prod(self, policy: str, keys: list[tuple[str, int]]) -> dict | None:
        """正式跑法（5.2）逐身份结果：N 与补跑队列 N2、N3 合并，每身份取非 infra 的真实结果；
        多个来源都有真实结果则标冲突（保留编号最小的来源，即 N 优先）。"""
        ck = ("NP", policy)
        if ck in self._cache:
            return self._cache[ck]
        codes = ("N", "N2", "N3")
        srcs = {c: self.get(c, policy) for c in codes}
        if all(v is None for v in srcs.values()):
            self._cache[ck] = None
            return None
        tabs = {c: (srcs[c] or {}).get("table", {}) for c in codes}
        raw: dict[tuple[str, int], dict] = {}
        origin: dict[tuple[str, int], str] = {}
        for c in reversed(codes):  # 后写者胜：N 最后写，冲突时保留 N
            src = srcs[c]
            if src and src.get("src"):
                for r in read_jsonl_tolerant(Path(src["src"]))[0]:
                    raw[rec_key(r)] = r
                    origin[rec_key(r)] = c
        infra_n = {(i["task"], i["seed"]) for i in (srcs["N"] or {}).get("infra", [])}
        conflicts = sorted(k for k in raw if sum(k in tabs[c] for c in codes) > 1)
        merge = {f"from_{c}": sum(v == c for v in origin.values()) for c in codes}
        merge.update({"poisoned_replaced": len({k for k in infra_n if k in raw and origin[k] != "N"}),
                      "still_missing": len([k for k in keys if k not in raw]), "conflicts": len(conflicts),
                      "conflict_keys": [f"{k[0]}/{k[1]}" for k in conflicts],
                      "poisoned_unreplaced": sorted(f"{k[0]}/{k[1]}" for k in infra_n if k not in raw)})
        st = {"attempts": 0, "canary": 0}
        roots = [r for c in codes for r in (srcs[c] or {}).get("rec_roots", [])]
        out = self._finish_merged("NP", policy, raw, [], st, [], roots)
        out["merge"] = merge
        self._cache[ck] = out
        return out


def histogram(items) -> str:
    """错误类型直方图：类型:次数;…（按次数降序）。"""
    c: dict[str, int] = {}
    for x in items:
        c[x] = c.get(x, 0) + 1
    return ";".join(f"{k}:{v}" for k, v in sorted(c.items(), key=lambda t: (-t[1], t[0]))) or "none"


def rec_steps(d: Path) -> int | None:
    """录制目录 summary.json 里记下的终局步数（录制器 close(summary) 写入）。"""
    try:
        doc = json.loads((Path(d) / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    st = (doc.get("summary") or {}).get("steps")
    return int(st) if isinstance(st, (int, float)) else None


def build_rec_index(roots) -> dict[tuple[str, int], list[Path]]:
    """扫描录制根目录（排序、确定性），按 (task, seed) 收集全部候选录制目录；跳过 *-vulkanfail-* 事故留档。"""
    out: dict[tuple[str, int], list[Path]] = {}
    for root in roots:
        for m in sorted(glob.glob(str(Path(root) / "**" / "meta.json"), recursive=True)):
            d = Path(m).parent
            if is_incident_path(d) or not (d / "frames-front.jsonl").exists():
                continue
            try:
                meta = json.loads(Path(m).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("task") is None or meta.get("seed") is None:
                continue
            out.setdefault((meta["task"], int(meta["seed"])), []).append(d)
    return out


def pick_rec(cands: list[Path], steps: Any = None) -> Path | None:
    """多个候选时：先留 summary 步数与结果记录相符的，再取最新（meta.created，其次目录 mtime，再按路径名定序）。"""
    cands = [c for c in cands if not is_incident_path(c)]
    if not cands:
        return None
    if steps is not None:
        match = [c for c in cands if rec_steps(c) == int(steps)]
        if match:
            cands = match

    def order(c: Path):
        try:
            created = json.loads((c / "meta.json").read_text(encoding="utf-8")).get("created") or ""
        except (OSError, json.JSONDecodeError):
            created = ""
        try:
            mt = c.stat().st_mtime
        except OSError:
            mt = 0.0
        return (str(created), mt, str(c))

    return max(cands, key=order)


def parse_killtest(text: str) -> dict:
    """席位日志：SERVER_KILLED_FOR_TEST 之后又有 SERVER_START + SERVER_READY → 已重启；requeued／done 取最后一行 QUEUE_CLAIM，
    errors／infra／done（席位自己的局数）取 SEAT_DONE。"""
    import re

    lines = text.splitlines()
    kill = next((i for i, l in enumerate(lines) if "SERVER_KILLED_FOR_TEST" in l), None)
    after = lines[kill + 1:] if kill is not None else []
    restarted = any(l.startswith("SERVER_START") for l in after) and any(l.startswith("SERVER_READY") for l in after)

    def last_kv(prefix: str) -> dict:
        ln = next((l for l in reversed(lines) if l.startswith(prefix)), "")
        return dict(re.findall(r"(\w+)=(\S+)", ln))

    q, sd = last_kv("QUEUE_CLAIM="), last_kv("SEAT_DONE")
    return {"killed": kill is not None, "restarted": restarted, "requeued": q.get("requeued", "n/a"),
            "q_done": q.get("done", "n/a"), "q_total": q.get("total", "n/a"), "queue_check": q.get("QUEUE_CLAIM", "n/a"),
            "done": sd.get("done", "n/a"), "errors": sd.get("errors", "n/a"), "infra": sd.get("infra", "n/a")}


def is_incident_path(p: Path | str) -> bool:
    """事故留档目录（如 s-ding-vulkanfail-0540）：保留原样、不进任何比较。"""
    return any("-vulkanfail-" in part for part in Path(p).parts)


def rec_key(rec: dict) -> tuple[str, int]:
    return (rec.get("task"), int(rec.get("seed", (rec.get("identity") or {}).get("seed", -1))))


def dedup_key(rec: dict) -> str:
    if rec.get("claim_token"):
        return "tok:" + str(rec["claim_token"])
    body = {k: v for k, v in rec.items() if not k.startswith("_")}
    return "sha:" + hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def error_type(rec: dict) -> str:
    """infra 记录的错误类型：infra_reason + 错误文本最后一行的异常名与前 60 字。"""
    import re

    err = str(rec.get("error") or rec.get("env_exception") or "")
    lines = [l.strip() for l in err.splitlines() if l.strip()]
    last = lines[-1] if lines else "none"
    m = re.search(r"([A-Za-z_][\w.]*(?:Error|Exception|Failed))\b[:]?\s*(.*)", last)
    body = (m.group(1) + ":" + m.group(2)) if m else last
    return f"{rec.get('infra_reason') or 'n/a'}|{body[:60]}".replace(" ", "_").replace(";", ",")


#: §3.4 基础设施故障特征（小写匹配错误文本）
INFRA_SIGNATURES = ("svulkan2", "vulkan", "exclusive", "createdeviceunique", "connectionrefused", "websocket",
                    "connection reset", "out of memory", "cuda")


def infra_signature(rec: dict) -> str | None:
    """错误文本里第一个命中的 §3.4 基础设施特征（按 INFRA_SIGNATURES 顺序）；无则 None。"""
    err = (str(rec.get("error") or "") + " " + str(rec.get("env_exception") or "")).lower()
    return next((sig for sig in INFRA_SIGNATURES if sig in err), None)


def is_incident_record(rec: dict) -> bool:
    """0 步、环境没建成的基础设施失败（GPU 计算模式事故等）：
    新接口 infra=True 记录或旧官方 status=error 行，steps 为 0／缺失，且 infra_reason=env_build 或命中 §3.4 特征。"""
    if not (rec.get("infra") or rec.get("status") == "error"):
        return False
    if rec.get("steps"):
        return False
    return rec.get("infra_reason") == "env_build" or infra_signature(rec) is not None


def infra_row(rec: dict, src: str) -> dict:
    k = rec_key(rec)
    return {"task": k[0], "seed": k[1], "seat": str(rec.get("seat")), "cond": rec.get("cond"), "steps": rec.get("steps"),
            "type": error_type(rec), "incident": is_incident_record(rec), "sig": infra_signature(rec) or "none", "src": src}


def coverage(src: dict | None, keys: list[tuple[str, int]]) -> tuple[int, int]:
    if not src:
        return 0, len(keys)
    return len(set(src["table"]) & set(keys)), len(keys)


# ---------------------------------------------------------------------------
# 各部分
# ---------------------------------------------------------------------------


class Summary:
    def __init__(self, lay: Layout, *, final: bool = False, partial: bool = False, decode: bool = True):
        self.lay, self.final, self.partial, self.decode = lay, final, partial, decode
        self.src = Sources(lay)
        self.rep = Report()
        self.detail = lay.out / "detail"
        self.detail.mkdir(parents=True, exist_ok=True)
        self.extra: dict[str, Any] = {}

    # -- 通用：两源闭环比较的前置核对
    def _ready(self, codes: list[tuple[str, str]], keys: list[tuple[str, int]]) -> tuple[bool, str]:
        parts, ok = [], True
        for code, pol in codes:
            have, need = coverage(self.src.get(code, pol), keys)
            parts.append(f"{code}:{have}/{need}")
            ok &= have == need
        return ok, ",".join(parts)

    # ------------------------------------------------------------------ 2.1
    def sec_env_parity(self) -> None:
        S = "env_parity"
        envd = self.lay.art / "env"
        need = len(self.lay.keys("small48"))
        for a, b in ENV_PAIRS:
            name = f"{a}:{b}"
            ra, rb = envd / a / "rows.jsonl", envd / b / "rows.jsonl"
            na = len(hr_mod()._env_rows(envd / a)) if ra.exists() else 0
            nb = len(hr_mod()._env_rows(envd / b)) if rb.exists() else 0
            if (na < need or nb < need) and not self.partial:
                self.rep.pending(S, "ENV_DIGEST_PARITY", {"pair": name, "have": f"{a}:{na}/{need},{b}:{nb}/{need}"})
                continue
            existing = envd / f"parity-{a}-{b}.json"
            fresh = existing.exists() and existing.stat().st_mtime >= max(ra.stat().st_mtime, rb.stat().st_mtime)
            path = existing
            if not fresh:
                path = self.detail / f"env-parity-{a}-{b}.json"
                call_cmd(hr_mod().cmd_env_digest_compare, a=str(envd / a), b=str(envd / b), out=str(path))
            s = json.loads(path.read_text(encoding="utf-8"))
            line = kv_line("ENV_DIGEST_PARITY", "INFO", {
                "pair": name, "compared": s["compared"],
                "layer_equal": ",".join(f"{k}:{v}" for k, v in s["layer_equal"].items()),
                "first_diff": s["first_diff"], "state_max_abs": s.get("state_max_abs"), "image_mad": s.get("image_mad"),
                "image_mad_unit": s.get("image_mad_unit"), "obs_max_abs": s.get("obs_max_abs"),
                "identities_with_diff": s.get("identities_with_diff"),
                "name_only": sum((s.get("name_only") or {}).values()), "key_set_diff": s.get("key_set_diff"),
                "missing_in_a": len(s.get("missing_in_a", [])),
                "missing_in_b": len(s.get("missing_in_b", [])), "unmeasured": s.get("unmeasured"),
                "source": "reused" if fresh else "recomputed", "partial": "yes" if min(na, nb) < need else "no"})
            self.rep.add(S, "ENV_DIGEST_PARITY", "INFO", line, {"json": str(path)})

    # ------------------------------------------------------------------ 环境栈
    def _official_rec_index(self, run: str, policy: str) -> dict[tuple[str, int], Path]:
        """官方录制按身份建索引：跳过事故留档；同一身份多份（如 s3 与 s3-resume）取步数与计入的结果相符且最新的一份。"""
        table = (self.src.get(run, policy) or {}).get("table", {})
        idx = build_rec_index(self.lay.official_rec_roots(run, policy))
        out = {}
        for k, cands in idx.items():
            d = pick_rec(cands, (table.get(k) or {}).get("steps"))
            if d is not None:
                out[k] = d
        return out

    def _decode_prefix(self, mkv: Path, n: int) -> list[np.ndarray] | None:
        """只解码 mkv 前 n 帧（reset 帧在最前），rgb24。"""
        if not mkv.exists() or n <= 0:
            return None
        R = rec_mod()
        ff = R.find_ffmpeg()
        probe = subprocess.run([ff, "-hide_banner", "-i", str(mkv)], capture_output=True, text=True).stderr
        import re

        m = re.search(r"Video: .*?, (\d+)x(\d+)", probe)
        if not m:
            return None
        w, h = int(m.group(1)), int(m.group(2))
        p = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-threads", "1", "-i", str(mkv), "-frames:v", str(n),
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, check=False)
        if p.returncode != 0:
            return None
        fb = h * w * 3
        return [np.frombuffer(p.stdout[i:i + fb], np.uint8).reshape(h, w, 3) for i in range(0, len(p.stdout) - fb + 1, fb)]

    def _stack_one(self, off_dir: Path, row: dict, cell_dir: Path) -> dict:
        """单身份：官方 reset（演示帧 + 初始帧、reset 状态）vs 环境检测的演示帧 + reset_obs。"""
        R = rec_mod()
        events, _ = read_jsonl_tolerant(off_dir / "events.jsonl")
        resets = [e for e in events if e.get("kind") == "reset" and e.get("ok", True) and e.get("front_idx")]
        if not resets:
            return {"error": "官方录制里没有 reset 事件"}
        ev = resets[-1]
        z = np.load(cell_dir / row["npz"])
        out: dict[str, Any] = {"unmeasured": 0}
        for stream in ("front", "wrist"):
            recs, _ = read_jsonl_tolerant(off_dir / f"frames-{stream}.jsonl")
            lo, hi = ev.get(f"{stream}_idx", [None, None])
            if lo is None:
                out["unmeasured"] += 1
                continue
            off = [r for r in recs if lo <= r["idx"] <= hi]
            demo = z[f"demo_frames/{stream}"]
            new = ([demo[i] for i in range(len(demo))] if demo.ndim == 4 else []) + [z[f"reset_obs/{stream}_init"]]
            new_sha = [R.frame_sha256(f) for f in new]
            n = min(len(off), len(new))
            sha_eq = sum(off[i]["sha256"] == new_sha[i] for i in range(n))
            init_eq = off[-1]["sha256"] == new_sha[-1] if off else False
            same_n = len(off) == len(new)
            s = {"n_off": len(off), "n_new": len(new), "count_equal": same_n, "sha_equal": int(sha_eq),
                 "sha_compared": n, "init_sha_equal": bool(init_eq), "mad_max": 0.0 if (same_n and sha_eq == n) else None,
                 "mad_mean": 0.0 if (same_n and sha_eq == n) else None, "init_mad": 0.0 if init_eq else None}
            if (sha_eq < n or not init_eq) and self.decode and off:
                encs = [r.get("enc") for r in off]
                if all(e is not None for e in encs):
                    dec = self._decode_prefix(off_dir / f"{stream}.mkv", max(encs) + 1)
                    if dec is not None and len(dec) > max(encs):
                        imgs = [dec[e] for e in encs]
                        mads = [float(np.abs(imgs[i].astype(np.int16) - new[i].astype(np.int16)).mean()) for i in range(n)
                                if imgs[i].shape == new[i].shape]
                        # 帧数不同时逐帧对齐无意义：只报初始帧 MAD，逐帧 MAD 记 None（计入 unmeasured）
                        s["mad_max"] = (max(mads) if mads else None) if same_n else None
                        s["mad_mean"] = (float(np.mean(mads)) if mads else None) if same_n else None
                        if imgs[-1].shape == new[-1].shape:
                            s["init_mad"] = float(np.abs(imgs[-1].astype(np.int16) - new[-1].astype(np.int16)).mean())
            if s["mad_max"] is None:
                out["unmeasured"] += 1
            out[stream] = s
        # reset 状态：官方 (n, 8|9) = 关节 7 + 夹爪（8 维只取夹爪第 1 维）；环境检测 reset_obs 关节与夹爪逐帧列表
        try:
            st, _ = cmp_mod().load_array(off_dir, "reset_state")
            st = np.asarray(st, dtype=np.float64)
            if st.ndim == 3:
                st = st[-1]
            if st.ndim == 1:
                st = st[None]
            joint = np.asarray(z["reset_obs/joint_state_list"], dtype=np.float64).reshape(-1, 7)
            grip = np.asarray(z["reset_obs/gripper_state_list"], dtype=np.float64).reshape(len(joint), -1)
            new_st = np.concatenate([joint, grip[:, : st.shape[1] - 7]], axis=1)
            if new_st.shape == st.shape:
                out["state_rows"] = "all"
                out["state_max_abs"] = float(np.abs(new_st - st).max(initial=0.0))
            else:
                out["state_rows"] = "last"
                out["state_max_abs"] = float(np.abs(new_st[-1] - st[-1]).max(initial=0.0))
            out["state_shape"] = [list(st.shape), list(new_st.shape)]
        except (KeyError, FileNotFoundError, ValueError) as e:
            out["state_max_abs"] = None
            out["state_error"] = f"{type(e).__name__}: {e}"
            out["unmeasured"] += 1
        return out

    def sec_env_stack(self) -> None:
        S = "env_stack"
        keys = self.lay.keys("small48")
        for run, cell in ENV_STACK_PAIRS:
            cell_dir = self.lay.art / "env" / cell
            rows = hr_mod()._env_rows(cell_dir) if (cell_dir / "rows.jsonl").exists() else {}
            by_id = {(r["task"], int(r["seed"])): r for r in rows.values()}
            for pol in POLICIES:
                idx = self._official_rec_index(run, pol)
                common = [k for k in keys if k in idx and k in by_id]
                if len(common) < len(keys) and not (self.partial and common):
                    self.rep.pending(S, "ENV_STACK", {"src": run, "policy": pol, "cell": cell,
                                                     "have": f"{run}:{sum(k in idx for k in keys)}/{len(keys)},{cell}:{sum(k in by_id for k in keys)}/{len(keys)}"})
                    continue
                per = {}
                for k in common:
                    try:
                        per[f"{k[0]}/{k[1]}"] = self._stack_one(idx[k], by_id[k], cell_dir)
                    except Exception as e:  # 单身份读不出不影响其余
                        per[f"{k[0]}/{k[1]}"] = {"error": f"{type(e).__name__}: {e}"}
                ok = [v for v in per.values() if "error" not in v]

                def agg(stream: str, field: str, fn=max):
                    vals = [v[stream][field] for v in ok if stream in v and v[stream].get(field) is not None]
                    return fn(vals) if vals else None

                cnt_eq = sum(all(v[s]["count_equal"] for s in ("front", "wrist") if s in v) for v in ok)
                sha_eq = sum(v[s]["sha_equal"] for v in ok for s in ("front", "wrist") if s in v)
                sha_n = sum(v[s]["sha_compared"] for v in ok for s in ("front", "wrist") if s in v)
                states = [v["state_max_abs"] for v in ok if v.get("state_max_abs") is not None]
                path = self.detail / f"env-stack-{run}-{cell}-{pol}.json"
                path.write_text(dumps({"src": run, "cell": cell, "policy": pol, "per_identity": per}, indent=1) + "\n", encoding="utf-8")
                mads = [x for x in (agg("front", "mad_max"), agg("wrist", "mad_max")) if x is not None]
                inits = [x for x in (agg("front", "init_mad"), agg("wrist", "init_mad")) if x is not None]
                means = [x for x in (agg("front", "mad_mean", lambda v: float(np.mean(v))), agg("wrist", "mad_mean", lambda v: float(np.mean(v)))) if x is not None]
                line = kv_line("ENV_STACK", "INFO", {
                    "src": run, "policy": pol, "cell": cell, "compared": len(ok), "errors": len(per) - len(ok),
                    "demo_count_equal": f"{cnt_eq}/{len(ok)}", "frames_sha_equal": f"{sha_eq}/{sha_n}",
                    "image_mad_max": max(mads) if mads else None, "image_mad_mean": float(np.mean(means)) if means else None,
                    "init_mad_max": max(inits) if inits else None, "state_max_abs": max(states) if states else None,
                    "unmeasured": sum(v.get("unmeasured", 0) for v in ok),
                    "partial": "yes" if len(common) < len(keys) else "no",
                    "note": "官方reset帧=演示帧+初始帧;MAD为0-255刻度"})
                self.rep.add(S, "ENV_STACK", "INFO", line, {"json": str(path)})

    # ------------------------------------------------------------------ 2.2
    def _find_video(self, run: str, policy: str, rec: dict) -> Path | None:
        bn = Path(str(rec.get("video") or "")).name
        if not bn:
            return None
        first = Path(rec["video"])
        if first.is_file() and not is_incident_path(first):
            return first
        cands = []
        for root in self.lay.official_rec_roots(run, policy):
            cands += [Path(p) for p in sorted(glob.glob(str(root / "**" / bn), recursive=True))]
        cands = [c for c in cands if c.is_file() and not is_incident_path(c)]
        # 多份（如原片与续跑片）取最新
        return max(cands, key=lambda c: (c.stat().st_mtime, str(c))) if cands else None

    @staticmethod
    def _video_frames_sha(path: Path) -> list[str]:
        import imageio.v3 as iio

        return [hashlib.sha256(np.ascontiguousarray(f).tobytes()).hexdigest() for f in iio.imiter(str(path), plugin="FFMPEG")]

    def sec_observer(self) -> None:
        S = "observer"
        norec_file = self.lay.nfs / "official" / "norec" / "smvla" / "episodes-shard00of01.jsonl"
        if not norec_file.exists():
            self.rep.pending(S, "OBSERVER_SMOKE", {"reason": "norec 结果不存在"})
            return
        rows, _ = read_jsonl_tolerant(norec_file)
        nr = [r for r in rows if (r.get("task"), int(r.get("seed", -1))) == NOREC_IDENTITY]
        o1 = self.src.get("O1", "smvla")
        orec = o1["table"].get(NOREC_IDENTITY) if o1 else None
        if not nr or orec is None:
            self.rep.pending(S, "OBSERVER_SMOKE", {"identity": f"{NOREC_IDENTITY[0]}/{NOREC_IDENTITY[1]}",
                                                   "have": f"norec:{len(nr)}/1,O1:{int(orec is not None)}/1"})
            return
        n = nr[-1]
        vn = Path(n.get("video") or "")
        if not vn.is_file():
            vn = self.lay.nfs / "official" / "norec" / "smvla-videos" / vn.name
        o1_full = orec
        o1_raw = None
        src_file = orec["src"].rsplit(":", 1)[0]
        for r in read_jsonl_tolerant(Path(src_file))[0]:
            if (r.get("task"), int(r.get("seed", -1))) == NOREC_IDENTITY:
                o1_raw = r
        vo = self._find_video("O1", "smvla", o1_raw or {})
        if vo is None or not vn.is_file():
            self.rep.pending(S, "OBSERVER_SMOKE", {"reason": "视频未就位", "norec_video": vn.is_file(), "o1_video": vo is not None})
            return
        C = cmp_mod()
        fa, fb = self._video_frames_sha(vn), self._video_frames_sha(vo)
        nf = min(len(fa), len(fb))
        first = next((i for i in range(nf) if fa[i] != fb[i]), None if len(fa) == len(fb) else nf)
        data = {"norec": {"video": str(vn), "sha256": C.sha256_file(vn), "frames": len(fa), "status": n.get("status"), "steps": n.get("steps")},
                "o1": {"video": str(vo), "sha256": C.sha256_file(vo), "frames": len(fb), "status": o1_full["status"], "steps": o1_full["steps"]},
                "first_diff_frame": first}
        path = self.detail / "observer-smoke.json"
        path.write_text(dumps(data, indent=1) + "\n", encoding="utf-8")
        line = kv_line("OBSERVER_SMOKE", "INFO", {
            "identity": f"{NOREC_IDENTITY[0]}/{NOREC_IDENTITY[1]}", "file_equal": data["norec"]["sha256"] == data["o1"]["sha256"],
            "frames_equal": fa == fb, "frames": f"{len(fa)}/{len(fb)}", "first_diff_frame": first,
            "status_equal": n.get("status") == o1_full["status"], "steps_equal": n.get("steps") == o1_full["steps"],
            "steps": f"{n.get('steps')}/{o1_full['steps']}"})
        self.rep.add(S, "OBSERVER_SMOKE", "INFO", line, {"json": str(path)})

    # ------------------------------------------------------------------ 2.3 / E0
    def sec_official(self) -> None:
        S = "official"
        C = cmp_mod()
        full = self.lay.keys("full192")
        small = self.lay.keys("small48")
        for pol in POLICIES:
            e0 = self.src.get("E0", pol)
            if e0 is None:
                self.rep.pending(S, "E0_SELF", {"policy": pol, "reason": "E0 结果不存在"})
            else:
                r = C.run_pair(e0["src"], e0["src"], full)
                self.rep.add(S, "E0_SELF", "INFO", kv_line("E0_SELF", "INFO", {
                    "policy": pol, "compared": r["compared"], "missing": r["missing_a"], "s2f": r["s2f"], "f2s": r["f2s"],
                    "sr_pct": r["sr_a_pct"], "success": r["success_a"], "files": e0["stats"]["files"], "lines": e0["stats"]["lines"],
                    "superseded": e0["stats"]["superseded"], "sanity": "ok" if r["s2f"] == r["f2s"] == 0 else "BAD"}))
            for run in ("O1", "O2"):
                have, need = coverage(self.src.get(run, pol), full)
                st = "INFO" if have == need else "PENDING"
                self.rep.add(S, "OFFICIAL_RERUN", st, kv_line("OFFICIAL_RERUN", st, {"run": run, "policy": pol, "have": f"{have}/{need}"}))
            ok, have = self._ready([("E0", pol), ("O1", pol), ("O2", pol)], full)
            if not ok and not self.partial:
                self.rep.pending(S, "OFFICIAL_NOISE", {"policy": pol, "have": have})
            else:
                srcs = {c: self.src.get(c, pol) for c in ("E0", "O1", "O2")}
                if all(srcs.values()):
                    out = self.detail / f"official-noise-{pol}.json"
                    _, lines = call_cmd(C.cmd_official_noise, e0=srcs["E0"]["src"], o1=srcs["O1"]["src"], o2=srcs["O2"]["src"],
                                        identities=str(self.lay.full192), out=str(out), policy=pol)
                    self.rep.lines(S, "OFFICIAL_NOISE", [l + (" partial=yes" if not ok else "") for l in lines], {"json": str(out)})
                else:
                    self.rep.pending(S, "OFFICIAL_NOISE", {"policy": pol, "have": have})
            # R1（本机旧官方小样本）vs 官方历史成绩：只报转移
            self._vs_e0(S, "R1", pol, small, "OFFICIAL_VS_E0")

    def _vs_e0(self, S: str, code: str, pol: str, keys: list, name: str) -> None:
        C = cmp_mod()
        ok, have = self._ready([(code, pol)], keys)
        src, e0 = self.src.get(code, pol), self.src.get("E0", pol)
        if (not ok and not (self.partial and src and src["table"])) or e0 is None or not src or not src.get("src"):
            self.rep.pending(S, name, {"cond": code, "policy": pol, "have": have})
            return
        r = C.run_pair(e0["src"], src["src"], keys)
        out = self.detail / f"{code}-vs-E0-{pol}.json"
        C.write_json(out, r)
        m = r["status_matrix"]
        mat = ";".join(f"{x[0]}>{''.join(str(m[x][y]) + y[0] for y in C.STATUSES)}" for x in C.STATUSES)
        self.rep.add(S, name, "INFO", kv_line(name, "INFO", {
            "cond": code, "policy": pol, "compared": r["compared"], "missing_b": r["missing_b"], "s2f": r["s2f"], "f2s": r["f2s"],
            "new_err": r["new_err"], "new_timeout": r["new_timeout"], "success": f"{r['success_a']}>{r['success_b']}",
            "steps_equal": f"{r['steps_equal']}/{r['steps_compared']}", "matrix": mat, "partial": "no" if ok else "yes"}),
            {"json": str(out)})

    # ------------------------------------------------------------------ 第 3 步
    def sec_step3(self) -> None:
        S = "step3"
        for pol in POLICIES:
            s = self.src.get("S3", pol)
            if not s or not s["table"]:
                self.rep.pending(S, "STEP3", {"policy": pol})
                continue
            for (task, seed), r in s["table"].items():
                rows, _ = read_jsonl_tolerant(Path(r["src"].rsplit(":", 1)[0]))
                raw = next((x for x in rows if x.get("task") == task and int(x.get("seed", -1)) == seed), {})
                proto = raw.get("protocol") or {}
                t = raw.get("timing") or {}
                self.rep.add(S, "STEP3", "INFO", kv_line("STEP3", "INFO", {
                    "policy": pol, "identity": f"{task}/{seed}", "status": r["status"], "steps": r["steps"], "error": r["error"] or "none",
                    "recorder_verify": raw.get("recorder_verify"), "messages": proto.get("messages"), "frames_sent": proto.get("frames_sent"),
                    "sha_mismatch": proto.get("sha_mismatch"), "episode_wall_s": t.get("episode_wall_s"),
                    "gpu": (raw.get("gpu_name") or "n/a").replace(" ", "_"), "git": (raw.get("git_commit") or "n/a")[:8]}))

    # ------------------------------------------------------------------ 第 4 步
    def _replay_report(self, cond: str, pol: str) -> Path | None:
        for base in (self.lay.art / "replay", self.lay.nfs / "replay"):
            p = base / cond / pol / "report.json"
            if p.exists():
                return p
        return None

    def sec_replay(self) -> None:
        S = "replay"
        PR = pr_mod()
        for cond in REPLAY_CONDS:
            for pol in POLICIES:
                p = self._replay_report(cond, pol)
                if p is None:
                    self.rep.pending(S, "POLICY_REPLAY", {"cond": cond, "policy": pol, "reason": "report.json 未生成"})
                    continue
                rep = json.loads(p.read_text(encoding="utf-8"))
                comps = rep.get("comparisons") or []
                groups: dict[tuple[str, str], list[dict]] = {}
                for c in comps:
                    groups.setdefault((str(c.get("det")), str(c.get("mode"))), []).append(c)
                for (det, mode), cs in sorted(groups.items()):
                    maxabs = [c.get("max_abs") for c in cs if c.get("max_abs") is not None]
                    fds = [c.get("first_diff_step") for c in cs if c.get("first_diff_step") is not None]
                    self.rep.add(S, "POLICY_REPLAY", "INFO", kv_line("POLICY_REPLAY", "INFO", {
                        "cond": cond, "policy": pol, "det": det, "mode": mode, "n": len(cs),
                        "bitwise": f"{sum(bool(c.get('bitwise')) for c in cs)}/{len(cs)}",
                        "max_abs": max(maxabs) if maxabs else 0.0, "first_diff_step_min": min(fds) if fds else None,
                        "above_action_max": sum((c.get("ref") or {}).get("side") == "above" for c in cs)}), {"report": str(p)})
                rule = rep.get("det_rule") or {}
                on_bw = [bool(c.get("bitwise")) for c in comps if c.get("det") == "on" and c.get("mode") in ("same", "restart")]
                re_rule = PR.det_rule(on_bw, rule.get("infer_ms_off"), rule.get("infer_ms_on"))
                self.rep.add(S, "DET_RULE", "INFO", kv_line("DET_RULE", "INFO", {
                    "cond": cond, "policy": pol, "det_bitwise": rule.get("det_bitwise"), "slowdown_pct": rule.get("slowdown_pct"),
                    "default": rule.get("default"), "recheck": "same" if re_rule["default"] == rule.get("default") else f"DIFF:{re_rule['default']}",
                    "rng_restored_all": rep.get("rng_restored_all"), "gpu_busy_events": rep.get("gpu_busy_events")}), {"report": str(p)})
        files = sorted(glob.glob(str(self.lay.art / "replay" / "iface" / "*.json")))
        if not files:
            self.rep.pending(S, "IFACE_OPEN", {"reason": "replay/iface/*.json 未生成"})
        for f in files:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            ex = d.get("exec_new_vs_official") or {}
            act = d.get("action") or {}
            ad = (act.get("official_recorded_vs_new_replay") or {}).get("max_abs")
            self.rep.add(S, "IFACE_OPEN", "INFO", kv_line("IFACE_OPEN", "INFO", {
                "policy": d.get("policy"), "file": Path(f).name, "payload_equal": d.get("payload_equal"),
                "payload_mismatch": d.get("payload_mismatch"), "wire_mismatch": d.get("wire_mismatch_vs_official"),
                "action_diff": ad if ad is not None else ("0(by_payload)" if d.get("payload_equal") else "n/a"),
                "exec_equal": ex.get("exec_equal")}), {"json": f})

    # ------------------------------------------------------------------ 5.1
    def _eval_parity(self, S: str, a: str, b: str, pol: str, which: str, pair: str | None = None, rec: bool = True) -> None:
        C = cmp_mod()
        keys = self.lay.keys(which)
        pair = pair or f"{a}:{b}"
        ok, have = self._ready([(a, pol), (b, pol)], keys)
        sa, sb = self.src.get(a, pol), self.src.get(b, pol)
        usable = sa and sb and sa.get("src") and sb.get("src")
        if not usable or (not ok and not self.partial):
            self.rep.pending(S, "EVAL_PARITY", {"pair": pair, "policy": pol, "have": have})
            return
        out = self.detail / f"eval-parity-{pair.replace(':', '-')}-{pol}.json"
        _, lines = call_cmd(C.cmd_eval_parity, a=sa["src"], b=sb["src"], pair=pair, policy=pol,
                            identities=str(self.lay.ident_path(which)),
                            rec_a=(sa.get("rec_roots") or [None])[0] if rec else None,
                            rec_b=(sb.get("rec_roots") or [None])[0] if rec else None, out=str(out))
        self.rep.lines(S, "EVAL_PARITY", [l + (" partial=yes" if not ok else "") for l in lines], {"json": str(out)})

    def sec_eval_conditions(self) -> None:
        S = "eval_conditions"
        small = self.lay.keys("small48")
        for pol in POLICIES:
            for a, b in EVAL_PAIRS:
                self._eval_parity(S, a, b, pol, "small48")
            # 同卡新旧接口闭环：a=R1（旧官方）、b=E1（新接口）；两边动作数组形状不同，不算首个动作分叉
            self._eval_parity(S, "R1", "E1", pol, "small48", rec=False)
            # A40 同卡型：官方重跑一 vs A40-乙首遍，限小样本 48
            self._eval_parity(S, "O1", "E5", pol, "small48", rec=False)
            for cond in E_CONDS:
                self._vs_e0(S, cond, pol, small, "EVAL_VS_E0")

    # ------------------------------------------------------------------ 5.2 / 第 6 步
    CANARY_CONDS = ("N", "N2", "N3", "K", "C")  # 顺序即「新旧」：C（金丝雀补跑）最后，同席位取最后一条真实金丝雀

    def _canary(self, S: str, pol: str) -> None:
        """金丝雀：每席位一局，取该席位最新的非 infra 记录；只有 infra 金丝雀的席位列为缺真实金丝雀，infra 金丝雀另行一行。
        K（杀 server 测试）的队列局不是正式结果，不进 N／PROD，只有它的金丝雀参与这里。"""
        real: dict[str, dict] = {}
        infra_c: list[dict] = []
        seats_all: set[str] = set()
        for code in self.CANARY_CONDS:
            src = self.src.get(code, pol) or {}
            for c in src.get("canary", []):
                real[str(c.get("seat"))] = dict(c, _cond=code)
            for c in src.get("canary_infra", []):
                infra_c.append(dict(c, _cond=code))
            seats_all |= {str(c.get("seat")) for c in src.get("canary", []) + src.get("canary_infra", [])}
        for code in ("N", "N2", "N3"):
            seats_all |= {str(r.get("seat")) for r in ((self.src.get(code, pol) or {}).get("table") or {}).values() if r.get("seat")}
        if not real and not infra_c:
            self.rep.pending(S, "CANARY", {"policy": pol, "reason": "无金丝雀记录"})
            return
        rows = []
        for seat, c in sorted(real.items()):
            k = rec_key(c)
            base = {code: (self.src.get(code, pol) or {"table": {}})["table"].get(k) for code in ("NP", "O1", "E0")}
            base["N"] = base.pop("NP")
            rows.append({"identity": f"{k[0]}/{k[1]}", "seat": seat, "cond": c["_cond"], "gpu": c.get("gpu_name"),
                         "status": c.get("status"), "steps": c.get("steps"),
                         **{f"{code}_status": (b or {}).get("status") for code, b in base.items()},
                         **{f"{code}_steps": (b or {}).get("steps") for code, b in base.items()},
                         "N_seat": (base["N"] or {}).get("seat")})
        missing = sorted(seats_all - set(real))
        path = self.detail / f"canary-{pol}.json"
        path.write_text(dumps({"real": rows, "infra": infra_c, "seats_missing_real": missing}, indent=1) + "\n", encoding="utf-8")

        def eq(code: str, field: str) -> str:
            have = [r for r in rows if r[f"{code}_{field}"] is not None]
            return f"{sum(r[field] == r[f'{code}_{field}'] for r in have)}/{len(have)}"

        self.rep.add(S, "CANARY", "INFO", kv_line("CANARY", "INFO", {
            "policy": pol, "n": len(rows), "seats": ",".join(r["seat"] for r in rows),
            "from": ",".join(f"{r['seat']}:{r['cond']}" for r in rows),
            "status_eq_N": eq("N", "status"), "steps_eq_N": eq("N", "steps"), "status_eq_O1": eq("O1", "status"),
            "status_eq_E0": eq("E0", "status"), "seats_missing_real": ",".join(missing) or "none"}), {"json": str(path)})
        if infra_c:
            self.rep.add(S, "CANARY_INFRA", "INFO", kv_line("CANARY_INFRA", "INFO", {
                "policy": pol, "n": len(infra_c),
                "items": ";".join(f"{c.get('seat')}:{c['_cond']}:{c.get('task')}/{c.get('seed')}:{c.get('infra_reason')}" for c in infra_c)}))

    def sec_killtest(self) -> None:
        """每策略一个席位故意杀一次 server 验证续跑（5.2）：从席位日志读判定。"""
        S = "killtest"
        logs = {"mme": ("new1", self.lay.nfs / "state" / "final7" / "logs" / "K-mme-s-new1.log", "K"),
                "smvla": ("new1", self.lay.nfs / "state" / "main" / "logs" / "N-smvla-s-new1.log", "N")}
        for pol, (seat, log, cond) in logs.items():
            if not log.exists():
                self.rep.pending(S, "KILLTEST", {"policy": pol, "seat": seat, "reason": "席位日志不存在"})
                continue
            f = parse_killtest(log.read_text(encoding="utf-8", errors="replace"))
            fields = {"policy": pol, "seat": seat, "cond": cond, "server_killed": f["killed"], "server_restarted": f["restarted"],
                      "requeued": f["requeued"], "done": f["done"], "errors": f["errors"], "seat_infra": f["infra"],
                      "queue_check": f["queue_check"], "log": log.name}
            if cond == "K":
                fields["done"] = f"{f['q_done']}/{f['q_total']}"
            self.rep.add(S, "KILLTEST", "INFO", kv_line("KILLTEST", "INFO", fields), {"log": str(log)})

    def _queue_lines(self, S: str, pol: str) -> None:
        """两个队列（prod 原队列、prod2 补跑队列）各一行 QUEUE_CLAIM；另报 infra 终态（事故毒化）个数。"""
        for qname in ("prod", "prod2", "prod3"):
            qdir = self.lay.nfs / "queue" / qname / pol
            if not (qdir / "order.json").exists():
                if qname == "prod":
                    self.rep.pending(S, "QUEUE_CLAIM", {"queue": qname, "policy": pol, "reason": "队列未建"})
                continue
            st = cq_mod().ClaimQueue(qdir).check()
            poisoned = 0
            for f in (qdir / "done").glob("*.json"):
                try:
                    poisoned += bool(json.loads(f.read_text(encoding="utf-8")).get("infra"))
                except (OSError, json.JSONDecodeError):
                    pass
            st["infra_terminal"] = poisoned
            line = cq_mod().check_line(st) + f" queue={qname} policy={pol} infra_terminal={poisoned}"
            if st["done"] < st["total"] and not self.final:
                self.rep.add(S, "QUEUE_CLAIM", "PENDING", "QUEUE_CLAIM=PENDING " + line.split(" ", 1)[1], st)
            else:
                self.rep.add(S, "QUEUE_CLAIM", "PASS" if st["dup"] == 0 and st["missing"] == 0 else "FAIL", line, st)

    def sec_prod(self) -> None:
        S = "prod"
        C = cmp_mod()
        full = self.lay.keys("full192")
        for pol in POLICIES:
            self._queue_lines(S, pol)
            np_ = self.src.get("NP", pol)
            if np_ is None:
                self.rep.pending(S, "PROD_MERGE", {"policy": pol, "reason": "N/N2 均无结果"})
            else:
                mg = np_["merge"]
                st = "INFO" if mg["conflicts"] == 0 else "FAIL"
                self.rep.add(S, "PROD_MERGE", st, kv_line("PROD_MERGE", st, {
                    "policy": pol, "from_N": mg["from_N"], "from_N2": mg["from_N2"], "from_N3": mg["from_N3"],
                    "poisoned_replaced": mg["poisoned_replaced"],
                    "still_missing": mg["still_missing"], "conflicts": mg["conflicts"],
                    "poisoned_unreplaced": len(mg["poisoned_unreplaced"])}), mg)
            # 正式跑法 vs 官方各参照
            ok, have = self._ready([("NP", pol), ("E0", pol), ("O1", pol), ("O2", pol)], full)
            have = have.replace("NP:", "N+N2:")
            srcs = {c: self.src.get(c, pol) for c in ("NP", "E0", "O1", "O2")}
            if not ok and not self.partial and not self.final:
                self.rep.pending(S, "PROD_VS_OFFICIAL", {"policy": pol, "have": have})
                self.rep.pending(S, "RELATIVE_ACCEPT", {"policy": pol, "have": have})
            elif not all(s and s.get("src") for s in srcs.values()):
                self.rep.add(S, "RELATIVE_ACCEPT", "BLOCKED" if self.final else "PENDING",
                             kv_line("RELATIVE_ACCEPT", "BLOCKED" if self.final else "PENDING",
                                     {"policy": pol, "have": have, "reason": "有源完全缺失"}))
            else:
                out = self.detail / f"prod-vs-official-{pol}.json"
                refs = [f"重跑一={srcs['O1']['src']}", f"历史={srcs['E0']['src']}", f"重跑二={srcs['O2']['src']}"]
                _, lines = call_cmd(C.cmd_prod_vs_official, prod=srcs["NP"]["src"], ref=refs, policy=pol,
                                    identities=str(self.lay.full192), out=str(out))
                tag = "" if ok else " partial=yes"
                self.rep.lines(S, "PROD_VS_OFFICIAL", [l + tag for l in lines if l.startswith("PROD_VS")], {"json": str(out)})
                out2 = self.detail / f"relative-accept-{pol}.json"
                rc, lines = call_cmd(C.cmd_relative_accept, e0=srcs["E0"]["src"], o1=srcs["O1"]["src"], o2=srcs["O2"]["src"],
                                     prod=srcs["NP"]["src"], identities=str(self.lay.full192), out=str(out2), policy=pol)
                ra_lines = [l for l in lines if l.startswith("RELATIVE_ACCEPT")]
                self.rep.lines(S, "RELATIVE_ACCEPT", [l + tag for l in ra_lines], {"json": str(out2)},
                               status="BLOCKED" if rc == 2 else "INFO")
                ra = json.loads(out2.read_text(encoding="utf-8"))["relative_accept"]
                trig = ra.get("extra_sample_trigger")
                self.rep.add(S, "EXTRA_SAMPLE", "INFO", kv_line("EXTRA_SAMPLE", "INFO", {
                    "policy": pol, "trigger": "n/a" if trig is None else trig,
                    "main_ci_half_width_pp": ra.get("main_ci_half_width_pp"),
                    "official_max_ci_half_width_pp": ra.get("official_max_ci_half_width_pp"),
                    "rule": "主比较CI半宽>2×官方3对最大半宽"}))
            # 金丝雀：不进 192 比较，单独与同身份正式局、官方重跑一、官方历史成绩比
            self._canary(S, pol)


    # ------------------------------------------------------------------ INFRA / 事故
    def sec_infra(self) -> None:
        """infra=True 的记录永不算策略结果；按条件／席位计数并给错误类型直方图。"""
        S = "infra"
        for code in ("O1", "O2", "R1", "S3") + E_CONDS + ("N", "N2", "N3"):
            for pol in POLICIES:
                s = self.src.get(code, pol)
                if not s:
                    continue
                by_seat: dict[str, list[dict]] = {}
                for r in s.get("infra", []):
                    by_seat.setdefault(r["seat"], []).append(r)
                if not by_seat:
                    self.rep.add(S, "INFRA", "INFO", kv_line("INFRA", "INFO", {"cond": code, "policy": pol, "seat": "all", "n": 0}))
                for seat, rs in sorted(by_seat.items()):
                    self.rep.add(S, "INFRA", "INFO", kv_line("INFRA", "INFO", {
                        "cond": code, "policy": pol, "seat": seat, "n": len(rs), "zero_step": sum(not r["steps"] for r in rs),
                        "incident": sum(r["incident"] for r in rs), "identities": len({(r["task"], r["seed"]) for r in rs}),
                        "sigs": histogram(r.get("sig", "none") for r in rs),
                        "hist": histogram(r["type"] for r in rs)}), rs)

    def sec_incident(self) -> None:
        """GPU 计算模式事故：*-vulkanfail-* 留档目录（不进比较）与队列里的 infra 终态（毒化）。"""
        S = "incident"
        dirs = self.lay.incident_dirs()
        for d in dirs:
            rows = [r for f in sorted(glob.glob(str(d / "**" / "results*.jsonl"), recursive=True)) for r in read_jsonl_tolerant(Path(f))[0]]
            inf = [r for r in rows if r.get("infra") or r.get("run_blocked")]
            parts = d.parts
            self.rep.add(S, "INCIDENT", "INFO", kv_line("INCIDENT", "INFO", {
                "dir": d.name, "cond": parts[-3], "policy": parts[-2], "records": len(rows), "real": len(rows) - len(inf),
                "infra": len(inf), "incident_0step": sum(is_incident_record(r) for r in inf),
                "hist": histogram(error_type(r) for r in inf), "compared": "excluded"}), {"path": str(d)})
        for pol in POLICIES:
            mg = (self.src.get("NP", pol) or {}).get("merge") or {}
            for qname in ("prod", "prod2", "prod3"):
                qdir = self.lay.nfs / "queue" / qname / pol / "done"
                poisoned = []
                for f in sorted(qdir.glob("*.json")):
                    try:
                        doc = json.loads(f.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if doc.get("infra"):
                        poisoned.append(doc)
                if not poisoned:
                    continue
                fields = {"queue": qname, "policy": pol, "infra_terminal": len(poisoned),
                          "seats": ",".join(sorted({str(d.get("seat")) for d in poisoned})),
                          "zero_step": sum(not d.get("steps") for d in poisoned),
                          "incident": sum(is_incident_record(d) for d in poisoned)}
                if qname == "prod":
                    fields.update(replaced=mg.get("poisoned_replaced"), unreplaced=len(mg.get("poisoned_unreplaced", [])))
                fields["hist"] = histogram(error_type(d) for d in poisoned)
                self.rep.add(S, "INCIDENT", "INFO", kv_line("INCIDENT", "INFO", fields))

    # ------------------------------------------------------------------ 测速
    def sec_speed(self) -> None:
        S = "speed"
        C = cmp_mod()
        for cell in ("C1", "C2", "C3", "C5", "C6", "C7"):
            d = self.lay.art / "env" / cell
            if not (d / "rows.jsonl").exists():
                self.rep.pending(S, "ENV_SPEED", {"cell": cell})
                continue
            rows = list(hr_mod()._env_rows(d).values())
            recs = [{"cell": cell, "timing": {**{k: v for k, v in (r.get("timing") or {}).items() if not isinstance(v, dict)},
                                              "wall_s": r.get("wall_s")}} for r in rows]
            summ = C.summarize_speed(recs, "cell").get(cell, {})
            self._speed_line(S, "ENV_SPEED", {"cell": cell, "rows": len(rows)}, summ, ENV_SPEED_KEYS)
        for code in ("S3",) + E_CONDS + ("N", "N2", "N3"):
            for pol in POLICIES:
                s = self.src.get(code, pol)
                if not s or not s["table"]:
                    continue
                recs = [dict(r, timing=r.get("timing") or {}) for r in s["table"].values()]
                for seat, summ in C.summarize_speed(recs, "seat").items():
                    self._speed_line(S, "EVAL_SPEED", {"cond": code, "policy": pol, "seat": seat,
                                                       "rows": sum(1 for r in recs if str(r.get("seat")) == seat)}, summ, EVAL_SPEED_KEYS)
        for code in ("E0", "O1", "O2", "R1"):
            for pol in POLICIES:
                s = self.src.get(code, pol)
                if not s or not s["table"]:
                    continue
                summ = C.summarize_speed(list(s["table"].values()), "none").get("all", {})
                self._speed_line(S, "EVAL_SPEED", {"cond": code, "policy": pol, "seat": "all", "rows": len(s["table"])}, summ, EVAL_SPEED_KEYS)

    def _speed_line(self, S: str, name: str, head: dict, summ: dict, keys: tuple) -> None:
        fields = dict(head)
        for k in keys:
            if k in summ:
                fields[f"{k}_p50"] = summ[k]["p50"]
                fields[f"{k}_p95"] = summ[k]["p95"]
        self.rep.add(S, name, "INFO", kv_line(name, "INFO", fields), {"all_fields": summ})

    # ------------------------------------------------------------------ 预算
    def sec_budget(self) -> None:
        S = "budget"
        rows = []

        def item(label: str, attempts: int, unique: int, est: str = "", incident: int = 0) -> None:
            """attempts = 轨迹尝试（环境建成的局）；incident = 0 步基础设施失败（环境未建成），按 §3.4 计入该项重试。"""
            cap, rcap = next((c, r) for l, c, r in BUDGET_CAPS if l == label)
            retries = max(0, attempts - unique) + incident
            rows.append({"item": label, "attempts": attempts, "unique": unique, "incident": incident, "retries": retries, "cap": cap,
                         "retry_cap": rcap if rcap is not None else f"共用{BUDGET_OTHER_RETRY_CAP}", "shared": rcap is None,
                         "est": est, "over": attempts > cap + (rcap or 0),
                         "retry_over": (retries > rcap) if rcap is not None else None})

        # 2.1：各格 rows.jsonl 全部行（含出错行）+ 开发期冒烟（估计）
        att = uniq = 0
        for cell in ("C1", "C2", "C3", "C5", "C6", "C7"):
            p = self.lay.art / "env" / cell / "rows.jsonl"
            if p.exists():
                rr, _ = read_jsonl_tolerant(p)
                att += len(rr)
                uniq += len({(r.get("task"), r.get("seed")) for r in rr})
        smoke = sum(len(read_jsonl_tolerant(Path(p))[0]) for p in glob.glob(str(self.lay.art / "dev-envdigest" / "**" / "rows.jsonl"), recursive=True))
        item("2.1 环境检测", att + smoke, uniq, f"含开发冒烟{smoke}行(估)" if smoke else "")
        nr = self.lay.nfs / "official" / "norec" / "smvla" / "episodes-shard00of01.jsonl"
        n_nr = len(read_jsonl_tolerant(nr)[0]) if nr.exists() else 0
        item("2.2 录制器验证", n_nr, min(n_nr, 1))

        def off_counts(codes: tuple) -> tuple[int, int, int]:
            a = u = inc = 0
            for code in codes:
                for pol in POLICIES:
                    s = self.src.get(code, pol)
                    if s:
                        a += s["stats"]["lines"] - s["stats"].get("incident", 0)
                        u += len(s["table"])
                        inc += s["stats"].get("incident", 0)
            return a, u, inc

        a, u, inc = off_counts(("O1", "O2"))
        item("2.3 官方重跑两遍", a, u, "按逐局文件行数;启动器内部整遍重评未落行的不计(估)", inc)
        a, u, inc = off_counts(("R1",))
        item("2.4 本机旧官方小样本", a, u, "同上(估)", inc)

        # 事故留档目录（不进比较）：真实局计入所属条目的轨迹尝试，infra 行计入该条目的重试
        dir_real: dict[str, int] = {}
        dir_infra: dict[str, int] = {}
        dir_incident = 0
        for d in self.lay.incident_dirs():
            cond = d.parts[-3]
            grp = "5.2" if cond.startswith("N") else ("3.1" if cond == "S3" else "5.1")
            for f in sorted(glob.glob(str(d / "**" / "results*.jsonl"), recursive=True)):
                for r in read_jsonl_tolerant(Path(f))[0]:
                    if r.get("infra") or r.get("run_blocked"):
                        dir_infra[grp] = dir_infra.get(grp, 0) + 1
                        dir_incident += is_incident_record(r)
                    elif not r.get("canary"):
                        dir_real[grp] = dir_real.get(grp, 0) + 1

        def new_counts(codes: tuple) -> tuple[int, int, int, int]:
            """轨迹尝试 = 去重后全部记录 − 金丝雀 − 0 步事故记录（环境没建成，不算轨迹尝试，计入重试）。"""
            a = u = c = inc = 0
            for code in codes:
                for pol in POLICIES:
                    s = self.src.get(code, pol)
                    if s:
                        a += (s["stats"]["attempts"] - s["stats"]["canary"] - s["stats"].get("canary_infra", 0)
                              - s["stats"].get("incident", 0))
                        u += len(s["table"])
                        c += s["stats"]["canary"]
                        inc += s["stats"].get("incident", 0)
            return a, u, c, inc

        a, u, _, inc = new_counts(("S3",))
        item("3.1 跑通", a + dir_real.get("3.1", 0), u, "中断未写结果的尝试不计(估)", inc + dir_infra.get("3.1", 0))
        a, u, _, inc = new_counts(E_CONDS)
        item("5.1 换条件评估", a + dir_real.get("5.1", 0), u,
             f"含事故留档目录真实局 {dir_real.get('5.1', 0)}、infra {dir_infra.get('5.1', 0)}", inc + dir_infra.get("5.1", 0))
        a, u, _, inc = new_counts(("N", "N2", "N3"))
        item("5.2 正式跑法", a + dir_real.get("5.2", 0), u, "含补跑队列 N2、N3", inc + dir_infra.get("5.2", 0))
        # 金丝雀：N／N2／N3／K／C 全部金丝雀局（含 infra 失败的）；去重单位 = (策略, 席位)
        c_all, c_seats = 0, set()
        for code in self.CANARY_CONDS:
            for pol in POLICIES:
                src = self.src.get(code, pol) or {}
                cs = src.get("canary", []) + src.get("canary_infra", [])
                c_all += len(cs)
                c_seats |= {(pol, str(c.get("seat"))) for c in cs}
        item("5.2 金丝雀", c_all, len(c_seats), "含 C 金丝雀补跑与 K 测试的金丝雀；重复席位计为重试")
        a, u, _, inc = new_counts(("K",))
        item("其他 杀server测试", a, u, "K：MME 杀 server 测试的队列局（不是正式结果）", inc)
        shared = sum(r["retries"] for r in rows if r["shared"])
        for r in rows:
            if r["shared"]:
                r["retry_over"] = shared > BUDGET_OTHER_RETRY_CAP
        total = sum(r["attempts"] for r in rows)
        inc_all = sum(r["incident"] for r in rows)
        rows.append({"item": "incident_infra_attempts", "attempts": 0, "unique": 0, "incident": inc_all, "retries": inc_all,
                     "cap": "n/a", "retry_cap": "见各项", "shared": False, "over": False, "retry_over": None,
                     "est": f"0 步、环境未建成（GPU 计算模式事故等），不计轨迹尝试、已计入各项重试；其中事故留档目录内 {dir_incident}"})
        for r in rows:
            self.rep.add(S, "BUDGET", "INFO", kv_line("BUDGET", "INFO", {
                "item": r["item"].replace(" ", "_"), "attempts": r["attempts"], "unique": r["unique"], "incident": r["incident"],
                "retries": r["retries"], "cap": r["cap"], "retry_cap": r["retry_cap"], "over": r["over"],
                "retry_over": "n/a" if r["retry_over"] is None else r["retry_over"], "est": r["est"] or "none"}))
        retry_over_items = [r["item"].replace(" ", "_") for r in rows if r["retry_over"]]
        self.rep.add(S, "BUDGET", "INFO", kv_line("BUDGET_TOTAL", "INFO", {
            "trajectory_attempts": total, "cap": BUDGET_TOTAL_CAP, "over": total > BUDGET_TOTAL_CAP,
            "incident_infra_attempts": inc_all, "all_attempts": total + inc_all,
            "attempts_over_items": ",".join(r["item"].replace(" ", "_") for r in rows if r["over"]) or "none",
            "retry_over_items": ",".join(retry_over_items) or "none", "shared_retries": shared,
            "shared_retry_cap": BUDGET_OTHER_RETRY_CAP}))
        self.extra["budget"] = rows

    # ------------------------------------------------------------------ 主流程
    SECTIONS = ("env_parity", "env_stack", "observer", "official", "step3", "replay", "eval_conditions", "prod", "killtest", "infra", "incident",
                "speed", "budget")

    def run(self, sections: tuple[str, ...] | None = None) -> dict:
        for sec in sections or self.SECTIONS:
            try:
                getattr(self, f"sec_{sec}")()
            except Exception as e:  # 一个部分出错不影响其余部分
                self.rep.add(sec, "SECTION_ERROR", "ERROR", f"SECTION_ERROR=FAIL section={sec} error={type(e).__name__}:{str(e)[:200]}",
                             {"traceback": traceback.format_exc()})
        return self.write()

    def write(self) -> dict:
        out = self.lay.out
        out.mkdir(parents=True, exist_ok=True)
        try:
            commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        except OSError:
            commit = ""
        counts: dict[str, int] = {}
        for e in self.rep.entries:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
        doc = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "git_commit": commit, "final": self.final, "partial": self.partial,
               "art": str(self.lay.art), "nfs": str(self.lay.nfs), "status_counts": counts, "entries": self.rep.entries,
               "budget": self.extra.get("budget"), "pending": [e["line"] for e in self.rep.entries if e["status"] == "PENDING"]}
        (out / "summary.json").write_text(dumps(doc, indent=1) + "\n", encoding="utf-8")
        (out / "verdicts.txt").write_text("".join(e["line"] + "\n" for e in self.rep.entries), encoding="utf-8")
        self.write_fragments(doc)
        print(f"STEP6_SUMMARY=INFO entries={len(self.rep.entries)} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
              + f" out={out / 'summary.json'}", flush=True)
        return doc

    def write_fragments(self, doc: dict) -> None:
        fdir = self.lay.out / "fragments"
        fdir.mkdir(parents=True, exist_ok=True)
        by_sec: dict[str, list[dict]] = {}
        for e in self.rep.entries:
            by_sec.setdefault(e["section"], []).append(e)
        for fname, secs in FRAGMENTS.items():
            parts = [f"<!-- 由 scripts/eval-official/step6_summary.py 自动生成于 {doc['generated']}（提交 {doc['git_commit'][:8]}）；"
                     f"重跑即覆盖，勿手改 -->", ""]
            for sec in secs:
                es = by_sec.get(sec, [])
                parts.append(f"### {SECTION_TITLES[sec]}")
                parts.append("")
                if not es:
                    parts += ["（本次未运行此部分）", ""]
                    continue
                n_pend = sum(e["status"] == "PENDING" for e in es)
                n_err = sum(e["status"] == "ERROR" for e in es)
                parts.append(f"判定行 {len(es)} 条，其中待定（输入未齐）{n_pend} 条" + (f"、汇总出错 {n_err} 条" if n_err else "") + "。")
                parts.append("")
                if sec == "budget" and doc.get("budget"):
                    parts += ["| 条目 | 轨迹尝试 | 去重身份 | 0 步事故 | 重试 | 上限 | 重试上限 | 尝试超限 | 重试超限 | 说明 |",
                              "|---|---:|---:|---:|---:|---:|---|---|---|---|"]
                    yn = lambda v: "—" if v is None else ("是" if v else "否")  # noqa: E731
                    for r in doc["budget"]:
                        parts.append(f"| {r['item']} | {r['attempts']} | {r['unique']} | {r['incident']} | {r['retries']} | {r['cap']} | "
                                     f"{r['retry_cap']} | {yn(r['over'])} | {yn(r['retry_over'])} | {r['est'] or '—'} |")
                    parts.append("")
                parts += ["```text"] + [e["line"] for e in es] + ["```", ""]
                details = sorted({(e.get("data") or {}).get("json") for e in es if isinstance(e.get("data"), dict) and (e["data"].get("json"))})
                if details:
                    parts.append("明细：" + "、".join(f"`{Path(d).relative_to(REPO) if str(d).startswith(str(REPO)) else d}`" for d in details))
                    parts.append("")
            (fdir / f"{fname}.md").write_text("\n".join(parts), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="v7.5eval 第 6 步汇总器（幂等，可随时重跑）")
    ap.add_argument("--art", default=str(DEFAULT_ART), help="artifacts/v7.5eval 根")
    ap.add_argument("--nfs", default=str(DEFAULT_NFS), help="NFS v75eval 根")
    ap.add_argument("--out", default=None, help="输出目录，默认 <art>/summary")
    ap.add_argument("--e0-mme", default=None, help="E0 MME 源（默认 compare.py 的 E0-mme）")
    ap.add_argument("--e0-smvla", default=None, help="E0 SMVLA 源（默认 compare.py 的 E0-smvla）")
    ap.add_argument("--sections", default=None, help="逗号分隔的部分名，默认全部：" + ",".join(Summary.SECTIONS))
    ap.add_argument("--final", action="store_true", help="第 6 步正式出结论：身份不全按运行阻塞输出")
    ap.add_argument("--partial", action="store_true", help="输入不全时在已有交集上算（开发期观察）")
    ap.add_argument("--no-decode", action="store_true", help="环境栈比较不解码视频（只比 sha）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    C = cmp_mod()
    art = Path(args.art)
    lay = Layout(art, Path(args.nfs), Path(args.out) if args.out else art / "summary",
                 {"mme": args.e0_mme or C.SOURCE_ALIASES["E0-mme"], "smvla": args.e0_smvla or C.SOURCE_ALIASES["E0-smvla"]})
    secs = tuple(s.strip() for s in args.sections.split(",")) if args.sections else None
    Summary(lay, final=args.final, partial=args.partial, decode=not args.no_decode).run(secs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
