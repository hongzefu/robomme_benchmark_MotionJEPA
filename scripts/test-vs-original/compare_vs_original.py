#!/usr/bin/env python
"""生成产物 vs 官方原始发布集的容差比较（`scripts/test-vs-original/`）。

背景：官方发布集本身是多 worker 生成的，逐位复现不可能；官方比较器只比 ``joint_action``、
零容差、帧数不等整局丢弃。本脚本在官方合同审计之上加一层**分档容差**判定：

* 每局分四类：``IDENTICAL``（全字段按位相同）／``DRIFT``（同一条规划、数值漂移在容差内）／
  ``REPLAN``（帧数不等或超容差，但合同与布局一致）／``FAIL``（合同层或布局层不过）。
* 数据集级：``FAIL == 0`` 且 ``REPLAN`` 比例 ≤ 档位上限 → ``VS_ORIGINAL=PASS``。
* 档位按硬件分：``ada``（sled-vail RTX 6000 Ada，与原版同架构，紧）／``a40``（A40 / A6000，松），
  ``--tier auto`` 用 ``nvidia-smi`` 自动匹配，判定行里必须标明档位。

输入布局与 ``train_split_parity.py merge`` 的输出一致：``<generated>/record_dataset_<Task>.h5`` +
``record_dataset_<Task>_metadata.json``；发布集同布局（每文件 100 局）。

判定行（末尾另有 ``EXIT_CODE=``）::

    VS_ORIGINAL=PASS tier=ada compared=48 identical=48 drift=0 replan=0 fail=0 replan_rate=0.0000 replan_max=0.02
    # 手臂通道 DRIFT 局 p99：joint_action=… eef_action=… joint_state=… eef_state=…
    # 布局层：ts0 grounded 相同=48/48；ts0 图像最大像素差比例=…；边界坐标最大像素差=…；边界帧号最大偏移=…
    REFERENCE_AUDIT_COMPLETE=PASS compared=48 contract_errors=0 missing=0     （给了 --official-root 时）

全部比较一律"产物 vs 原版发布集"，不做产物互比。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

DEFAULT_REFERENCE = Path("/data/hongzefu/robomme_data_h5")
DEFAULT_TOLERANCE = HERE / "tolerance.json"

# 手臂通道：逐元素容差；夹爪通道：按翻转事件比
ARM_FIELDS = {
    "joint_action": ("action/joint_action", slice(0, 7)),
    "eef_action": ("action/eef_action", slice(0, 6)),
    "joint_state": ("obs/joint_state", slice(None)),
    "eef_state": ("obs/eef_state", slice(None)),
}
GRIPPER_SIGN_FIELDS = {
    "joint_action_gripper": ("action/joint_action", 7),
    "eef_action_gripper": ("action/eef_action", 6),
}
IMAGE_FIELDS = ("obs/front_rgb", "obs/front_depth", "obs/wrist_rgb", "obs/wrist_depth")
COORD_RE = re.compile(r"<\s*(-?\d+)\s*,\s*(-?\d+)\s*>")


class CompareError(RuntimeError):
    pass


# ---------- 读取 ----------

def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, np.ndarray):
        return json.dumps([_text(v) for v in value.tolist()], ensure_ascii=False)
    return str(value)


_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm_text(value: str) -> str:
    """指令文本归一化：小写、非字母数字一律折成单个空格。只用于合同层的文本比较。"""
    return _NORM_RE.sub(" ", value.lower()).strip()


def _timesteps(group: h5py.Group) -> list[int]:
    steps = []
    for name in group:
        if name.startswith("timestep_"):
            steps.append(int(name.split("_", 1)[1]))
    return sorted(steps)


def _stack(group: h5py.Group, steps: list[int], path: str) -> np.ndarray:
    return np.stack([group[f"timestep_{t}/{path}"][()] for t in steps])


def _bools(group: h5py.Group, steps: list[int], path: str) -> np.ndarray:
    return np.array([bool(group[f"timestep_{t}/{path}"][()]) for t in steps])


def _flips(seq: np.ndarray) -> np.ndarray:
    """布尔/符号序列的翻转帧号（翻转发生在第 i+1 帧）。"""
    return np.flatnonzero(np.diff(seq.astype(np.int64)) != 0) + 1


def _read_generated_records(generated: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for meta in sorted(generated.glob("record_dataset_*_metadata.json")):
        payload = json.loads(meta.read_text(encoding="utf-8"))
        for rec in payload["records"]:
            rows.append({
                "task": str(rec["task"]),
                "episode": int(rec["episode"]),
                "seed": int(rec["seed"]),
                "difficulty": str(rec["difficulty"]),
            })
    if not rows:
        raise CompareError(f"{generated} 下没有 record_dataset_*_metadata.json")
    return rows


# ---------- 档位 ----------

def detect_tier(tolerance: dict[str, Any], requested: str) -> tuple[str, str]:
    tiers = tolerance["tiers"]
    if requested != "auto":
        if requested not in tiers:
            raise CompareError(f"未知档位 {requested!r}，可选 {sorted(tiers)}")
        return requested, "explicit"
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise CompareError(f"--tier auto 需要 nvidia-smi：{exc}；请显式给 --tier") from exc
    names = [line.strip() for line in out.splitlines() if line.strip()]
    for tier, cfg in tiers.items():
        if any(any(m in name for m in cfg["match"]) for name in names):
            return tier, f"auto:{names[0]}"
    raise CompareError(f"nvidia-smi 报的 GPU {names!r} 不匹配任何档位的 match 列表；请显式给 --tier")


# ---------- 单局比较 ----------

def compare_episode(gen: h5py.Group, ref: h5py.Group, tier_cfg: dict[str, Any]) -> dict[str, Any]:
    rec: dict[str, Any] = {"reasons": []}

    # 1. 合同层（零容差）。文本字段先做归一化（小写、去标点/连字符/多余空白）再比：
    #    发布集（v0.5 分支）与现行源码之间存在纯标点差异（如 "right-side" vs "right side"、多一个逗号），
    #    这类差异只记录 text_raw_mismatch，不判 FAIL；归一化后仍不同才是真的指令变了。
    contract_mismatch = []
    text_raw_mismatch = []
    text_semantic_mismatch = []
    for key in ("seed", "difficulty"):
        gp, rp = f"setup/{key}", f"setup/{key}"
        if (gp in gen) != (rp in ref):
            contract_mismatch.append(f"{key}:missing")
            continue
        if gp in gen and _text(gen[gp][()]) != _text(ref[rp][()]):
            contract_mismatch.append(key)
    for key in ("task_goal", "available_multi_choices"):
        gp, rp = f"setup/{key}", f"setup/{key}"
        if (gp in gen) != (rp in ref):
            contract_mismatch.append(f"{key}:missing")
            continue
        if gp in gen:
            a_raw, b_raw = gen[gp][()], ref[rp][()]
            a, b = _text(a_raw), _text(b_raw)
            if a != b:
                text_raw_mismatch.append(key)
                if key == "task_goal":
                    # task_goal 是若干条等价指令的数组；现行源码比发布集多出改写条目（如 VideoPlaceButton 3 条 vs 2 条）。
                    # 只对第 0 条（主指令）做归一化比较，其余改写条只记录。
                    a0 = _text(np.asarray(a_raw).reshape(-1)[0]) if isinstance(a_raw, np.ndarray) else a
                    b0 = _text(np.asarray(b_raw).reshape(-1)[0]) if isinstance(b_raw, np.ndarray) else b
                    if _norm_text(a0) != _norm_text(b0):
                        text_semantic_mismatch.append(key)
                elif _norm_text(a) != _norm_text(b):
                    text_semantic_mismatch.append(key)
    rec["text_raw_mismatch"] = text_raw_mismatch
    rec["text_semantic_mismatch"] = text_semantic_mismatch
    # 指令语义不同（如 VideoPlaceOrder 的 task_goal 由示范执行结果决定："first target" vs "second target"）：
    # 紧档判 FAIL（同架构应精确复现示范）；松档记为 REPLAN 级差异（示范阶段重规划），不判 FAIL。
    if text_semantic_mismatch and tier_cfg.get("strict_text", True):
        contract_mismatch.extend(text_semantic_mismatch)
    tg, tr = _timesteps(gen), _timesteps(ref)
    rec["frames"] = {"generated": len(tg), "reference": len(tr)}
    if not tg or not tr:
        contract_mismatch.append("no_timesteps")
    else:
        gc = bool(gen[f"timestep_{tg[-1]}/info/is_completed"][()])
        rc = bool(ref[f"timestep_{tr[-1]}/info/is_completed"][()])
        rec["final_is_completed"] = {"generated": gc, "reference": rc}
        if gc != rc or not gc:
            contract_mismatch.append("final_is_completed")
    rec["contract_mismatch"] = contract_mismatch
    if contract_mismatch:
        rec["reasons"].append("contract:" + ",".join(contract_mismatch))
        rec["category"] = "FAIL"
        return rec

    # 2. 布局层：ts0 grounded 全文精确；ts0 深度/rgb 逐像素
    g0 = _text(gen["timestep_0/info/grounded_subgoal"][()])
    r0 = _text(ref["timestep_0/info/grounded_subgoal"][()])
    rec["ts0_grounded"] = {"generated": g0, "reference": r0, "same": g0 == r0}
    layout_fail = []
    plan_level = []  # 布局相同但首个目标物选择不同：规划层差异（松档记 REPLAN，紧档 FAIL）
    if g0 != r0:
        if tier_cfg.get("strict_ts0_grounded", True):
            layout_fail.append("ts0_grounded_mismatch")
        else:
            plan_level.append("ts0_grounded_mismatch")
    img = {}
    for key in ("front_depth", "front_rgb"):
        a = gen[f"timestep_0/obs/{key}"][()]
        b = ref[f"timestep_0/obs/{key}"][()]
        if a.shape != b.shape:
            img[key] = {"shape_mismatch": [list(a.shape), list(b.shape)]}
            layout_fail.append(f"ts0_{key}_shape")
            continue
        d = np.abs(a.astype(np.int64) - b.astype(np.int64))
        img[key] = {"px_diff_ratio": float((d > 0).mean()), "max": int(d.max())}
    rec["ts0_image"] = img
    ts0_cfg = tier_cfg.get("ts0_image", {"px_diff_ratio": 0.0, "depth_max": 0})
    if "front_depth" in img and "px_diff_ratio" in img["front_depth"]:
        if img["front_depth"]["px_diff_ratio"] > ts0_cfg["px_diff_ratio"] or img["front_depth"]["max"] > ts0_cfg["depth_max"]:
            layout_fail.append("ts0_depth_over_tol")
        if img["front_rgb"]["px_diff_ratio"] > ts0_cfg["px_diff_ratio"]:
            layout_fail.append("ts0_rgb_over_tol")
    if layout_fail:
        rec["reasons"].append("layout:" + ",".join(layout_fail))
        rec["category"] = "FAIL"
        return rec
    if text_semantic_mismatch and not tier_cfg.get("strict_text", True):
        plan_level.append("text:" + ",".join(text_semantic_mismatch))

    # 3. 子目标层：边界按序号对齐，去坐标文本须相同，坐标 ≤ px_tol
    def bounds(group: h5py.Group, steps: list[int]) -> list[tuple[int, str]]:
        out = []
        for t in steps:
            if bool(group[f"timestep_{t}/info/is_subgoal_boundary"][()]):
                out.append((t, _text(group[f"timestep_{t}/info/grounded_subgoal"][()])))
        return out

    bg, br = bounds(gen, tg), bounds(ref, tr)
    strip = lambda s: COORD_RE.sub("<>", s)
    sub_same = [strip(x) for _, x in bg] == [strip(x) for _, x in br]
    px_max = 0
    shift_max = 0
    for (ta, xa), (tb, xb) in zip(bg, br):
        shift_max = max(shift_max, abs(ta - tb))
        ca, cb = COORD_RE.findall(xa), COORD_RE.findall(xb)
        if len(ca) == len(cb):
            for (y1, x1), (y2, x2) in zip(ca, cb):
                px_max = max(px_max, abs(int(y1) - int(y2)), abs(int(x1) - int(x2)))
        else:
            sub_same = False
    rec["subgoal"] = {
        "boundaries": [len(bg), len(br)], "text_sequence_same": sub_same,
        "px_max": px_max, "boundary_shift_max": shift_max,
    }

    # 4. 夹爪事件层
    n = min(len(tg), len(tr))
    grip: dict[str, Any] = {}
    grip_ok = True
    seqs = {
        "is_gripper_close": (_bools(gen, tg, "obs/is_gripper_close"), _bools(ref, tr, "obs/is_gripper_close")),
    }
    for name, (path, idx) in GRIPPER_SIGN_FIELDS.items():
        seqs[name] = (np.sign(_stack(gen, tg, path)[:, idx]), np.sign(_stack(ref, tr, path)[:, idx]))
    flip_shift_max = 0
    for name, (sa, sb) in seqs.items():
        fa, fb = _flips(sa), _flips(sb)
        m = min(len(fa), len(fb))
        shift = int(np.abs(fa[:m] - fb[:m]).max()) if m else 0
        grip[name] = {"flips": [int(len(fa)), int(len(fb))], "shift_max": shift}
        if len(fa) != len(fb):
            grip_ok = False
        flip_shift_max = max(flip_shift_max, shift)
    grip["flip_shift_max"] = flip_shift_max
    grip["flip_counts_equal"] = grip_ok
    rec["gripper"] = grip

    # 5. 手臂轨迹层：公共前缀上逐帧比，允许 ±frame_delta_max 帧的错位（对每帧取各偏移下的最小差）——
    #    末段多/少 1 帧会让后续全部错位一帧，不做错位容忍会把"同一条规划"误判成 REPLAN。紧档 frame_delta_max=0 即严格逐帧。
    arm: dict[str, Any] = {}
    identical_lowdim = len(tg) == len(tr)
    shifts = range(-int(tier_cfg["frame_delta_max"]), int(tier_cfg["frame_delta_max"]) + 1)
    for name, (path, sl) in ARM_FIELDS.items():
        a_full = _stack(gen, tg, path).astype(np.float64)[:, sl]
        b_full = _stack(ref, tr, path).astype(np.float64)[:, sl]
        a = a_full[:n]
        best = None
        for s in shifts:
            # 生成侧第 t 帧对参考侧第 t+s 帧
            lo, hi = max(0, -s), min(n, len(b_full) - s)
            if hi <= lo:
                continue
            cand = np.full(a.shape, np.inf)
            cand[lo:hi] = np.abs(a[lo:hi] - b_full[lo + s:hi + s])
            best = cand if best is None else np.minimum(best, cand)
        d = best
        d[~np.isfinite(d)] = np.abs(a - b_full[:n])[~np.isfinite(d)]
        per_frame = d.max(axis=1) if d.ndim == 2 else d
        thr = tier_cfg["arm"][name]["p99"]
        over = np.flatnonzero(per_frame > thr)
        arm[name] = {
            "max": float(d.max()), "p99": float(np.percentile(d, 99)), "mean": float(d.mean()),
            "diverge_at": int(over[0]) if len(over) else None,
        }
        if not np.array_equal(_stack(gen, tg[:n], path), _stack(ref, tr[:n], path)):
            identical_lowdim = False
    rec["arm"] = arm

    # 6. 图像层：只查存在与 shape（首尾两帧）
    img_ok = True
    for path in IMAGE_FIELDS:
        for ta, tb in ((tg[0], tr[0]), (tg[-1], tr[-1])):
            ga, rb = f"timestep_{ta}/{path}", f"timestep_{tb}/{path}"
            if ga not in gen or rb not in ref or gen[ga].shape != ref[rb].shape or gen[ga].dtype != ref[rb].dtype:
                img_ok = False
    rec["images_present_same_shape"] = img_ok

    # 7. 分类
    if identical_lowdim and grip_ok and flip_shift_max == 0 and sub_same and px_max == 0 and shift_max == 0:
        # 低维全同，再做全字段按位比较判 IDENTICAL
        if _episode_bitwise_equal(gen, ref, tg):
            rec["category"] = "IDENTICAL"
            return rec
        rec["reasons"].append("bitwise:other_fields_differ")
    within = (
        not plan_level
        and abs(len(tg) - len(tr)) <= tier_cfg["frame_delta_max"]
        and all(arm[k]["p99"] <= tier_cfg["arm"][k]["p99"] and arm[k]["max"] <= tier_cfg["arm"][k]["max"] for k in ARM_FIELDS)
        and shift_max <= tier_cfg["boundary_shift_max"]
        and flip_shift_max <= tier_cfg["flip_shift_max"]
        and grip_ok and sub_same and px_max <= tier_cfg["px_tol"] and img_ok
    )
    if within:
        rec["category"] = "DRIFT"
        return rec
    why = list(plan_level)
    if abs(len(tg) - len(tr)) > tier_cfg["frame_delta_max"]:
        why.append(f"frames:{len(tg)}vs{len(tr)}")
    for k in ARM_FIELDS:
        if arm[k]["p99"] > tier_cfg["arm"][k]["p99"] or arm[k]["max"] > tier_cfg["arm"][k]["max"]:
            why.append(f"arm:{k}")
    if not sub_same:
        why.append("subgoal:text_sequence")
    if px_max > tier_cfg["px_tol"]:
        why.append(f"subgoal:px={px_max}")
    if shift_max > tier_cfg["boundary_shift_max"]:
        why.append(f"boundary_shift={shift_max}")
    if not grip_ok:
        why.append("gripper:flip_count")
    if flip_shift_max > tier_cfg["flip_shift_max"]:
        why.append(f"gripper:flip_shift={flip_shift_max}")
    if not img_ok:
        why.append("images:shape")
    rec["reasons"].append("replan:" + ",".join(why))
    rec["category"] = "REPLAN"
    return rec


_TEXT_TOLERANT = ("setup/task_goal", "setup/available_multi_choices")


def _episode_bitwise_equal(gen: h5py.Group, ref: h5py.Group, steps: list[int]) -> bool:
    """全字段按位比较（低维已相同时才调用）。生成侧可能缺条件写入字段，只比两侧都有的路径。
    指令文本两项（``setup/task_goal``、``available_multi_choices``）按合同层同一口径归一化后比，
    发布集与现行源码之间的纯标点/改写条目差异不影响 IDENTICAL 判定。"""
    names: list[str] = []
    gen.visititems(lambda n, o: names.append(n) if isinstance(o, h5py.Dataset) else None)
    for name in names:
        if name not in ref:
            continue
        a, b = gen[name], ref[name]
        if name in _TEXT_TOLERANT:
            ta, tb = _text(a[()]), _text(b[()])
            if name == "setup/task_goal":
                ta = _text(np.asarray(a[()]).reshape(-1)[0]) if a.dtype.kind == "O" and a.shape else ta
                tb = _text(np.asarray(b[()]).reshape(-1)[0]) if b.dtype.kind == "O" and b.shape else tb
            if _norm_text(ta) != _norm_text(tb):
                return False
            continue
        if a.shape != b.shape or a.dtype != b.dtype:
            return False
        if a.dtype.kind == "O":
            if _text(a[()]) != _text(b[()]):
                return False
        elif a[()].tobytes() != b[()].tobytes():
            return False
    return True


# ---------- 数据集级 ----------

def run(args: argparse.Namespace) -> int:
    generated = Path(args.generated).resolve()
    reference = Path(args.reference).resolve()
    tolerance = json.loads(Path(args.tolerance).read_text(encoding="utf-8"))
    tier, tier_source = detect_tier(tolerance, args.tier)
    tier_cfg = tolerance["tiers"][tier]

    rows = _read_generated_records(generated)
    if args.sequence:
        wanted = {tuple(item.strip().split("/")) for item in args.sequence.split(",") if item.strip()}
        wanted = {(t, int(e)) for t, e in wanted}
        rows = [r for r in rows if (r["task"], r["episode"]) in wanted]
        missing = wanted - {(r["task"], r["episode"]) for r in rows}
        if missing:
            raise CompareError(f"--sequence 里这些身份不在生成侧 metadata：{sorted(missing)}")
    if args.tasks:
        keep = set(args.tasks.split(","))
        rows = [r for r in rows if r["task"] in keep]
    rows.sort(key=lambda r: (r["task"], r["episode"]))

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    jsonl = (output / "episodes.jsonl").open("w", encoding="utf-8")
    counts = {"IDENTICAL": 0, "DRIFT": 0, "REPLAN": 0, "FAIL": 0}
    drift_p99 = {k: [] for k in ARM_FIELDS}
    drift_max = {k: [] for k in ARM_FIELDS}
    ts0_same = 0
    text_raw_mismatch_total = 0
    ts0_px_ratio_max = 0.0
    ts0_depth_max = 0
    px_max_all = 0
    shift_max_all = 0
    flip_shift_all = 0
    frame_delta_all = 0
    replan_frame_deltas: list[int] = []

    handles: dict[str, tuple[h5py.File, h5py.File]] = {}
    try:
        for row in rows:
            task, ep = row["task"], row["episode"]
            if task not in handles:
                gp = generated / f"record_dataset_{task}.h5"
                rp = reference / f"record_dataset_{task}.h5"
                if not gp.exists() or not rp.exists():
                    raise CompareError(f"缺文件：{gp if not gp.exists() else rp}")
                handles[task] = (h5py.File(gp, "r"), h5py.File(rp, "r"))
            gf, rf = handles[task]
            key = f"episode_{ep}"
            if key not in gf or key not in rf:
                rec = {"task": task, "episode": ep, "category": "FAIL", "reasons": ["missing_episode"]}
            else:
                rec = compare_episode(gf[key], rf[key], tier_cfg)
                rec.update({"task": task, "episode": ep, "seed": row["seed"], "difficulty": row["difficulty"]})
            counts[rec["category"]] += 1
            text_raw_mismatch_total += int(bool(rec.get("text_raw_mismatch")))
            if "ts0_grounded" in rec and rec["ts0_grounded"]["same"]:
                ts0_same += 1
            if "ts0_image" in rec and "px_diff_ratio" in rec["ts0_image"].get("front_depth", {}):
                ts0_px_ratio_max = max(ts0_px_ratio_max, rec["ts0_image"]["front_depth"]["px_diff_ratio"], rec["ts0_image"]["front_rgb"]["px_diff_ratio"])
                ts0_depth_max = max(ts0_depth_max, rec["ts0_image"]["front_depth"]["max"])
            if "subgoal" in rec:
                px_max_all = max(px_max_all, rec["subgoal"]["px_max"])
                shift_max_all = max(shift_max_all, rec["subgoal"]["boundary_shift_max"])
            if "gripper" in rec:
                flip_shift_all = max(flip_shift_all, rec["gripper"]["flip_shift_max"])
            if "frames" in rec:
                delta = abs(rec["frames"]["generated"] - rec["frames"]["reference"])
                frame_delta_all = max(frame_delta_all, delta)
                if rec["category"] == "REPLAN":
                    replan_frame_deltas.append(delta)
            if rec["category"] == "DRIFT":
                for k in ARM_FIELDS:
                    drift_p99[k].append(rec["arm"][k]["p99"])
                    drift_max[k].append(rec["arm"][k]["max"])
            jsonl.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if args.verbose:
                print(f"# {task}/ep{ep}: {rec['category']} {' '.join(rec.get('reasons', []))}", flush=True)
    finally:
        jsonl.close()
        for gf, rf in handles.values():
            gf.close()
            rf.close()

    compared = sum(counts.values())
    replan_rate = counts["REPLAN"] / compared if compared else 0.0
    passed = counts["FAIL"] == 0 and replan_rate <= tier_cfg["replan_max"] and compared > 0
    status = "PASS" if passed else "FAIL"
    drift_stats = {
        k: {
            "n": len(drift_p99[k]),
            "p99_max": max(drift_p99[k]) if drift_p99[k] else None,
            "max_max": max(drift_max[k]) if drift_max[k] else None,
        }
        for k in ARM_FIELDS
    }
    summary = {
        "schema": "test-vs-original-summary/1",
        "compared_at": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "tier": tier, "tier_source": tier_source, "tolerance_file": str(Path(args.tolerance).resolve()),
        "tier_config": tier_cfg,
        "generated": str(generated), "reference": str(reference),
        "compared": compared, "counts": counts, "replan_rate": replan_rate, "status": status,
        "ts0_grounded_same": ts0_same, "text_raw_mismatch_episodes": text_raw_mismatch_total,
        "ts0_image": {"px_diff_ratio_max": ts0_px_ratio_max, "depth_max": ts0_depth_max},
        "subgoal_px_max": px_max_all, "boundary_shift_max": shift_max_all, "flip_shift_max": flip_shift_all,
        "frame_delta_max": frame_delta_all, "replan_frame_deltas": replan_frame_deltas,
        "drift_arm_stats": drift_stats,
    }
    print(
        f"VS_ORIGINAL={status} tier={tier} compared={compared} identical={counts['IDENTICAL']} "
        f"drift={counts['DRIFT']} replan={counts['REPLAN']} fail={counts['FAIL']} "
        f"replan_rate={replan_rate:.4f} replan_max={tier_cfg['replan_max']}"
    )
    print("# 手臂通道 DRIFT 局 p99 最大值：" + " ".join(
        f"{k}={drift_stats[k]['p99_max']:.3g}" if drift_stats[k]["p99_max"] is not None else f"{k}=n/a" for k in ARM_FIELDS
    ) + f"（阈值 " + " ".join(f"{k}={tier_cfg['arm'][k]['p99']:.3g}" for k in ARM_FIELDS) + "）")
    print(
        f"# 布局层：ts0 grounded 相同={ts0_same}/{compared}；ts0 图像最大像素差比例={ts0_px_ratio_max:.4f}，深度 max={ts0_depth_max}；"
        f"边界坐标最大像素差={px_max_all}；边界帧号最大偏移={shift_max_all}；夹爪翻转最大偏移={flip_shift_all}；帧数最大差={frame_delta_all}"
    )
    print(f"# 指令文本仅标点/连字符差异（归一化后相同、不判 FAIL）的局数={text_raw_mismatch_total}")

    # 官方合同审计（复用 train_split_comparison，口径不变）
    if args.official_root:
        from train_split_comparison import load_official, validate_generated_subset, validate_manifest_scope

        contract, _ = load_official(args.official_root)
        records_by_task = contract.read_train_metadata(
            Path(args.official_root) / "src" / "robomme" / "env_metadata" / "train"
        )
        all_rows = _read_generated_records(generated)
        episodes_by_task = validate_manifest_scope(all_rows, records_by_task, contract.ALL_TASKS)
        contract_result = validate_generated_subset(generated, episodes_by_task, records_by_task, reference, contract)
        errors = (
            contract_result["metadata"]["error_count"]
            + contract_result["generated"]["error_count"]
            + contract_result["official"]["error_count"]
        )
        audited = contract_result["generated"]["episode_count"]
        audit_status = "PASS" if contract_result["passed"] else "FAIL"
        print(f"REFERENCE_AUDIT_COMPLETE={audit_status} compared={audited} contract_errors={errors} missing=0")
        summary["contract_audit"] = {"status": audit_status, "compared": audited, "errors": errors}
        if audit_status != "PASS":
            status = "FAIL"
            summary["status"] = status

    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"# 逐局明细 {output / 'episodes.jsonl'}；汇总 {output / 'summary.json'}")
    return 0 if status == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--generated", required=True, help="生成侧官方布局目录（merge 的输出）")
    p.add_argument("--reference", default=str(DEFAULT_REFERENCE), help="官方发布集目录")
    p.add_argument("--tolerance", default=str(DEFAULT_TOLERANCE), help="容差表 JSON")
    p.add_argument("--tier", default="auto", help="auto｜ada｜a40；auto 用 nvidia-smi 匹配")
    p.add_argument("--sequence", default=None, help="只比这些身份：Task/ep,Task/ep,…（默认比生成侧 metadata 里全部）")
    p.add_argument("--tasks", default=None, help="只比这些 task（逗号分隔）")
    p.add_argument("--official-root", default=None, help="给了就同时跑官方合同审计（REFERENCE_AUDIT_COMPLETE 行）")
    p.add_argument("--label", default="", help="写进 summary 的自由标签（机器/规模/worker 数）")
    p.add_argument("--output", required=True, help="结果目录（episodes.jsonl + summary.json）")
    p.add_argument("--verbose", action="store_true", help="逐局打印分类")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code = run(args)
    except CompareError as exc:
        print(f"VS_ORIGINAL=ERROR {exc}", file=sys.stderr)
        code = 2
    print(f"EXIT_CODE={code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
