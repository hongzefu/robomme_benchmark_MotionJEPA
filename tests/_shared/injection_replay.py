"""固定碰撞案例的轨迹重算（NEW_VALUE_INJECTION_TEST_PLAN 第 5.7 节 ``COLLISION_REPRODUCE``）。

从 ``manifest.json::cases[].initial`` 用**当前实现**独立重算原交换轨迹，与保存的 51 步
位姿、SAT 判定值、最危险对象对与形状对逐步核对。

⚠ 这里只做「从初态重算轨迹」这一条证据链。计划要求的第二条——「从保存轨迹重渲染」——
需要 SAPIEN 渲染，单列为 ``--mode render``，本模块不做。
⚠ 只读原目录，绝不写入：复现产物一律落新目录，输出目录已存在即拒绝。
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from robomme.robomme_env.utils import bin_collision as bc

#: 原诊断固定的容器／方块半尺寸来源，与 `native_sampling` 的 `cube_half_size` 同值。
CUBE_HALF_SIZE = 0.02
#: 位姿与判定值的对照容差。保存的是 float32 位姿，实测差在 1e-9 量级，1e-6 留足余量。
REPLAY_TOL = 1e-6


def _shapes_for(shape_count: int) -> tuple[bc.ShapeSpec, ...]:
    """按盒体数还原对象类型：容器 6 个盒体、方块 1 个。"""
    if shape_count == 6:
        return bc.bin_shape_specs(CUBE_HALF_SIZE)
    if shape_count == 1:
        return bc.cube_shape_specs(CUBE_HALF_SIZE)
    raise ValueError(f"未知的盒体数 {shape_count}，只认容器 6 与方块 1")


def _infer_swap_pair(records: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """从首末两步的位置差推断交换的是哪两个对象。

    案例清单没有显式记交换对（只记了最危险对象对），但交换双方是唯一位置发生变化的两个，
    首末对照即可唯一确定，比把「0↔1」写死在代码里更稳。
    """
    first = records[0]["poses"]
    last = records[-1]["poses"]
    moved = [
        index for index in range(len(first))
        if np.linalg.norm(np.asarray(first[index]["p"]) - np.asarray(last[index]["p"])) > 1e-6
    ]
    if len(moved) != 2:
        raise ValueError(f"首末位置差认出了 {len(moved)} 个移动对象，应为 2 个")
    return moved[0], moved[1]


def _exhaustive_min(states: Sequence[bc.ObjectState]) -> tuple[float, tuple[int, int], tuple[int, int]]:
    """全场最小 SAT 判定值，以及取到它的对象对与形状对。

    ⚠ 必须用全量（不粗筛）：要逐步对照保存下来的 ``sat_gap_m``，粗筛跳过的对象对
    虽然安全但没有精算值，会让最小值对不上。
    """
    best = math.inf
    best_pair = (-1, -1)
    best_shapes = (-1, -1)
    for i in range(len(states)):
        rot_i = bc.quat_to_matrix(states[i].q)
        for j in range(i + 1, len(states)):
            rot_j = bc.quat_to_matrix(states[j].q)
            for si, shape_i in enumerate(states[i].shapes):
                box_i = bc._world_box(states[i].p, rot_i, shape_i)
                for sj, shape_j in enumerate(states[j].shapes):
                    gap = bc.sat_gap(*box_i, *bc._world_box(states[j].p, rot_j, shape_j))
                    if gap < best:
                        best, best_pair, best_shapes = gap, (i, j), (si, sj)
    return float(best), best_pair, best_shapes


def replay_case(case: dict[str, Any], *, epsilon: float) -> dict[str, Any]:
    """重算一个案例的全部控制步并与保存记录逐步核对。"""
    records = case["records"]
    steps = len(records)
    initial = case["initial"]
    shapes = [_shapes_for(count) for count in case["shape_count"]]
    a, b = _infer_swap_pair(records)

    xy_a = np.asarray(initial[a]["p"][:2], dtype=np.float64)
    xy_b = np.asarray(initial[b]["p"][:2], dtype=np.float64)
    q_a = np.asarray(initial[a]["q"], dtype=np.float64)
    q_b = np.asarray(initial[b]["q"], dtype=np.float64)
    delta = xy_b - xy_a
    normal = np.array([-delta[1], delta[0]], dtype=np.float64)
    norm = float(np.linalg.norm(normal))
    normal = normal / norm if norm > bc.COINCIDENT_XY else np.zeros(2)

    pose_diffs: list[float] = []
    gap_diffs: list[float] = []
    pair_mismatches: list[dict[str, Any]] = []
    first_reject_step: int | None = None

    for step in range(steps):
        # 复刻 swap_flat_two_lane：alpha 先归一化再 smoothstep，弯道侧移 0.07·sin(πs)
        u = step / max(1, steps - 1)
        s = u * u * (3.0 - 2.0 * u)
        offset = bc.LANE_OFFSET * math.sin(math.pi * s)
        moved_xy = {
            a: xy_a + delta * s + normal * offset,
            b: xy_b - delta * s - normal * offset,
        }
        moved_q = {
            a: bc._quat_at(q_a, q_b, s),
            b: bc._quat_at(q_b, q_a, s),
        }

        states: list[bc.ObjectState] = []
        for index, entry in enumerate(initial):
            if index in moved_xy:
                p = np.array([moved_xy[index][0], moved_xy[index][1], entry["p"][2]], dtype=np.float64)
                q = moved_q[index]
            else:
                p = np.asarray(entry["p"], dtype=np.float64)
                q = np.asarray(entry["q"], dtype=np.float64)
            states.append(bc.ObjectState(name=f"obj_{index}", p=p, q=q, shapes=shapes[index]))

        saved = records[step]
        for index, entry in enumerate(saved["poses"]):
            pose_diffs.append(float(np.linalg.norm(states[index].p - np.asarray(entry["p"], dtype=np.float64))))

        gap, pair, shape_pair = _exhaustive_min(states)
        gap_diffs.append(abs(gap - float(saved["sat_gap_m"])))
        if list(pair) != list(saved["pair"]) or list(shape_pair) != list(saved["shape_pair"]):
            pair_mismatches.append(
                {"step": step, "recomputed_pair": list(pair), "saved_pair": saved["pair"],
                 "recomputed_shape_pair": list(shape_pair), "saved_shape_pair": saved["shape_pair"]}
            )
        if first_reject_step is None and gap <= epsilon:
            first_reject_step = step

    status = "REJECT" if first_reject_step is not None else "PASS"
    min_gap = min(float(item["sat_gap_m"]) for item in records)
    recomputed_min = min_gap  # 保存值的最小；重算值的最小由 gap_diffs 的一致性间接保证
    return {
        "id": case["id"],
        "swap_pair": [a, b],
        "steps": steps,
        "max_pose_diff_m": max(pose_diffs) if pose_diffs else 0.0,
        "max_gap_diff_m": max(gap_diffs) if gap_diffs else 0.0,
        "pair_mismatches": pair_mismatches,
        "saved_status": case["status"],
        "recomputed_status": status,
        "saved_first_reject_step": case["first_reject_step"],
        "recomputed_first_reject_step": first_reject_step,
        "saved_min_sat_gap_m": case["min_sat_gap_m"],
        "saved_records_min_m": recomputed_min,
        "passed": (
            max(pose_diffs, default=0.0) <= REPLAY_TOL
            and max(gap_diffs, default=0.0) <= REPLAY_TOL
            and not pair_mismatches
            and status == case["status"]
            and first_reject_step == case["first_reject_step"]
        ),
    }


def verify_source_files(root: Path) -> dict[str, Any]:
    """核 21 个文件散列，并**显式报告**几何来源的散列漂移，不隐瞒。"""
    checks = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
    bad = []
    for name, expected in checks.items():
        target = root / name
        if not target.is_file() or target.is_symlink():
            bad.append(f"{name}: 缺文件或是符号链接")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            bad.append(f"{name}: 散列不符")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    drift = []
    repo_root = Path(__file__).resolve().parents[2]
    for rel, expected in (manifest.get("geometry_sources") or {}).items():
        path = repo_root / rel
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != expected:
            drift.append({"path": rel, "recorded": expected, "current": actual})
    return {
        "files_checked": len(checks),
        "file_problems": bad,
        "geometry_source_drift": drift,
        "checksums_sha256": hashlib.sha256((root / "checksums.json").read_bytes()).hexdigest(),
    }
