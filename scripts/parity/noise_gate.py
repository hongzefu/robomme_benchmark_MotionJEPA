#!/usr/bin/env python3
"""噪声基线的比较器与回归闸门（1003 噪声基线计划第一部分第二、三、六节，第二部分 §一 ``noise_gate.py`` 行、§二 S2 行）。

纯 CPU；判定逻辑只用标准库与 h5py／numpy（统计量用纯 Python 精确计算，不依赖 scipy）。不复用 ``hard_parity.schema_of``／
``pair_metrics`` 做判定（计划审查意见 2、3：前者把帧号归一后取集合会漏掉单帧缺字段，后者只比少数字段且全同局不给分叉步）。
评估取数只读导入 ``scripts/eval-official/v8_report.py`` 的 ``load_policy``／``analyze_attempts``（按账本 ``accepted_attempt_id``）。

子命令（仓库根运行；每个都打印具名判定行，``*_BASELINE``／``GEN_PAIR`` 只出 INFO）::

    noise_gate.py gen-compare --ref <侧> --new <侧> --identities <G9 或 D0 清单> --out <jsonl>
    noise_gate.py eval-extract --format {v8,legacy} --root <运行根或结果 jsonl> --policy <p> --identities <清单> --out <jsonl>
    noise_gate.py run-fresh --extract <jsonl> --provenance <来源报告 json> --expect 192 [--other <jsonl> ...]
    noise_gate.py baseline-reset --compare <env-digest-compare json> --set {G9,D0}
    noise_gate.py baseline-gen --pairs <gen-compare jsonl>... --workers {4,1} --set {G9,D0}
    noise_gate.py baseline-eval --pairs <a.jsonl>:<b.jsonl>... --policy <p> --set {G9,D0}
    noise_gate.py freeze --spec <描述各组输入的 json> --out <noise-baseline.json>
    noise_gate.py verify --path <noise-baseline.json>
    noise_gate.py check-reset --baseline <json> --set <s> --compare <env-digest-compare json>
    noise_gate.py check-gen --baseline <json> --set <s> --workers <w> --pair <gen-compare jsonl>
    noise_gate.py check-eval --baseline <json> --set <s> --policy <p> --ref <基线参照遍 extract> --new <新一遍 extract>
    noise_gate.py selftest

「侧」（``gen-compare`` 的 ``--ref``／``--new``）可以是：
- 交付清单 json（``schema`` 以 ``v8-delivery`` 开头，读 ``rows`` 的 ``h5``／``h5_sha256``，交付行一律视为成功）；
- 生成输出根目录（``hard_parity.py generate`` 的 ``identities.jsonl``，``path`` 相对该目录；xhard0 的 H 侧与官方 O 侧
  bucket 目录同格式）；
- 只有 ``results.jsonl`` 的 ``generate_h5.py`` 输出根（行 ``{"kind": "result", "record": {...}}``）。
身份按 (task, seed) 对齐；``tier`` 为 ``xhard0`` 的身份接受侧行写成官方难度名 ``hard``。

逐帧结构的具体口径（对计划 3.1「逐帧键集合、dtype、shape 全同」的细化，见 ``compare_h5`` 注释）：真实 V9 二次生成里
``action/waypoint_action`` 每帧都在，但无待执行路点时录像器写 float32 的 NaN 占位、有路点时写 float64 实值，两种签名落在
哪些帧随轨迹而变（V9 新生成 7 个分叉局里有 3 局在分叉后出现这种差异）。所以只对「两侧文件里签名都随帧变化」的多态字段
放行分叉后的签名差异（按内容差异计，第 0 帧仍须全同）；其余字段两侧必须每帧签名恒定且相同，只在一侧随帧变化
（如某一帧缺字段）即结构不同。

``eval-extract --format v8`` 可重复给 ``--root``（G9 的正式评估那一遍：180 局在 V8 运行根、MoveCube 新规格 12 局在 V9
运行根），各根按自己的账本判后逐身份按规格指纹选根；``--allow-extra`` 放行运行根里的清单外身份（正式评估覆盖全集）。

``freeze --spec`` 的格式::

    {"conditions": {...固定条件，原样写进冻结文件...},
     "groups": [
       {"kind": "gen", "set": "G9", "workers": 4, "pairs": ["<gen-compare jsonl>", ...]},
       {"kind": "eval", "set": "G9", "policy": "mme", "pairs": [["<a extract>", "<b extract>"], ...],
        "reference": "<回归时作参照的那一遍 extract，须出现在 pairs 里>"},
       {"kind": "reset", "set": "G9", "compare": ["<env-digest-compare json>", ...],
        "reference_rows": "<冻结的九层摘要 rows.jsonl，可省>"}]}
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[2]
for _extra in (REPO / "src", REPO):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

V8_REPORT = REPO / "scripts" / "eval-official" / "v8_report.py"

BASELINE_SCHEMA = "noise-baseline/1"
GEN_SCHEMA = "noise-gen-compare/1"
EXTRACT_SCHEMA = "noise-eval-extract/1"

#: 生成五类（计划第一部分 3.1），互斥且完备
GEN_CLASSES = ("byte_equal", "diverge", "gen_fail", "structural", "unknown")
#: 求解器走完任务列表仍未成功的记录类型（计入「生成失败」）；其余失败类型一律「原因不明」
SOLVER_FAIL_TYPES = ("DatasetGenerationError", "PlannerExhausted")
#: 评估终态
TERMINAL = ("success", "fail", "timeout")
#: 说明发生在 reset 之前的基础设施原因（env_client：环境构建失败、录像器初始化失败，都在 0 步时记）
PRE_RESET_INFRA = ("env_build", "recorder")

#: 成功局数净损失上限：净损失（成功→失败 减 失败→成功）≤ 4，达到 5 即 FAIL。
#: 来自用户裁决 1「少 5 局」（2026-10-03，计划第一部分第七节）；G9 与 D0 各自按 192 局计。
NET_LOSS_MAX = 4
#: 线的公式常量（计划第一部分 3.4）
CP_ALPHA = 0.05          # 单侧 95% Clopper–Pearson 上界
LINE_QUANTILE = 0.99     # Binomial(n, p_U) 的 99% 分位数
BAND_FACTOR = 1.5        # 步数差均值、中位数的带 = 基线各对绝对值最大值 × 1.5
FORMULA = ("p_hat = sum(x_i)/(m*n)；p_U = 单侧 95% Clopper–Pearson 上界（N = m*n 次试验、sum(x_i) 次发生；x 全 0 时 "
           "p_U = 1 - 0.05^(1/N)，x = N 时 p_U = 1）；line = max(Binomial(n, p_U) 的 99% 分位数, max(x_i))；"
           "步数差均值／中位数带 = 各对绝对值最大值 × 1.5")
#: 生成组按个数算线的量
GEN_METRICS = ("diff", "gen_fail")
#: 评估组按个数算线的量
EVAL_METRICS = ("status_changed", "s2f", "f2s", "timeout_delta", "steps_diff")
EVAL_BANDS = ("steps_absdiff_mean", "steps_absdiff_median")


class GateError(RuntimeError):
    """输入不合契约、冻结文件不自洽等，拒跑。"""


# ── 通用小工具 ──────────────────────────────────────────────────────────────


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def payload_sha256(obj: dict[str, Any]) -> str:
    """剔掉顶层 ``sha256`` 键后 canonical JSON 的 sha256（与 ``gate_set.payload_sha256`` 同口径）。"""
    body = {k: v for k, v in obj.items() if k != "sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    out = []
    for text in Path(path).read_text(encoding="utf-8").splitlines():
        if text.strip():
            out.append(json.loads(text))
    return out


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    return path


def line_count(path: str | Path) -> int:
    return sum(1 for t in Path(path).read_text(encoding="utf-8").splitlines() if t.strip())


def id_str(task: str, tier: str, seed: int) -> str:
    return f"{task}|{tier}|{int(seed)}"


def tier_compatible(want: str, got: Any) -> bool:
    """身份档位与侧行档位是否相容：xhard0 接受官方难度名 hard；未写档位的侧行不判冲突。"""
    if got is None:
        return True
    got = str(got)
    return got == want or (want == "xhard0" and got == "hard")


# ── 身份清单 ────────────────────────────────────────────────────────────────


def load_identities(path: str | Path) -> list[dict[str, Any]]:
    """读 G9（``gate_set`` 冻结 json）、D0（``identities-full192.json`` 列表，缺 tier 记 xhard0）或 jsonl 身份清单。
    统一为 ``{id, task, tier, seed, spec_sha256?, source_episode?, candidate?}``；(task, seed) 重复即拒。"""
    path = Path(path)
    if path.suffix == ".jsonl":
        raw = read_jsonl(path)
    else:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and str(obj.get("schema", "")).startswith("gate-set"):
            from scripts.parity import gate_set

            raw = gate_set.load_gate_set(path)
        elif isinstance(obj, dict) and isinstance(obj.get("rows"), list):
            raw = obj["rows"]
        elif isinstance(obj, list):
            raw = obj
        else:
            raise GateError(f"{path}：认不出身份清单格式")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for row in raw:
        task, seed = str(row["task"]), int(row["seed"])
        tier = str(row.get("tier") or row.get("difficulty") or "xhard0")
        if (task, seed) in seen:
            raise GateError(f"{path}：身份重复 {task} seed={seed}")
        seen.add((task, seed))
        item = {"id": id_str(task, tier, seed), "task": task, "tier": tier, "seed": seed}
        for key in ("spec_sha256", "source_episode", "candidate", "builder_episode"):
            if row.get(key) is not None:
                item[key] = row[key]
        out.append(item)
    return out


# ── 生成：侧加载器 ──────────────────────────────────────────────────────────


def _side_entry(h5: Any, sha: Any, ok: bool, error_type: Any = None, error: Any = None, tier: Any = None,
                **extra: Any) -> dict[str, Any]:
    return {"h5": str(h5) if h5 else None, "sha256": sha, "status": "ok" if ok else "fail",
            "error_type": error_type, "error": error, "tier": tier, **extra}


def load_side(spec: str | Path) -> dict[tuple[str, int], dict[str, Any]]:
    """把交付清单／生成输出根／O-bucket 目录统一映射为 ``(task, seed) -> {h5, sha256, status, error_type, error, tier}``。
    同一身份出现多行（续跑重复）时记 ``duplicate=True``，比较时归「原因不明」。"""
    spec = Path(spec)
    out: dict[tuple[str, int], dict[str, Any]] = {}

    def put(key: tuple[str, int], entry: dict[str, Any]) -> None:
        if key in out:
            entry["duplicate"] = True
        out[key] = entry

    if spec.is_file():
        obj = json.loads(spec.read_text(encoding="utf-8"))
        if not (isinstance(obj, dict) and str(obj.get("schema", "")).startswith("v8-delivery")):
            raise GateError(f"{spec}：文件侧只认 v8-delivery 交付清单")
        for row in obj.get("rows", []):
            h5 = row.get("h5")
            if h5 and not Path(h5).is_absolute():
                h5 = str((spec.parent / h5).resolve())
            put((str(row["task"]), int(row["seed"])),
                _side_entry(h5, row.get("h5_sha256"), True, tier=row.get("tier"), source="delivery"))
        return out
    if not spec.is_dir():
        raise GateError(f"侧不存在：{spec}")
    identities = spec / "identities.jsonl"
    results = spec / "results.jsonl"
    if identities.is_file():
        for line in read_jsonl(identities):
            rel = line.get("path")
            ok = bool(line.get("success")) and not line.get("h5_error")
            error = line.get("h5_error") or line.get("error")
            put((str(line["task"]), int(line["seed"])),
                _side_entry(spec / rel if rel else None, line.get("sha256"), ok, line.get("error_type"), error,
                            tier=line.get("tier"), source="identities"))
        return out
    if results.is_file():
        for line in read_jsonl(results):
            rec = line.get("record", line)
            if line.get("kind") not in (None, "result"):
                continue
            h5 = rec.get("h5")
            put((str(rec["task"]), int(rec["seed"])),
                _side_entry(h5 if rec.get("ok") else None, rec.get("h5_sha256"), bool(rec.get("ok")),
                            rec.get("error_type"), rec.get("error"), tier=rec.get("tier"), source="results"))
        # results.jsonl 里同一身份的多轮记录（基础设施重试）按最后一行算，不当重复
        for entry in out.values():
            entry.pop("duplicate", None)
        return out
    raise GateError(f"{spec}：既无 identities.jsonl 也无 results.jsonl")


# ── 生成：h5 逐帧比较器 ─────────────────────────────────────────────────────


def _is_ts(name: str) -> bool:
    return name.startswith("timestep_") and name[len("timestep_"):].isdigit()


def _attrs(obj) -> dict[str, Any]:
    out = {}
    for k in sorted(obj.attrs.keys()):
        v = obj.attrs[k]
        out[k] = v.tolist() if hasattr(v, "tolist") else v
    return out


def _value_key(value: Any) -> Any:
    """数据集值的可比形态：数值数组按字节，字符串／对象按 tolist。"""
    import numpy as np

    arr = np.asarray(value)
    if arr.dtype.kind in "OSUV":
        return ("obj", repr(arr.tolist()))
    return ("bin", arr.dtype.str, arr.shape, arr.tobytes())


def _tree(group) -> tuple[dict[str, tuple[str, tuple]], dict[str, Any]]:
    """一个组下全部数据集 {相对路径: (dtype, shape)} 与全部组／数据集属性 {路径: attrs}。"""
    import h5py

    datasets: dict[str, tuple[str, tuple]] = {}
    attrs: dict[str, Any] = {"": _attrs(group)}

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            datasets[name] = (str(obj.dtype), tuple(obj.shape))
        a = _attrs(obj)
        if a:
            attrs[name] = a
    group.visititems(visit)
    return datasets, attrs


def _frames(episode) -> dict[int, str]:
    return {int(k[len("timestep_"):]): k for k in episode.keys() if _is_ts(k)}


def _max_abs(a: Any, b: Any) -> float:
    import numpy as np

    x, y = np.asarray(a), np.asarray(b)
    if x.shape != y.shape or x.dtype.kind not in "biuf" or y.dtype.kind not in "biuf" or x.size == 0:
        return 0.0
    return float(np.max(np.abs(x.astype(np.float64) - y.astype(np.float64))))


#: 参考量（只写报告、不参与判定）
REF_ACTION = ("action/joint_action",)
REF_STATE = ("obs/joint_state", "obs/gripper_state")
REF_IMAGE = ("obs/front_rgb", "obs/wrist_rgb")


def compare_h5(left: str | Path, right: str | Path) -> dict[str, Any]:
    """两份成功生成的 h5 内容比较（字节已知不同）。返回 ``{verdict, reason, first_divergence, ...参考量}``，
    verdict ∈ {diverge, structural, unknown}。规则见计划第一部分 3.1。"""
    import h5py

    out: dict[str, Any] = {"first_divergence": None, "action_max": 0.0, "state_max": 0.0, "image_max": 0.0,
                           "frames_ref": None, "frames_new": None, "frames_diff": None}
    try:
        with h5py.File(left, "r") as lf, h5py.File(right, "r") as rf:
            if _attrs(lf) != _attrs(rf):
                return {**out, "verdict": "structural", "reason": "file_attrs"}
            if sorted(lf.keys()) != sorted(rf.keys()):
                return {**out, "verdict": "structural", "reason": "top_keys",
                        "detail": [sorted(lf.keys()), sorted(rf.keys())]}
            tops = sorted(lf.keys())
            first: int | None = None
            for top in tops:
                le, re_ = lf[top], rf[top]
                if not isinstance(le, h5py.Group) or not isinstance(re_, h5py.Group):
                    if _value_key(le[()]) != _value_key(re_[()]):
                        return {**out, "verdict": "structural", "reason": f"top_dataset:{top}"}
                    continue
                # 非时间步内容：键集合、dtype、shape、值、属性全同
                if _attrs(le) != _attrs(re_):
                    return {**out, "verdict": "structural", "reason": f"{top}:attrs"}
                lnon = sorted(k for k in le.keys() if not _is_ts(k))
                rnon = sorted(k for k in re_.keys() if not _is_ts(k))
                if lnon != rnon:
                    return {**out, "verdict": "structural", "reason": f"{top}:non_timestep_keys",
                            "detail": [lnon, rnon]}
                for name in lnon:
                    lo, ro = le[name], re_[name]
                    if isinstance(lo, h5py.Group) != isinstance(ro, h5py.Group):
                        return {**out, "verdict": "structural", "reason": f"{top}/{name}:kind"}
                    if isinstance(lo, h5py.Group):
                        ld, la = _tree(lo)
                        rd, ra = _tree(ro)
                        if ld != rd or la != ra:
                            return {**out, "verdict": "structural", "reason": f"{top}/{name}:schema"}
                        for ds in ld:
                            if _value_key(lo[ds][()]) != _value_key(ro[ds][()]):
                                return {**out, "verdict": "structural", "reason": f"{top}/{name}/{ds}:value"}
                    else:
                        if (lo.dtype, lo.shape) != (ro.dtype, ro.shape) or _attrs(lo) != _attrs(ro) \
                                or _value_key(lo[()]) != _value_key(ro[()]):
                            return {**out, "verdict": "structural", "reason": f"{top}/{name}:value"}
                # 时间步：逐帧对应（不做帧号归一）
                lfr, rfr = _frames(le), _frames(re_)
                nl, nr = len(lfr), len(rfr)
                out.update(frames_ref=nl, frames_new=nr, frames_diff=abs(nl - nr))
                if sorted(lfr) != list(range(nl)) or sorted(rfr) != list(range(nr)):
                    return {**out, "verdict": "structural", "reason": f"{top}:frames_not_contiguous"}
                if nl == 0 or nr == 0:
                    return {**out, "verdict": "structural", "reason": f"{top}:no_frame0"}
                # 逐帧结构（第一遍只读元数据）。每个数据集在每帧的「签名」= 不存在，或 (dtype, shape)。
                # 「多态字段」= 在两侧文件里签名都随帧变化的数据集（实测 action/waypoint_action：无待执行路点时录像器写
                # float32 的 NaN 占位、有路点时写 float64 实值，两种签名的帧落在哪里随轨迹而变）；它在分叉后的签名差异按内容
                # 差异计（第 0 帧仍须全同）。其余字段两侧都必须每帧签名恒定且相同——只在一侧随帧变化（如某一帧缺字段）、
                # 或两侧恒定签名不同、或任一侧出现过另一侧从未出现的字段，一律结构不同。
                lsch = [_tree(le[lfr[i]]) for i in range(nl)]
                rsch = [_tree(re_[rfr[i]]) for i in range(nr)]
                lall = set().union(*(set(d) for d, _a in lsch))
                rall = set().union(*(set(d) for d, _a in rsch))
                if lall != rall:
                    return {**out, "verdict": "structural", "reason": f"{top}:dataset_universe",
                            "detail": sorted(lall ^ rall)[:10]}
                variable: set[str] = set()
                for key in sorted(lall):
                    lsig = [d.get(key) for d, _a in lsch]
                    rsig = [d.get(key) for d, _a in rsch]
                    lvar, rvar = len(set(lsig)) > 1, len(set(rsig)) > 1
                    if lvar and rvar:
                        variable.add(key)
                        continue
                    if lvar or rvar:
                        side, sig, other = ("ref", lsig, rsig[0]) if lvar else ("new", rsig, lsig[0])
                        frame = next(i for i, s in enumerate(sig) if s != other)
                        return {**out, "verdict": "structural", "reason": f"{top}:frame{frame}:schema_{side}",
                                "detail": [key, str(sig[frame]), str(other)]}
                    if lsig[0] != rsig[0]:
                        return {**out, "verdict": "structural", "reason": f"{top}:signature",
                                "detail": [key, str(lsig[0]), str(rsig[0])]}
                out["variable_keys"] = sorted(variable)
                common = min(nl, nr)
                local_first: int | None = None
                out["variable_signature_frames"] = 0
                for i in range(common):
                    lg, rg = le[lfr[i]], re_[rfr[i]]
                    ld, la = lsch[i]
                    rd, ra = rsch[i]
                    shared = {k for k in set(ld) & set(rd) if ld[k] == rd[k]}
                    sig_diff = sorted(k for k in set(ld) | set(rd) if ld.get(k) != rd.get(k))
                    if sig_diff:
                        if i == 0:
                            return {**out, "verdict": "structural", "reason": f"{top}:frame0:schema",
                                    "detail": sig_diff[:10]}
                        out["variable_signature_frames"] += 1  # 只可能是多态字段（其余字段上面已判恒定且相同）
                    if local_first is None:
                        same = not sig_diff and la == ra and all(
                            _value_key(lg[ds][()]) == _value_key(rg[ds][()]) for ds in ld)
                        if not same:
                            if i == 0:
                                return {**out, "verdict": "structural", "reason": f"{top}:frame0_content"}
                            local_first = i
                    # 参考量：只算公共帧
                    for ds in REF_ACTION:
                        if ds in shared:
                            out["action_max"] = max(out["action_max"], _max_abs(lg[ds][()], rg[ds][()]))
                    for ds in REF_STATE:
                        if ds in shared:
                            out["state_max"] = max(out["state_max"], _max_abs(lg[ds][()], rg[ds][()]))
                    if local_first is not None:
                        for ds in REF_IMAGE:
                            if ds in shared:
                                out["image_max"] = max(out["image_max"], _max_abs(lg[ds][()], rg[ds][()]))
                if local_first is None and nl != nr:
                    local_first = common  # 公共帧全同、只差帧数：分叉在第一个多出来的帧
                if local_first is not None:
                    first = local_first if first is None else min(first, local_first)
            if first is None:
                return {**out, "verdict": "unknown", "reason": "content_equal_bytes_differ"}
            out["first_divergence"] = first
            return {**out, "verdict": "diverge", "reason": None}
    except Exception as exc:  # noqa: BLE001 打不开或读错一律原因不明
        return {**out, "verdict": "unknown", "reason": f"open_error:{type(exc).__name__}: {exc}"[:300]}


def classify_pair(ident: dict[str, Any], ref: dict[str, Any] | None, new: dict[str, Any] | None,
                  *, rehash: bool = True) -> dict[str, Any]:
    """一局归入互斥五类之一（计划第一部分 3.1），返回逐局报告行。"""
    row: dict[str, Any] = {"kind": "pair", "id": ident["id"], "task": ident["task"], "tier": ident["tier"],
                           "seed": ident["seed"], "class": None, "reason": None, "fail_side": None,
                           "first_divergence": None, "action_max": None, "state_max": None, "image_max": None,
                           "frames_ref": None, "frames_new": None, "frames_diff": None,
                           "ref_h5": ref.get("h5") if ref else None, "new_h5": new.get("h5") if new else None,
                           "ref_sha256": None, "new_sha256": None}

    def done(cls: str, reason: str | None = None, **kw: Any) -> dict[str, Any]:
        row.update(kw)
        row["class"], row["reason"] = cls, reason
        return row

    if ref is None or new is None:
        return done("unknown", f"missing_{'ref' if ref is None else 'new'}")
    for side, entry in (("ref", ref), ("new", new)):
        if entry.get("duplicate"):
            return done("unknown", f"duplicate_{side}")
        if not tier_compatible(ident["tier"], entry.get("tier")):
            return done("unknown", f"tier_mismatch_{side}:{entry.get('tier')}")
    fails = {side for side, entry in (("ref", ref), ("new", new)) if entry["status"] != "ok"}
    if fails:
        bad = [side for side in sorted(fails)
               if (ref if side == "ref" else new).get("error_type") not in SOLVER_FAIL_TYPES]
        if bad:
            entry = ref if bad[0] == "ref" else new
            return done("unknown", f"infra_{bad[0]}:{entry.get('error_type')}:{str(entry.get('error'))[:120]}")
        side = "both" if len(fails) == 2 else next(iter(fails))
        return done("gen_fail", (ref if side == "ref" else new).get("error_type"), fail_side=side)
    for side, entry in (("ref", ref), ("new", new)):
        if not entry.get("h5") or not Path(entry["h5"]).is_file():
            return done("unknown", f"missing_file_{side}")
    shas = {}
    for side, entry in (("ref", ref), ("new", new)):
        recorded = entry.get("sha256")
        if rehash or not recorded:
            actual = sha256_file(entry["h5"])
            if recorded and recorded != actual:
                return done("unknown", f"sha_recorded_mismatch_{side}", **{f"{side}_sha256": actual})
            shas[side] = actual
        else:
            shas[side] = recorded
    row["ref_sha256"], row["new_sha256"] = shas["ref"], shas["new"]
    if shas["ref"] == shas["new"]:
        return done("byte_equal")
    got = compare_h5(ref["h5"], new["h5"])
    extra = {k: got.get(k) for k in ("first_divergence", "action_max", "state_max", "image_max", "frames_ref", "variable_signature_frames", "variable_keys",
                                     "frames_new", "frames_diff")}
    if got.get("detail") is not None:
        extra["detail"] = got["detail"]
    return done(got["verdict"], got.get("reason"), **extra)


def gen_compare(ref_spec: str | Path, new_spec: str | Path, identities: list[dict[str, Any]],
                *, rehash: bool = True) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ref, new = load_side(ref_spec), load_side(new_spec)
    rows = [classify_pair(i, ref.get((i["task"], i["seed"])), new.get((i["task"], i["seed"])), rehash=rehash)
            for i in identities]
    counts = {c: sum(r["class"] == c for r in rows) for c in GEN_CLASSES}
    return rows, counts


def read_gen_pairs(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = read_jsonl(path)
    meta = next((r for r in lines if r.get("kind") == "meta"), None)
    if meta is None or meta.get("schema") != GEN_SCHEMA:
        raise GateError(f"{path}：不是 gen-compare 输出（缺 meta 或 schema 不符）")
    rows = [r for r in lines if r.get("kind") == "pair"]
    for r in rows:
        if r.get("class") not in GEN_CLASSES:
            raise GateError(f"{path}：{r.get('id')} 类别非法 {r.get('class')}")
    if len({r["id"] for r in rows}) != len(rows):
        raise GateError(f"{path}：身份重复")
    return meta, rows


def gen_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {c: sum(r["class"] == c for r in rows) for c in GEN_CLASSES}
    counts["diff"] = counts["diverge"] + counts["gen_fail"]
    counts["n"] = len(rows)
    return counts


# ── 评估：按权威尝试取结果 ──────────────────────────────────────────────────


def _v8_report():
    spec = importlib.util.spec_from_file_location("noise_gate_v8_report", V8_REPORT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _extract_row(ident: dict[str, Any], **kw: Any) -> dict[str, Any]:
    row = {"kind": "row", "id": ident["id"], "task": ident["task"], "tier": ident["tier"], "seed": ident["seed"],
           "spec_sha256": ident.get("spec_sha256"), "source_episode": ident.get("source_episode"),
           "status": None, "exec_steps": None, "attempt_id": None, "started_at": None,
           "retried_after_steps": False, "missing": False, "conflict": None, "flags": []}
    row.update(kw)
    return row


def _extract_v8_root(v8, root: str | Path, policy: str, identities: list[dict[str, Any]]
                     ) -> tuple[list[dict], dict, set[str]]:
    """单个运行根的账本口径取数；返回 (逐身份行, meta, 该根全部被接受的键)。"""
    state = v8.load_policy(Path(root), policy)
    ana = v8.analyze_attempts(state)
    ledger = state["ledger"]
    start_t: dict[str, float] = {}
    started: dict[str, set[str]] = defaultdict(set)
    ended: dict[str, dict] = {}
    accept_lines: Counter = Counter()
    for lr in ledger:
        kind, aid, key = lr.get("kind"), lr.get("attempt_id"), str(lr.get("key"))
        if kind == "attempt_start" and aid:
            start_t.setdefault(str(aid), lr.get("t"))
            started[key].add(str(aid))
        elif kind == "attempt_end" and aid:
            ended[str(aid)] = lr
        elif kind == "accept":
            accept_lines[key] += 1
    rows_by_key: dict[str, list[dict]] = defaultdict(list)
    for r in ana["rows"]:
        rows_by_key[v8.key_of(r)].append(r)
    conflicts = {c["key"]: c for c in ana["conflicts"]}
    no_row = {a["key"]: a for a in ana["accept_no_row"]}
    out: list[dict[str, Any]] = []
    want_keys = set()
    for ident in identities:
        key = f"{ident['task']}_{ident['tier']}_{ident['seed']}"
        want_keys.add(key)
        flags: list[str] = []
        acc = ana["accepted"].get(key)
        conflict = None
        if key in conflicts:
            conflict = conflicts[key]["reason"]
        elif key in no_row:
            conflict = "accept_no_row"
        elif accept_lines[key] > 1:
            conflict = "duplicate_accept"
        if acc is not None and conflict is None:
            for field in ("task", "tier"):
                if str(acc.get(field)) != str(ident[field]):
                    conflict = f"{field}_mismatch"
            if int(acc.get("seed", -1)) != ident["seed"]:
                conflict = "seed_mismatch"
            if ident.get("spec_sha256") and acc.get("spec_sha256") != ident["spec_sha256"]:
                conflict = "spec_sha256_mismatch"
        accepted_id = str(acc["attempt_id"]) if acc is not None else None
        # 步后重试：任何未被接受、且执行过步数（或步数不明且不在 reset 之前）的尝试
        retried = False
        attempts = {str(r.get("attempt_id")) for r in rows_by_key.get(key, []) if r.get("attempt_id")}
        attempts |= started.get(key, set())
        attempts |= {aid for aid, lr in ended.items() if str(lr.get("key")) == key}
        for aid in sorted(attempts - {accepted_id}):
            rlist = [r for r in rows_by_key.get(key, []) if str(r.get("attempt_id")) == aid]
            src = rlist[-1] if rlist else ended.get(aid)
            if src is None:
                flags.append(f"orphan_attempt:{aid}")
                retried = True
                continue
            steps = src.get("exec_steps")
            reason = src.get("infra_reason")
            if steps is None:
                if reason not in PRE_RESET_INFRA:
                    retried = True
                    flags.append(f"retry_after_unknown_steps:{aid}:{reason}")
            elif int(steps) > 0:
                retried = True
                flags.append(f"retry_after_steps:{aid}:{steps}")
        for r in ana["late"]:
            if v8.key_of(r) == key:
                flags.append(f"late:{r.get('attempt_id')}:{r.get('status')}")
        kw: dict[str, Any] = {"retried_after_steps": retried, "conflict": conflict, "flags": flags}
        if acc is None or conflict is not None:
            kw["missing"] = acc is None and conflict is None
        else:
            kw.update(status=acc.get("status"), exec_steps=acc.get("exec_steps"), attempt_id=accepted_id,
                      started_at=start_t.get(accepted_id))
        out.append(_extract_row(ident, **kw))
    meta = {"duplicate": ana["duplicate"], "late": len(ana["late"]), "abandoned": len(ana["abandoned"])}
    return out, meta, set(ana["accepted"])


def extract_v8(root: str | Path | list, policy: str, identities: list[dict[str, Any]]) -> tuple[list[dict], dict]:
    """V8 账本口径：权威行 = ``analyze_attempts`` 的 ``accepted``；键四元组 (task, tier, seed, spec_sha256)。

    ``root`` 可给多个运行根（如 G9 的正式评估那一遍：180 局在 V8 运行根、MoveCube 新规格 12 局在 V9 运行根）。
    各根分别按自己的账本判，再逐身份合并：规格指纹不符的根只记 ``ignored_root`` 标记、不参与；剩下恰好一个根有
    有效权威行就取它；两个以上根都有 → 冲突 ``multiple_roots``；任一根有其他冲突照传；都没有 → 缺失（若有根因规格不符
    被忽略，则记冲突 ``spec_sha256_mismatch``）。"""
    v8 = _v8_report()
    roots = root if isinstance(root, (list, tuple)) else [root]
    per_root = [_extract_v8_root(v8, one, policy, identities) for one in roots]
    want_keys = {f"{i['task']}_{i['tier']}_{i['seed']}" for i in identities}
    out: list[dict[str, Any]] = []
    for n, ident in enumerate(identities):
        cands = [(k, rows[n]) for k, (rows, _m, _a) in enumerate(per_root)]
        flags: list[str] = []
        valid, other_conflict, spec_ignored = [], None, False
        for k, row in cands:
            tag = f"r{k}:" if len(roots) > 1 else ""
            flags += [tag + f for f in row["flags"]]
            if row["conflict"] == "spec_sha256_mismatch" and len(roots) > 1:
                spec_ignored = True
                flags.append(f"ignored_root:r{k}:spec_sha256_mismatch")
            elif row["conflict"] is not None:
                other_conflict = other_conflict or row["conflict"]
            elif not row["missing"]:
                valid.append(row)
        if other_conflict is not None:
            out.append(_extract_row(ident, conflict=other_conflict, flags=flags,
                                    retried_after_steps=any(r["retried_after_steps"] for _k, r in cands)))
        elif len(valid) > 1:
            out.append(_extract_row(ident, conflict="multiple_roots", flags=flags,
                                    retried_after_steps=any(r["retried_after_steps"] for r in valid)))
        elif len(valid) == 1:
            row = dict(valid[0])
            row["flags"] = flags
            out.append(row)
        elif spec_ignored or (len(roots) == 1 and cands[0][1]["conflict"] == "spec_sha256_mismatch"):
            out.append(_extract_row(ident, conflict="spec_sha256_mismatch", flags=flags,
                                    retried_after_steps=any(r["retried_after_steps"] for _k, r in cands)))
        else:
            out.append(_extract_row(ident, missing=True, flags=flags,
                                    retried_after_steps=any(r["retried_after_steps"] for _k, r in cands)))
    accepted_all = set().union(*(a for _r, _m, a in per_root))
    extra = sorted(accepted_all - want_keys)
    meta = {"extra": len(extra), "extra_keys": extra[:20],
            "duplicate": sum(m["duplicate"] for _r, m, _a in per_root),
            "late": sum(m["late"] for _r, m, _a in per_root),
            "abandoned": sum(m["abandoned"] for _r, m, _a in per_root), "run_blocked": 0, "rec_checked": None}
    return out, meta


def _rec_name(path: Any) -> str | None:
    return Path(str(path)).name if path else None


def extract_legacy(root: str | Path, policy: str, identities: list[dict[str, Any]]) -> tuple[list[dict], dict]:
    """旧路线（D0，``run_seat.sh`` 不带 ``--v8``）严格口径，无账本：
    每身份恰好 1 条非 canary、非 infra、非 run_blocked 行；允许的前置重试只有 ``steps == 0`` 的 infra 行；
    ``steps`` 为 None 或 > 0 的 infra 行 → retried_after_steps；任何 run_blocked 行 → 整遍无效；
    ``rec/`` 下没有对应结果行的 ``<key>``／``<key>.aN`` 目录 → orphan_attempt（视同 retried_after_steps）。
    ``--root`` 给目录时读 ``<root>/<policy>/results.jsonl``，录像目录 ``<root>/<policy>/rec``；给 jsonl 文件时只读该文件、
    不核录像目录（meta ``rec_checked=false``）。"""
    root = Path(root)
    if root.is_file():
        results, rec_root = root, None
    else:
        results = root / policy / "results.jsonl"
        rec_root = root / policy / "rec"
        if not results.is_file():
            raise GateError(f"旧路线结果不存在：{results}")
    rows = [r for r in read_jsonl(results) if r.get("policy") in (None, policy)]
    run_blocked = sum(bool(r.get("run_blocked")) for r in rows)
    by_ident: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("canary"):
            continue
        by_ident[(str(r["task"]), int(r["seed"]))].append(r)
    rec_names: set[str] = set()
    for r in rows:
        name = _rec_name(r.get("rec_dir"))
        if name:
            rec_names.add(name)
    orphans: dict[tuple[str, int], list[str]] = defaultdict(list)
    if rec_root is not None and rec_root.is_dir():
        for d in sorted(rec_root.iterdir()):
            if not d.is_dir() or ".canary" in d.name or d.name in rec_names:
                continue
            base = d.name.split(".a")[0]
            task, _, seed = base.rpartition("_")
            if task and seed.isdigit():
                orphans[(task, int(seed))].append(d.name)
    out: list[dict[str, Any]] = []
    want = set()
    for ident in identities:
        key = (ident["task"], ident["seed"])
        want.add(key)
        flags: list[str] = []
        lst = by_ident.get(key, [])
        finals = [r for r in lst if not r.get("infra") and not r.get("run_blocked")]
        infra = [r for r in lst if r.get("infra")]
        retried = False
        for r in infra:
            steps = r.get("steps")
            if steps is None or int(steps) > 0:
                retried = True
                flags.append(f"infra_after_steps:a{r.get('attempt')}:{r.get('infra_reason')}:{steps}")
        for name in orphans.get(key, []):
            retried = True
            flags.append(f"orphan_attempt:{name}")
        conflict = None
        if len(finals) > 1:
            conflict = "multiple_final_rows"
        elif finals and ident.get("source_episode") is not None and finals[0].get("source_episode") is not None \
                and int(finals[0]["source_episode"]) != int(ident["source_episode"]):
            conflict = "source_episode_mismatch"
        elif finals and not tier_compatible(ident["tier"], (finals[0].get("identity") or {}).get("tier")):
            conflict = "tier_mismatch"
        kw: dict[str, Any] = {"retried_after_steps": retried, "conflict": conflict, "flags": flags}
        if len(finals) == 1 and conflict is None:
            fr = finals[0]
            kw.update(status=fr.get("status"), exec_steps=fr.get("steps"),
                      attempt_id=f"{_rec_name(fr.get('rec_dir')) or ''}#a{fr.get('attempt')}", started_at=None)
        else:
            kw["missing"] = not finals
        out.append(_extract_row(ident, **kw))
    extra = sorted(f"{t}_{s}" for t, s in set(by_ident) - want)
    meta = {"extra": len(extra), "extra_keys": extra[:20], "duplicate": 0, "late": 0, "abandoned": 0,
            "run_blocked": run_blocked, "rec_checked": rec_root is not None and rec_root.is_dir()}
    return out, meta


def extract_summary(rows: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, int]:
    return {"n": len(rows), "missing": sum(r["missing"] for r in rows),
            "conflicts": sum(r["conflict"] is not None for r in rows),
            "retried_after_steps": sum(bool(r["retried_after_steps"]) for r in rows),
            "error_final": sum(r["status"] == "error" for r in rows),
            "extra": meta.get("extra", 0), "run_blocked": meta.get("run_blocked", 0)}


def eval_extract(fmt: str, root: str | Path, policy: str, identities: list[dict[str, Any]], *,
                 allow_extra: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any], bool, str]:
    """``allow_extra``：运行根里有清单外的身份时不判 FAIL（并入 V8／V9 正式评估那一遍时用，正式评估覆盖全集）。"""
    roots = root if isinstance(root, (list, tuple)) else [root]
    if fmt == "v8":
        rows, meta = extract_v8(roots, policy, identities)
    elif fmt == "legacy":
        if len(roots) != 1:
            raise GateError("legacy 只接受一个 --root")
        rows, meta = extract_legacy(roots[0], policy, identities)
    else:
        raise GateError(f"未知格式 {fmt}")
    s = extract_summary(rows, meta)
    ok = s["missing"] == 0 and s["conflicts"] == 0 and (s["extra"] == 0 or allow_extra) and s["run_blocked"] == 0
    line = (f"EVAL_EXTRACT={'PASS' if ok else 'FAIL'} format={fmt} policy={policy} n={s['n']} missing={s['missing']} "
            f"conflicts={s['conflicts']} retried_after_steps={s['retried_after_steps']} "
            f"error_final={s['error_final']} extra={s['extra']} run_blocked={s['run_blocked']}")
    full_meta = {"kind": "meta", "schema": EXTRACT_SCHEMA, "format": fmt, "policy": policy, "allow_extra": allow_extra,
                 "root": str(Path(roots[0]).resolve()), "roots": [str(Path(r).resolve()) for r in roots],
                 **meta, "summary": s}
    return rows, full_meta, ok, line


def read_extract(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = read_jsonl(path)
    meta = next((r for r in lines if r.get("kind") == "meta"), None)
    if meta is None or meta.get("schema") != EXTRACT_SCHEMA:
        raise GateError(f"{path}：不是 eval-extract 输出")
    rows = [r for r in lines if r.get("kind") == "row"]
    if len({r["id"] for r in rows}) != len(rows):
        raise GateError(f"{path}：身份重复")
    return meta, rows


# ── 新跑核验 ────────────────────────────────────────────────────────────────


def _root_was_empty(state: Any) -> bool:
    """来源报告 ``out_root_state``：起跑前输出根不存在或为空。接受字符串（empty／absent／missing／nonexistent）
    或字典（``empty=True``、``exists=False``、``entries``／``n_entries`` 为 0 任一）。"""
    if isinstance(state, str):
        return state.lower() in ("empty", "absent", "missing", "nonexistent", "not_exist", "not_exists")
    if isinstance(state, dict):
        if state.get("empty") is True or state.get("exists") is False:
            return True
        for key in ("entries", "n_entries"):
            if key in state and int(state[key]) == 0:
                return True
    return False


def _related(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def run_fresh(extract: tuple[dict, list[dict]], prov: dict[str, Any], expect: int,
              others: list[tuple[dict, list[dict]]]) -> tuple[bool, str, list[str]]:
    meta, rows = extract
    s = meta.get("summary") or extract_summary(rows, meta)
    reasons: list[str] = []
    fmt = meta.get("format")
    if len(rows) != expect:
        reasons.append(f"rows={len(rows)}!={expect}")
    for key in ("missing", "conflicts", "extra", "run_blocked"):
        if s.get(key) and not (key == "extra" and meta.get("allow_extra")):
            reasons.append(f"{key}={s[key]}")
    retried = sum(bool(r["retried_after_steps"]) for r in rows)
    if retried:
        reasons.append(f"retried_after_steps={retried}")
    roots = [Path(r) for r in (meta.get("roots") or [meta["root"]])]
    if prov.get("out_root") and not all(_related(r, Path(prov["out_root"])) for r in roots):
        reasons.append("root_not_under_provenance_out_root")
    mine = {str(r.resolve()) for r in roots}
    for om, _orows in others:
        theirs = {str(Path(r).resolve()) for r in (om.get("roots") or [om["root"]])}
        if mine & theirs:
            reasons.append(f"root_reused:{sorted(mine & theirs)[0]}")
    fresh = 0
    if fmt == "v8":
        t0 = prov.get("started_at")
        if t0 is None:
            reasons.append("provenance_no_started_at")
        other_ids = {r.get("attempt_id") for _om, orows in others for r in orows if r.get("attempt_id")}
        reused = 0
        for r in rows:
            ok = r.get("attempt_id") and r.get("started_at") is not None and t0 is not None \
                and float(r["started_at"]) > float(t0)
            if r.get("attempt_id") in other_ids:
                reused += 1
                ok = False
            fresh += bool(ok)
        if reused:
            reasons.append(f"attempt_id_reused={reused}")
        if "out_root_state" in prov and not _root_was_empty(prov["out_root_state"]):
            reasons.append("out_root_not_empty_at_start")
        ledger_new = fresh == len(rows) and len(rows) > 0
    elif fmt == "legacy":
        empty = _root_was_empty(prov.get("out_root_state"))
        if not empty:
            reasons.append("out_root_not_empty_at_start")
        if meta.get("rec_checked") is not True:
            reasons.append("rec_not_checked")
        ledger_new = empty
        fresh = sum(1 for r in rows if empty and not r["missing"] and r["conflict"] is None
                    and not r["retried_after_steps"])
    else:
        reasons.append(f"unknown_format:{fmt}")
        ledger_new = False
    if fresh != expect:
        reasons.append(f"fresh={fresh}/{expect}")
    assets = "PASS" if prov.get("assets_sha") else "FAIL"
    if assets != "PASS":
        reasons.append("assets_sha_absent")
    fp = str(prov.get("fingerprint") or "")[:12] or "-"
    ok = not reasons
    line = (f"RUN_FRESH={'PASS' if ok else 'FAIL'} pass={prov.get('pass')} fresh={fresh}/{expect} "
            f"ledger_new={'yes' if ledger_new else 'no'} assets={assets} fingerprint={fp} "
            f"retried_after_steps={retried}")
    return ok, line, reasons


# ── 统计量（纯 Python 精确计算）────────────────────────────────────────────


def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return math.log(math.comb(n, k)) + k * math.log(p) + (n - k) * math.log1p(-p)


def binom_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    logs = [_log_pmf(i, n, p) for i in range(k + 1)]
    top = max(logs)
    if top == -math.inf:
        return 0.0
    return min(1.0, math.exp(top) * math.fsum(math.exp(v - top) for v in logs))


def cp_upper(x: int, n: int, alpha: float = CP_ALPHA) -> float:
    """单侧 (1-alpha) Clopper–Pearson 上界：满足 P(X ≤ x | n, p) = alpha 的 p；x=0 用闭式，x=n 为 1。"""
    if n <= 0:
        raise GateError("cp_upper：n 须 > 0")
    if x >= n:
        return 1.0
    if x == 0:
        return 1.0 - alpha ** (1.0 / n)
    lo, hi = x / n, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if binom_cdf(x, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def binom_quantile(q: float, n: int, p: float) -> int:
    """Binomial(n, p) 的 q 分位数：最小的 k 使 CDF(k) ≥ q（相对容差 1e-12 吸收浮点误差）。"""
    for k in range(n + 1):
        if binom_cdf(k, n, p) >= q - 1e-12:
            return k
    return n


def mcnemar_p(b: int, c: int) -> float:
    """精确 McNemar（双侧二项检验，Bin(b+c, 0.5)），只报告。"""
    m = b + c
    if m == 0:
        return 1.0
    k = min(b, c)
    tail = math.fsum(math.comb(m, i) for i in range(k + 1)) / (2 ** m)
    return min(1.0, 2 * tail)


def noise_line(xs: list[int], n: int) -> dict[str, Any]:
    """计划第一部分 3.4：合并比例、单侧 95% CP 上界、99% 分位数线（不小于观测最大值）。"""
    if not xs:
        raise GateError("noise_line：没有基线对")
    m = len(xs)
    total = sum(xs)
    p_hat = total / (m * n)
    p_u = cp_upper(total, m * n)
    q = binom_quantile(LINE_QUANTILE, n, p_u)
    return {"x": list(xs), "m": m, "n": n, "p_hat": p_hat, "p_upper": p_u, "quantile_line": q,
            "max_x": max(xs), "line": max(q, max(xs))}


# ── 评估：两遍比较 ──────────────────────────────────────────────────────────


def eval_pair_metrics(a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """两遍按身份对齐：终态变化（含 fail↔timeout）、成功→失败、失败→成功、净损失、超时局数变化、步数不同局数与
    逐局步数绝对差的均值／中位数、错误终局数、McNemar p（只报告）。"""
    a = {r["id"]: r for r in a_rows}
    b = {r["id"]: r for r in b_rows}
    if set(a) != set(b):
        raise GateError(f"两遍身份集合不同：只在前 {len(set(a) - set(b))}，只在后 {len(set(b) - set(a))}")
    bad = {i for i in a if a[i]["missing"] or a[i]["conflict"] or b[i]["missing"] or b[i]["conflict"]}
    status_changed = s2f = f2s = steps_diff = 0
    absdiff: list[float] = []
    for i in sorted(set(a) - bad):  # 缺失／冲突的身份不参与计数，单列 invalid（冻结与闸门见 invalid>0 即拒）
        sa, sb = a[i]["status"], b[i]["status"]
        status_changed += sa != sb
        s2f += sa == "success" and sb != "success"
        f2s += sa != "success" and sb == "success"
        ea, eb = a[i]["exec_steps"], b[i]["exec_steps"]
        if ea != eb:
            steps_diff += 1
        if ea is not None and eb is not None:
            absdiff.append(abs(float(ea) - float(eb)))
    t_a = sum(r["status"] == "timeout" for r in a.values())
    t_b = sum(r["status"] == "timeout" for r in b.values())
    err = sum(r["status"] == "error" for r in b.values())
    return {"n": len(a), "status_changed": status_changed, "s2f": s2f, "f2s": f2s, "net": s2f - f2s,
            "timeout_delta": abs(t_b - t_a), "timeout_a": t_a, "timeout_b": t_b, "steps_diff": steps_diff,
            "steps_absdiff_mean": statistics.fmean(absdiff) if absdiff else 0.0,
            "steps_absdiff_median": float(statistics.median(absdiff)) if absdiff else 0.0,
            "error_final": err, "error_final_a": sum(r["status"] == "error" for r in a.values()),
            "invalid": len(bad), "mcnemar_p": mcnemar_p(s2f, f2s),
            "success_a": sum(r["status"] == "success" for r in a.values()),
            "success_b": sum(r["status"] == "success" for r in b.values())}


# ── 九层摘要 ────────────────────────────────────────────────────────────────


def reset_summary(compare: dict[str, Any]) -> dict[str, Any]:
    details = compare.get("details") or []
    layers = list(compare.get("layer_equal", {}).keys())
    name_only_ids = sorted({d["id"] for d in details
                            if any(v.get("name_only") for v in d.get("layers", {}).values())})
    real_diff_ids = sorted({d["id"] for d in details
                            if any(not v.get("equal") and not v.get("name_only")
                                   for v in d.get("layers", {}).values())})
    return {"compared": int(compare.get("compared", len(details))), "layers": layers,
            "layer_equal": dict(compare.get("layer_equal", {})), "name_only_ids": name_only_ids,
            "name_only": sum((compare.get("name_only") or {}).values()), "real_diff_ids": real_diff_ids,
            "missing": len(compare.get("missing_in_a") or []) + len(compare.get("missing_in_b") or [])}


# ── 冻结与核验 ──────────────────────────────────────────────────────────────


def _bind(path: str | Path, role: str) -> dict[str, Any]:
    p = Path(path).resolve()
    return {"path": str(p), "sha256": sha256_file(p), "lines": line_count(p), "role": role}


def _group_name(g: dict[str, Any]) -> str:
    if g["kind"] == "gen":
        return f"gen:{g['set']}:w{int(g['workers'])}"
    if g["kind"] == "eval":
        return f"eval:{g['set']}:{g['policy']}"
    if g["kind"] == "reset":
        return f"reset:{g['set']}"
    raise GateError(f"未知组类型 {g.get('kind')}")


def _compute_group(g: dict[str, Any]) -> dict[str, Any]:
    """按组定义从输入重算原始个数、线、带（freeze 与 verify 共用）。"""
    kind = g["kind"]
    out: dict[str, Any] = {"name": _group_name(g), "kind": kind, "set": g["set"]}
    if kind == "gen":
        out["workers"] = int(g["workers"])
        per_pair = []
        ids = None
        for path in g["pairs"]:
            _meta, rows = read_gen_pairs(path)
            c = gen_counts(rows)
            if c["structural"] or c["unknown"]:
                raise GateError(f"{path}：基线里出现 structural={c['structural']} unknown={c['unknown']}，"
                                f"这两类必须为 0，不能当噪声冻结（交用户裁决）")
            cur = sorted(r["id"] for r in rows)
            if ids is not None and cur != ids:
                raise GateError(f"{path}：与同组其他对的身份集合不同")
            ids = cur
            per_pair.append(c)
        n = per_pair[0]["n"]
        out.update(n=n, pairs=per_pair,
                   lines={m: noise_line([c[m] for c in per_pair], n) for m in GEN_METRICS})
        out["zero_noise"] = all(c["diff"] == 0 for c in per_pair)
        out["inputs"] = [_bind(p, "gen_pair") for p in g["pairs"]]
    elif kind == "eval":
        out["policy"] = g["policy"]
        per_pair = []
        files: list[str] = []
        for pair in g["pairs"]:
            pa, pb = pair
            _ma, ra = read_extract(pa)
            _mb, rb = read_extract(pb)
            m = eval_pair_metrics(ra, rb)
            if m["invalid"]:
                raise GateError(f"{pa}:{pb}：有 {m['invalid']} 个身份缺失或冲突，不能冻结")
            per_pair.append(m)
            for p in (pa, pb):
                if str(Path(p).resolve()) not in files:
                    files.append(str(Path(p).resolve()))
        ref = g.get("reference")
        if ref is None or str(Path(ref).resolve()) not in files:
            raise GateError(f"{out['name']}：reference 须给出且是 pairs 里的某一遍")
        n = per_pair[0]["n"]
        out.update(n=n, pairs=per_pair, reference=str(Path(ref).resolve()),
                   lines={m: noise_line([p[m] for p in per_pair], n) for m in EVAL_METRICS},
                   bands={b: {"max_abs": max(abs(p[b]) for p in per_pair),
                              "band": max(abs(p[b]) for p in per_pair) * BAND_FACTOR} for b in EVAL_BANDS},
                   error_final_max=max(p["error_final"] for p in per_pair))
        out["zero_noise"] = all(p["status_changed"] == 0 and p["steps_diff"] == 0 for p in per_pair)
        out["inputs"] = [_bind(p, "eval_extract") for p in files]
    elif kind == "reset":
        sums = []
        for path in g["compare"]:
            sums.append(reset_summary(json.loads(Path(path).read_text(encoding="utf-8"))))
        out.update(pairs=sums, n=sums[0]["compared"],
                   name_only_ids=sorted({i for s in sums for i in s["name_only_ids"]}),
                   real_diff_ids=sorted({i for s in sums for i in s["real_diff_ids"]}))
        out["inputs"] = [_bind(p, "reset_compare") for p in g["compare"]]
        if g.get("reference_rows"):
            out["inputs"].append(_bind(g["reference_rows"], "reset_reference_rows"))
    return out


def _spec_of(group: dict[str, Any]) -> dict[str, Any]:
    """从冻结组还原它的输入定义（verify 用）。"""
    kind = group["kind"]
    if kind == "gen":
        return {"kind": "gen", "set": group["set"], "workers": group["workers"],
                "pairs": [i["path"] for i in group["inputs"]]}
    if kind == "eval":
        return {"kind": "eval", "set": group["set"], "policy": group["policy"], "pairs": group["pair_paths"],
                "reference": group["reference"]}
    spec = {"kind": "reset", "set": group["set"],
            "compare": [i["path"] for i in group["inputs"] if i["role"] == "reset_compare"]}
    ref = [i["path"] for i in group["inputs"] if i["role"] == "reset_reference_rows"]
    if ref:
        spec["reference_rows"] = ref[0]
    return spec


def freeze(spec: dict[str, Any]) -> dict[str, Any]:
    groups = []
    names = set()
    for g in spec["groups"]:
        frozen = _compute_group(g)
        if g["kind"] == "eval":
            frozen["pair_paths"] = [[str(Path(a).resolve()), str(Path(b).resolve())] for a, b in g["pairs"]]
        if frozen["name"] in names:
            raise GateError(f"组重复：{frozen['name']}")
        names.add(frozen["name"])
        groups.append(frozen)
    obj = {"schema": BASELINE_SCHEMA, "conditions": spec.get("conditions", {}), "formula": FORMULA,
           "constants": {"cp_alpha": CP_ALPHA, "line_quantile": LINE_QUANTILE, "band_factor": BAND_FACTOR,
                         "net_loss_max": NET_LOSS_MAX},
           "groups": groups}
    obj["sha256"] = payload_sha256(obj)
    return obj


def _num_eq(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-15)
        except (TypeError, ValueError):
            return False
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_num_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_num_eq(x, y) for x, y in zip(a, b))
    return a == b


def verify(obj: dict[str, Any]) -> tuple[bool, str, list[str]]:
    """重算顶层 sha256、各线公式、各输入 sha256 与由输入重算的原始个数。"""
    reasons: list[str] = []
    if obj.get("schema") != BASELINE_SCHEMA:
        reasons.append("schema")
    if obj.get("sha256") != payload_sha256(obj):
        reasons.append("top_sha256_mismatch")
    consts = obj.get("constants", {})
    if consts.get("net_loss_max") != NET_LOSS_MAX or consts.get("band_factor") != BAND_FACTOR \
            or consts.get("cp_alpha") != CP_ALPHA or consts.get("line_quantile") != LINE_QUANTILE:
        reasons.append("constants_changed")
    inputs = 0
    for g in obj.get("groups", []):
        name = g.get("name")
        for metric, ln in (g.get("lines") or {}).items():
            again = noise_line(ln["x"], ln["n"])
            if not _num_eq(again, ln):
                reasons.append(f"{name}:{metric}:line_formula")
        for band, bd in (g.get("bands") or {}).items():
            if not _num_eq(bd["band"], bd["max_abs"] * BAND_FACTOR):
                reasons.append(f"{name}:{band}:band_formula")
        for item in g.get("inputs", []):
            inputs += 1
            p = Path(item["path"])
            if not p.is_file():
                reasons.append(f"{name}:input_missing:{p}")
            elif sha256_file(p) != item["sha256"]:
                reasons.append(f"{name}:input_sha_mismatch:{p}")
        if any(r.startswith(f"{name}:input_") for r in reasons):
            continue
        try:
            again = _compute_group(_spec_of(g))
        except GateError as exc:
            reasons.append(f"{name}:recompute_error:{exc}")
            continue
        for key in ("pairs", "lines", "bands", "n", "zero_noise", "name_only_ids", "real_diff_ids"):
            if key in g or key in again:
                if not _num_eq(g.get(key), again.get(key)):
                    reasons.append(f"{name}:{key}_differs_from_inputs")
    ok = not reasons
    fsha = str(obj.get("sha256", ""))[:12]
    line = (f"NOISE_BASELINE={'PASS' if ok else 'FAIL'} groups={len(obj.get('groups', []))} "
            f"inputs_bound={inputs} file_sha={fsha}")
    return ok, line, reasons


def load_baseline(path: str | Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    ok, line, reasons = verify(obj)
    print(line, flush=True)
    if not ok:
        raise GateError(f"冻结文件核验失败，拒跑：{reasons[:10]}")
    return obj


def find_group(obj: dict[str, Any], name: str) -> dict[str, Any]:
    for g in obj["groups"]:
        if g["name"] == name:
            return g
    raise GateError(f"冻结文件里没有组 {name}")


# ── 闸门 ────────────────────────────────────────────────────────────────────


def gate_reset(group: dict[str, Any], compare: dict[str, Any]) -> tuple[bool, str, list[str]]:
    reasons: list[str] = []
    s = reset_summary(compare)
    if s["missing"]:
        reasons.append(f"missing={s['missing']}")
    if s["compared"] != group["n"]:
        reasons.append(f"compared={s['compared']}!={group['n']}")
    allowed = set(group.get("name_only_ids", []))
    new_name = [i for i in s["name_only_ids"] if i not in allowed]
    if new_name:
        reasons.append(f"new_name_only={len(new_name)}")
    if s["real_diff_ids"]:
        reasons.append(f"layer_diff={len(s['real_diff_ids'])}")
    ref = [i for i in group.get("inputs", []) if i["role"] == "reset_reference_rows"]
    ref_state = "unbound"
    if ref:
        shas = set()
        for side in ("a", "b"):
            if compare.get(side):
                rows = Path(compare[side]) / "rows.jsonl"
                if rows.is_file():
                    shas.add(sha256_file(rows))
        ref_state = "bound" if ref[0]["sha256"] in shas else "mismatch"
        if ref_state == "mismatch":
            reasons.append("reference_rows_not_used")
    ok = not reasons
    eq = ",".join(f"{k}:{v}" for k, v in s["layer_equal"].items())
    line = (f"RESET_GATE={'PASS' if ok else 'FAIL'} set={group['set']} compared={s['compared']} layers_equal={eq} "
            f"name_only={len(s['name_only_ids'])} new_name_only={len(new_name)} layer_diff={len(s['real_diff_ids'])} "
            f"reference={ref_state}")
    return ok, line, reasons


def gate_gen(group: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[bool, str, list[str], dict]:
    c = gen_counts(rows)
    reasons: list[str] = []
    if c["n"] != group["n"]:
        reasons.append(f"n={c['n']}!={group['n']}")
    if c["structural"]:
        reasons.append(f"structural={c['structural']}")
    if c["unknown"]:
        reasons.append(f"unknown={c['unknown']}")
    line_diff, line_fail = group["lines"]["diff"]["line"], group["lines"]["gen_fail"]["line"]
    if c["diff"] > line_diff:
        reasons.append(f"diff={c['diff']}>{line_diff}")
    if c["gen_fail"] > line_fail:
        reasons.append(f"gen_fail={c['gen_fail']}>{line_fail}")
    per_task: dict[str, int] = Counter(r["task"] for r in rows if r["class"] != "byte_equal")
    ok = not reasons
    line = (f"GEN_NOISE_GATE={'PASS' if ok else 'FAIL'} set={group['set']} workers={group['workers']} n={c['n']} "
            f"byte_equal={c['byte_equal']} diverge={c['diverge']} gen_fail={c['gen_fail']} "
            f"structural={c['structural']} unknown={c['unknown']} diff={c['diff']}/{line_diff} "
            f"gen_fail_line={line_fail}")
    return ok, line, reasons, dict(per_task)


def gate_eval(group: dict[str, Any], ref_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]
              ) -> tuple[bool, str, list[str], dict]:
    reasons: list[str] = []
    m = eval_pair_metrics(ref_rows, new_rows)
    if m["n"] != group["n"]:
        reasons.append(f"n={m['n']}!={group['n']}")
    if m["invalid"]:
        reasons.append(f"invalid={m['invalid']}")
    retried = sum(bool(r["retried_after_steps"]) for r in new_rows)
    if retried:
        reasons.append(f"retried_after_steps={retried}")
    if m["error_final"]:
        reasons.append(f"error_final={m['error_final']}")
    if group["zero_noise"]:
        mode = "zero"
        if m["status_changed"]:
            reasons.append(f"status_changed={m['status_changed']}>0")
        if m["steps_diff"]:
            reasons.append(f"steps_diff={m['steps_diff']}>0")
    else:
        mode = "noise"
        for metric in EVAL_METRICS:
            lim = group["lines"][metric]["line"]
            if m[metric] > lim:
                reasons.append(f"{metric}={m[metric]}>{lim}")
        if m["net"] > NET_LOSS_MAX:
            reasons.append(f"net_loss={m['net']}>{NET_LOSS_MAX}")
        for band in EVAL_BANDS:
            lim = group["bands"][band]["band"]
            if m[band] > lim + 1e-12:
                reasons.append(f"{band}={m[band]:.4g}>{lim:.4g}")
    ok = not reasons
    line = (f"EVAL_NOISE_GATE={'PASS' if ok else 'FAIL'} policy={group['policy']} set={group['set']} mode={mode} "
            f"n={m['n']} status_changed={m['status_changed']} s2f={m['s2f']} f2s={m['f2s']} net={m['net']} "
            f"timeout_delta={m['timeout_delta']} steps_diff={m['steps_diff']} "
            f"steps_absdiff_mean={m['steps_absdiff_mean']:.4g} steps_absdiff_median={m['steps_absdiff_median']:.4g} "
            f"error_final={m['error_final']} mcnemar_p={m['mcnemar_p']:.4g}")
    return ok, line, reasons, m


# ── selftest：内存夹具 ──────────────────────────────────────────────────────


def _fx_h5(path: Path, *, frames: int = 4, seed: int = 1, setup_seed: int | None = None, drop: tuple | None = None,
           diverge_at: int | None = None, frame0_delta: bool = False, waypoint_frames: Iterable[int] = (),
           waypoint_nan_frames: Iterable[int] = ()) -> Path:
    """小型 h5：一个 ``episode_<seed>`` 组，``setup`` 组 + ``timestep_<i>`` 组（动作／观测／信息三类数据集）。
    ``drop=(帧号, 数据集)`` 删一个字段；``diverge_at`` 起动作与关节状态加偏移；``frame0_delta`` 改第 0 帧图像；
    ``waypoint_frames`` 里的帧写 float64 实值的 ``action/waypoint_action``，``waypoint_nan_frames`` 里的帧写 float32 的 NaN
    占位（仿录像器：有待执行路点写实值、没有写占位，两种签名的帧随轨迹而变）。"""
    import h5py
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        ep = f.create_group(f"episode_{seed}")
        st = ep.create_group("setup")
        st["seed"] = np.int64(setup_seed if setup_seed is not None else seed)
        st["difficulty"] = "xhard1"
        st["front_camera_intrinsic"] = np.eye(3, dtype=np.float32)
        for i in range(frames):
            g = ep.create_group(f"timestep_{i}")
            off = 0.5 if diverge_at is not None and i >= diverge_at else 0.0
            g["action/joint_action"] = np.full(8, 0.1 * i + off, dtype=np.float64)
            g["obs/joint_state"] = np.full(7, 0.2 * i + off, dtype=np.float32)
            g["obs/gripper_state"] = np.zeros(2, dtype=np.float32)
            img = np.full((4, 4, 3), i % 255, dtype=np.uint8)
            if frame0_delta and i == 0:
                img[0, 0, 0] = 9
            g["obs/front_rgb"] = img
            g["obs/front_depth"] = np.zeros((4, 4, 1), dtype=np.int16)
            g["info/is_completed"] = np.bool_(i == frames - 1)
            if i in set(waypoint_frames):
                g["action/waypoint_action"] = np.full(7, 0.3, dtype=np.float64)
            elif i in set(waypoint_nan_frames):
                g["action/waypoint_action"] = np.full(7, np.nan, dtype=np.float32)
            if drop is not None and drop[0] == i:
                del g[drop[1]]
    return path


def _fx_side(root: Path, entries: dict[tuple[str, int], dict[str, Any]]) -> Path:
    """生成输出根夹具：写 identities.jsonl（``path`` 相对根）。"""
    root.mkdir(parents=True, exist_ok=True)
    lines = []
    for (task, seed), e in entries.items():
        line = {"task": task, "tier": e.get("tier", "xhard1"), "seed": seed, "success": e.get("ok", True),
                "error_type": e.get("error_type"), "path": None, "sha256": None}
        if e.get("h5"):
            line["path"] = os.path.relpath(e["h5"], root)  # 可指向根外（反例夹具复用同代码侧的文件）
            line["sha256"] = sha256_file(e["h5"])
        lines.append(line)
    write_jsonl(root / "identities.jsonl", lines)
    return root


def _fx_idents(n: int, tier: str = "xhard1", task: str = "T") -> list[dict[str, Any]]:
    return [{"id": id_str(task, tier, s), "task": task, "tier": tier, "seed": s} for s in range(n)]


def _fx_extract(statuses: list[str], steps: list[int | None], *, root: str = "/x", ids: list[dict] | None = None,
                aid_prefix: str = "a", started: float = 100.0) -> tuple[dict, list[dict]]:
    ids = ids or _fx_idents(len(statuses))
    rows = [_extract_row(i, status=s, exec_steps=k, attempt_id=f"{aid_prefix}{n}", started_at=started + n)
            for n, (i, s, k) in enumerate(zip(ids, statuses, steps))]
    meta = {"kind": "meta", "schema": EXTRACT_SCHEMA, "format": "v8", "policy": "p", "root": root, "extra": 0,
            "run_blocked": 0, "rec_checked": None}
    meta["summary"] = extract_summary(rows, meta)
    return meta, rows


def _fx_write_extract(path: Path, ext: tuple[dict, list[dict]]) -> Path:
    return write_jsonl(path, [ext[0], *ext[1]])


def _fx_v8_stage(stage: Path, policy: str, entries: list[dict[str, Any]]) -> Path:
    """V8 运行根夹具：``s01/<policy>/results.jsonl`` 与账本。entries 每项 {key, task, tier, seed, attempts:[{id,
    status, exec_steps, infra, infra_reason, accept, late, t}]}。"""
    sd = stage / "s01" / policy
    sd.mkdir(parents=True, exist_ok=True)
    res, led = [], []
    for e in entries:
        for a in e["attempts"]:
            led.append({"kind": "attempt_start", "key": e["key"], "attempt_id": a["id"], "attempt_no": 1,
                        "retry": False, "t": a.get("t", 1000.0)})
            row = {"v8": True, "key": e["key"], "task": e["task"], "tier": e["tier"], "seed": e["seed"],
                   "spec_sha256": e.get("spec"), "status": a["status"], "exec_steps": a.get("exec_steps"),
                   "attempt_id": a["id"], "infra": a.get("infra", False), "infra_reason": a.get("infra_reason"),
                   "canary": False, "policy": policy}
            if not a.get("no_row"):
                res.append(row)
            led.append({"kind": "attempt_end", "key": e["key"], "attempt_id": a["id"], "status": a["status"],
                        "infra": a.get("infra", False), "exec_steps": a.get("exec_steps"), "late": a.get("late", False)})
            if a.get("accept"):
                led.append({"kind": "accept", "key": e["key"], "attempt_id": a["id"], "accepted_attempt_id": a["id"],
                            "status": a["status"]})
    write_jsonl(sd / "results.jsonl", res)
    write_jsonl(sd / f"{policy}.ledger.jsonl", led)
    return stage


def _noisy_eval_baseline(tmp: Path, n: int = 192) -> tuple[dict[str, Any], Path]:
    """带噪声的评估基线：参照遍 + 两遍，各约 10 局成败互翻、若干步数差。返回 (冻结对象, 参照 extract 路径)。"""
    ids = _fx_idents(n, task="E")
    base = ["success" if i % 3 == 0 else "fail" for i in range(n)]
    steps = [100 + (i % 7) for i in range(n)]
    ref = _fx_write_extract(tmp / "ref.jsonl", _fx_extract(base, steps, ids=ids, root="/r0"))
    paths = []
    for k, (flip, dstep) in enumerate(((10, 3), (12, 5))):
        st = list(base)
        sp = list(steps)
        succ = [i for i in range(n) if base[i] == "success"]
        fail = [i for i in range(n) if base[i] == "fail"]
        for i in succ[:flip]:
            st[i] = "fail"
        for i in fail[:flip - 1]:
            st[i] = "success"
        for i in range(0, 2 * dstep, 2):
            sp[i] += dstep
        paths.append(_fx_write_extract(tmp / f"b{k}.jsonl", _fx_extract(st, sp, ids=ids, root=f"/r{k + 1}",
                                                                        aid_prefix=f"p{k}")))
    spec = {"conditions": {"gpu": "fixture"},
            "groups": [{"kind": "eval", "set": "G9", "policy": "p",
                        "pairs": [[str(ref), str(paths[0])], [str(ref), str(paths[1])], [str(paths[0]), str(paths[1])]],
                        "reference": str(ref)}]}
    return freeze(spec), ref


def selftest(verbose: bool = True) -> tuple[bool, str, list[tuple[str, bool]]]:
    """同代码一对须 PASS；计划第一部分第六节的反例（另加旧路线墙钟超时后重试）须逐个 FAIL。"""
    results: list[tuple[str, bool, str]] = []  # (名字, 是否符合预期, 说明)

    def expect(name: str, want_pass: bool, got_pass: bool, note: str = "") -> None:
        results.append((name, want_pass == got_pass, note))
        if verbose:
            print(f"# selftest {name}: 预期={'PASS' if want_pass else 'FAIL'} 实得={'PASS' if got_pass else 'FAIL'} {note}")

    with tempfile.TemporaryDirectory(prefix="noise-gate-selftest-") as tmpd:
        tmp = Path(tmpd)
        # ── 生成：同代码一对（含全等局、一个正常分叉局）与基线 ──
        ids = _fx_idents(6)
        ref_e, same_e, bad_e = {}, {}, {}
        for i in ids:
            s = i["seed"]
            # seed 5 是正常分叉局：第 2 帧起分叉，间歇字段 waypoint_action 的有无也随之不同（不得判结构不同）
            ref_e[("T", s)] = {"h5": _fx_h5(tmp / "ref" / f"e{s}.h5", seed=s,
                                            waypoint_frames=(1, 2) if s == 5 else ())}
            same_e[("T", s)] = {"h5": _fx_h5(tmp / "same" / f"e{s}.h5", seed=s, diverge_at=2 if s == 5 else None,
                                             waypoint_frames=(1, 3) if s == 5 else ())}
        ref_root = _fx_side(tmp / "ref", ref_e)
        same_root = _fx_side(tmp / "same", same_e)
        rows, counts = gen_compare(ref_root, same_root, ids)
        gen_meta = {"kind": "meta", "schema": GEN_SCHEMA, "ref": str(ref_root), "new": str(same_root), "n": len(rows)}
        p1 = write_jsonl(tmp / "gen1.jsonl", [gen_meta, *rows])
        p2 = write_jsonl(tmp / "gen2.jsonl", [gen_meta, *rows])
        gbase = freeze({"groups": [{"kind": "gen", "set": "G9", "workers": 4, "pairs": [str(p1), str(p2)]}]})
        ggroup = find_group(gbase, "gen:G9:w4")
        ok, line, _r, _t = gate_gen(ggroup, rows)
        byte_eq = counts["byte_equal"] == 5 and counts["diverge"] == 1
        expect("same_code_gen", True, ok and byte_eq, line)
        # 全等局不得被分叉步规则拒绝（全同局 first_divergence 为 null、归 byte_equal）
        eq_rows = [r for r in rows if r["class"] == "byte_equal"]
        expect("全等局不被分叉步规则拒绝", True, bool(eq_rows) and all(r["first_divergence"] is None for r in eq_rows))
        # 反例：初帧缺一个字段
        bad_e = dict(same_e)
        bad_e[("T", 0)] = {"h5": _fx_h5(tmp / "bad1" / "e0.h5", seed=0, drop=(0, "obs/front_depth"))}
        rows_b, _c = gen_compare(ref_root, _fx_side(tmp / "bad1", bad_e), ids)
        ok, line, _r, _t = gate_gen(ggroup, rows_b)
        expect("初帧缺一个字段", False, ok, line)
        # 加强：中间某一帧缺一个字段（schema_of 归一后取集合会漏掉）
        bad_e = dict(same_e)
        bad_e[("T", 1)] = {"h5": _fx_h5(tmp / "bad2" / "e1.h5", seed=1, drop=(2, "obs/front_depth"))}
        rows_b, _c = gen_compare(ref_root, _fx_side(tmp / "bad2", bad_e), ids)
        ok, line, _r, _t = gate_gen(ggroup, rows_b)
        expect("中间帧缺一个字段", False, ok, line)
        # 反例：setup 改一个值
        bad_e = dict(same_e)
        bad_e[("T", 2)] = {"h5": _fx_h5(tmp / "bad3" / "e2.h5", seed=2, setup_seed=999)}
        rows_b, _c = gen_compare(ref_root, _fx_side(tmp / "bad3", bad_e), ids)
        ok, line, _r, _t = gate_gen(ggroup, rows_b)
        expect("setup 改一个值", False, ok, line)

        # ── 评估 ──
        ebase, ref_path = _noisy_eval_baseline(tmp)
        egroup = find_group(ebase, "eval:G9:p")
        _rm, ref_rows = read_extract(ref_path)
        # 同代码一对：少量互翻、少量步数差
        st = [r["status"] for r in ref_rows]
        sp = [r["exec_steps"] for r in ref_rows]
        succ = [i for i, s in enumerate(st) if s == "success"]
        fail = [i for i, s in enumerate(st) if s == "fail"]
        st2 = list(st)
        for i in succ[:3]:
            st2[i] = "fail"
        for i in fail[:3]:
            st2[i] = "success"
        sp2 = list(sp)
        sp2[0] += 2
        same = _fx_extract(st2, sp2, ids=_fx_idents(192, task="E"), root="/new")
        ok, line, _r, _m = gate_eval(egroup, ref_rows, same[1])
        expect("same_code_eval", True, ok, line)
        # 反例：失败全部改成超时而成功数不变
        st3 = ["timeout" if s == "fail" else s for s in st]
        ok, line, _r, _m = gate_eval(egroup, ref_rows, _fx_extract(st3, sp, ids=_fx_idents(192, task="E"))[1])
        expect("失败全改超时成功数不变", False, ok, line)
        # 反例：终态不变但步数从 100 变 1600
        ok, line, _r, _m = gate_eval(egroup, ref_rows,
                                     _fx_extract(st, [1600] * len(st), ids=_fx_idents(192, task="E"))[1])
        expect("步数 100 变 1600", False, ok, line)
        # 反例：成功→失败 12、失败→成功 4（各自不超线，只有净损失 8 超）
        st4 = list(st)
        for i in succ[:12]:
            st4[i] = "fail"
        for i in fail[:4]:
            st4[i] = "success"
        ok, line, why, _m = gate_eval(egroup, ref_rows, _fx_extract(st4, sp, ids=_fx_idents(192, task="E"))[1])
        expect("s2f=12 f2s=4", False, ok, f"{line} reasons={why}")
        # 反例：迟到成功覆盖已接受失败（账本口径取被接受的失败；5 局即净损失 5 → FAIL；按「最后一条」取数会漏放）
        eids = _fx_idents(192, task="E")
        entries = []
        for n, i in enumerate(eids):
            key = f"{i['task']}_{i['tier']}_{i['seed']}"
            if n in succ[:5]:
                attempts = [{"id": f"x{n}", "status": "fail", "exec_steps": sp[n], "accept": True, "t": 2000.0},
                            {"id": f"y{n}", "status": "success", "exec_steps": sp[n], "late": True, "t": 2100.0}]
            else:
                attempts = [{"id": f"x{n}", "status": st[n], "exec_steps": sp[n], "accept": True, "t": 2000.0}]
            entries.append({"key": key, "task": i["task"], "tier": i["tier"], "seed": i["seed"], "attempts": attempts})
        stage = _fx_v8_stage(tmp / "late-stage", "p", entries)
        late_rows, _meta = extract_v8(stage, "p", eids)
        took_accepted = all(late_rows[n]["status"] == "fail" for n in succ[:5])
        ok, line, _r, _m = gate_eval(egroup, ref_rows, late_rows)
        expect("迟到成功覆盖已接受失败", False, ok or not took_accepted, line)
        # 反例：第二遍复用第一遍的输出根（同一运行根、同一批 attempt_id）；用一个干净的运行根，排除迟到行的干扰
        clean = [dict(e, attempts=e["attempts"][:1]) for e in entries]
        stage = _fx_v8_stage(tmp / "clean-stage", "p", clean)
        first = extract_v8(stage, "p", eids)
        prov1 = {"pass": "pass1", "started_at": 1500.0, "out_root": str(stage), "assets_sha": "abc",
                 "fingerprint": "f" * 64, "out_root_state": "empty"}
        m1 = {"kind": "meta", "schema": EXTRACT_SCHEMA, "format": "v8", "root": str(stage.resolve()), **first[1]}
        ok1, line1, _r = run_fresh((m1, first[0]), prov1, 192, [])
        expect("same_code_first_pass_fresh", True, ok1, line1)
        prov ={"pass": "pass2", "started_at": 1500.0, "out_root": str(stage), "assets_sha": "abc",
                "fingerprint": "f" * 64, "out_root_state": "empty"}
        ok, line, _r = run_fresh((m1, first[0]), prov, 192, [(m1, first[0])])
        expect("第二遍复用第一遍的输出根", False, ok, line)
        # 反例：改动冻结文件里一条线而不改 sha256
        tampered = json.loads(json.dumps(ebase))
        tampered["groups"][0]["lines"]["s2f"]["line"] += 5
        ok, line, _r = verify(tampered)
        expect("改冻结线不改 sha256", False, ok, line)
        # 加强：旧路线墙钟超时后重试成功须判 retried_after_steps
        lroot = tmp / "legacy"
        (lroot / "p" / "rec" / "T_0").mkdir(parents=True)
        (lroot / "p" / "rec" / "T_0.a2").mkdir(parents=True)
        write_jsonl(lroot / "p" / "results.jsonl", [
            {"task": "T", "seed": 0, "policy": "p", "attempt": 1, "status": "error", "infra": True,
             "infra_reason": "episode_wall", "steps": None, "canary": False, "rec_dir": "/tmp/x/rec/T_0"},
            {"task": "T", "seed": 0, "policy": "p", "attempt": 2, "status": "success", "infra": False,
             "steps": 300, "canary": False, "rec_dir": "/tmp/x/rec/T_0.a2"}])
        lid = [{"id": id_str("T", "xhard0", 0), "task": "T", "tier": "xhard0", "seed": 0}]
        lrows, lmeta = extract_legacy(lroot, "p", lid)
        lm = {"kind": "meta", "schema": EXTRACT_SCHEMA, "format": "legacy", "root": str(lroot.resolve()), **lmeta}
        ok, line, _r = run_fresh((lm, lrows), {"pass": "d0", "out_root": str(lroot), "out_root_state": "empty",
                                               "assets_sha": "abc", "fingerprint": "f" * 64}, 1, [])
        expect("旧路线墙钟超时后重试成功", False, ok or not lrows[0]["retried_after_steps"], line)

    same_ok = all(ok for name, ok, _ in results if name.startswith("same_code") or name.startswith("全等局"))
    cases = [(name, ok) for name, ok, _ in results if not (name.startswith("same_code") or name.startswith("全等局"))]
    passed = same_ok and all(ok for _n, ok in cases)
    good = sum(ok for _n, ok in cases)
    line = (f"GATE_SELFTEST={'PASS' if passed else 'FAIL'} same_code={'PASS' if same_ok else 'FAIL'} "
            f"cases_fail={good}/{len(cases)}")
    return passed, line, [(n, ok) for n, ok, _ in results]


# ── CLI ─────────────────────────────────────────────────────────────────────


def _print_per_task(title: str, table: dict[str, Any]) -> None:
    for task in sorted(table):
        print(f"# {title} {task}: {table[task]}")


def cmd_gen_compare(args) -> int:
    identities = load_identities(args.identities)
    rows, counts = gen_compare(args.ref, args.new, identities, rehash=not args.trust_recorded_sha)
    meta = {"kind": "meta", "schema": GEN_SCHEMA, "ref": str(Path(args.ref).resolve()),
            "new": str(Path(args.new).resolve()), "identities": str(Path(args.identities).resolve()),
            "n": len(rows), "rehash": not args.trust_recorded_sha, "counts": counts}
    write_jsonl(args.out, [meta, *rows])
    for r in rows:
        if r["class"] not in ("byte_equal", "diverge"):
            print(f"# {r['class']} {r['id']} reason={r['reason']} fail_side={r['fail_side']}")
    print(f"GEN_PAIR=INFO ref={Path(args.ref).name} new={Path(args.new).name} n={len(rows)} "
          + " ".join(f"{c}={counts[c]}" for c in GEN_CLASSES), flush=True)
    return 0


def cmd_eval_extract(args) -> int:
    identities = load_identities(args.identities)
    rows, meta, ok, line = eval_extract(args.format, args.root, args.policy, identities, allow_extra=args.allow_extra)
    meta["identities"] = str(Path(args.identities).resolve())
    write_jsonl(args.out, [meta, *rows])
    for r in rows:
        if r["missing"] or r["conflict"] or r["retried_after_steps"]:
            print(f"# {r['id']} missing={r['missing']} conflict={r['conflict']} flags={r['flags'][:4]}")
    print(line, flush=True)
    return 0 if ok else 1


def cmd_run_fresh(args) -> int:
    ext = read_extract(args.extract)
    prov = json.loads(Path(args.provenance).read_text(encoding="utf-8"))
    others = [read_extract(p) for p in args.other or []]
    ok, line, reasons = run_fresh(ext, prov, args.expect, others)
    for r in reasons:
        print(f"# {r}")
    print(line, flush=True)
    return 0 if ok else 1


def cmd_baseline_reset(args) -> int:
    s = reset_summary(json.loads(Path(args.compare).read_text(encoding="utf-8")))
    eq = ",".join(f"{k}:{v}" for k, v in s["layer_equal"].items())
    print(f"RESET_BASELINE=INFO set={args.set} pairs=1 compared={s['compared']} layers_equal={eq} "
          f"name_only={len(s['name_only_ids'])} layer_diff={len(s['real_diff_ids'])} missing={s['missing']}", flush=True)
    return 0


def cmd_baseline_gen(args) -> int:
    per_pair = []
    nonbyte: Counter = Counter()
    per_task: dict[str, list[int]] = defaultdict(lambda: [0] * len(args.pairs))
    n = None
    for k, path in enumerate(args.pairs):
        _meta, rows = read_gen_pairs(path)
        per_pair.append(gen_counts(rows))
        n = len(rows) if n is None else n
        for r in rows:
            if r["class"] != "byte_equal":
                nonbyte[r["id"]] += 1
                per_task[r["task"]][k] += 1
    total = {c: sum(p[c] for p in per_pair) for c in GEN_CLASSES}
    overlap = sum(1 for v in nonbyte.values() if v >= 2)
    _print_per_task("逐任务非逐字节相同局数（按对）", dict(per_task))
    print(f"GEN_BASELINE=INFO set={args.set} workers={args.workers} pairs={len(per_pair)} n={n} classes="
          + ",".join(f"{c}:{total[c]}" for c in GEN_CLASSES) + f" same_identity_overlap={overlap}", flush=True)
    return 0


def cmd_baseline_eval(args) -> int:
    ms = []
    for spec in args.pairs:
        a, _, b = spec.partition(":")
        if not b:
            raise GateError(f"--pairs 项须为 a.jsonl:b.jsonl：{spec}")
        ms.append(eval_pair_metrics(read_extract(a)[1], read_extract(b)[1]))

    def j(key, fmt="{}"):
        return ",".join(fmt.format(m[key]) for m in ms)
    print(f"EVAL_BASELINE=INFO policy={args.policy} set={args.set} pairs={len(ms)} status_changed={j('status_changed')} "
          f"s2f={j('s2f')} f2s={j('f2s')} net={j('net')} timeout_delta={j('timeout_delta')} "
          f"steps_diff={j('steps_diff')} steps_absdiff_mean={j('steps_absdiff_mean', '{:.4g}')} "
          f"steps_absdiff_median={j('steps_absdiff_median', '{:.4g}')} error_final={j('error_final')} "
          f"mcnemar_p={j('mcnemar_p', '{:.4g}')}", flush=True)
    return 0


def cmd_freeze(args) -> int:
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    try:
        obj = freeze(spec)
    except GateError as exc:
        print(f"# {exc}")
        print("NOISE_BASELINE=FAIL groups=0 inputs_bound=0 file_sha=-", flush=True)
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for g in obj["groups"]:
        lines = ",".join(f"{k}:{v['line']}" for k, v in (g.get("lines") or {}).items())
        print(f"# {g['name']} n={g.get('n')} zero_noise={g.get('zero_noise')} lines={lines}")
    ok, line, reasons = verify(obj)
    for r in reasons:
        print(f"# {r}")
    print(line, flush=True)
    return 0 if ok else 1


def cmd_verify(args) -> int:
    obj = json.loads(Path(args.path).read_text(encoding="utf-8"))
    ok, line, reasons = verify(obj)
    for r in reasons:
        print(f"# {r}")
    print(line, flush=True)
    return 0 if ok else 1


def cmd_check_reset(args) -> int:
    obj = load_baseline(args.baseline)
    ok, line, reasons = gate_reset(find_group(obj, f"reset:{args.set}"),
                                   json.loads(Path(args.compare).read_text(encoding="utf-8")))
    for r in reasons:
        print(f"# {r}")
    print(line, flush=True)
    return 0 if ok else 1


def cmd_check_gen(args) -> int:
    obj = load_baseline(args.baseline)
    _meta, rows = read_gen_pairs(args.pair)
    ok, line, reasons, per_task = gate_gen(find_group(obj, f"gen:{args.set}:w{args.workers}"), rows)
    _print_per_task("逐任务非逐字节相同局数（只定位、不判定）", per_task)
    for r in reasons:
        print(f"# {r}")
    print(line, flush=True)
    return 0 if ok else 1


def cmd_check_eval(args) -> int:
    obj = load_baseline(args.baseline)
    group = find_group(obj, f"eval:{args.set}:{args.policy}")
    if str(Path(args.ref).resolve()) != group["reference"] or sha256_file(args.ref) != next(
            i["sha256"] for i in group["inputs"] if i["path"] == group["reference"]):
        raise GateError(f"--ref 须是冻结文件登记的参照遍：{group['reference']}")
    ok, line, reasons, _m = gate_eval(group, read_extract(args.ref)[1], read_extract(args.new)[1])
    for r in reasons:
        print(f"# {r}")
    print(line, flush=True)
    return 0 if ok else 1


def cmd_selftest(args) -> int:
    ok, line, _cases = selftest(verbose=True)
    print(line, flush=True)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="噪声基线比较器与回归闸门")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("gen-compare", help="两侧生成 h5 逐局五类归类")
    p.add_argument("--ref", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--identities", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--trust-recorded-sha", action="store_true", help="不重算文件 sha256，直接用侧记录的值（快、弱）")
    p.set_defaults(func=cmd_gen_compare)
    p = sub.add_parser("eval-extract", help="按权威尝试取评估结果")
    p.add_argument("--format", choices=("v8", "legacy"), required=True)
    p.add_argument("--root", required=True, action="append", help="v8 可重复给多个运行根（合并后按账本判）")
    p.add_argument("--policy", required=True)
    p.add_argument("--identities", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--allow-extra", action="store_true", help="运行根有清单外身份时不判 FAIL（并入正式评估那一遍）")
    p.set_defaults(func=cmd_eval_extract)
    p = sub.add_parser("run-fresh", help="核对一遍是真的新跑")
    p.add_argument("--extract", required=True)
    p.add_argument("--provenance", required=True)
    p.add_argument("--expect", type=int, default=192)
    p.add_argument("--other", action="append")
    p.set_defaults(func=cmd_run_fresh)
    p = sub.add_parser("baseline-reset")
    p.add_argument("--compare", required=True)
    p.add_argument("--set", choices=("G9", "D0"), required=True)
    p.set_defaults(func=cmd_baseline_reset)
    p = sub.add_parser("baseline-gen")
    p.add_argument("--pairs", nargs="+", required=True)
    p.add_argument("--workers", type=int, choices=(4, 1), required=True)
    p.add_argument("--set", choices=("G9", "D0"), required=True)
    p.set_defaults(func=cmd_baseline_gen)
    p = sub.add_parser("baseline-eval")
    p.add_argument("--pairs", nargs="+", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--set", choices=("G9", "D0"), required=True)
    p.set_defaults(func=cmd_baseline_eval)
    p = sub.add_parser("freeze")
    p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_freeze)
    p = sub.add_parser("verify")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("check-reset")
    p.add_argument("--baseline", required=True)
    p.add_argument("--set", choices=("G9", "D0"), required=True)
    p.add_argument("--compare", required=True)
    p.set_defaults(func=cmd_check_reset)
    p = sub.add_parser("check-gen")
    p.add_argument("--baseline", required=True)
    p.add_argument("--set", choices=("G9", "D0"), required=True)
    p.add_argument("--workers", type=int, choices=(4, 1), default=4)
    p.add_argument("--pair", required=True)
    p.set_defaults(func=cmd_check_gen)
    p = sub.add_parser("check-eval")
    p.add_argument("--baseline", required=True)
    p.add_argument("--set", choices=("G9", "D0"), required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--new", required=True)
    p.set_defaults(func=cmd_check_eval)
    p = sub.add_parser("selftest")
    p.set_defaults(func=cmd_selftest)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except GateError as exc:
        print(f"# 拒跑：{exc}", flush=True)
        name = {"check-reset": "RESET_GATE", "check-gen": "GEN_NOISE_GATE", "check-eval": "EVAL_NOISE_GATE",
                "run-fresh": "RUN_FRESH", "eval-extract": "EVAL_EXTRACT", "verify": "NOISE_BASELINE",
                "selftest": "GATE_SELFTEST"}.get(args.cmd)
        if name:
            print(f"{name}=FAIL reason=refused", flush=True)
        return 2


if __name__ == "__main__":
    os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
    sys.exit(main())
