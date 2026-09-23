"""两个 UnmaskSwap 环境（VideoUnmaskSwap / ButtonUnmaskSwap）xhard 档的共用件。

依据 NEWTASK_RELEASE_V4_PLAN 2.7①③、2.10、2.11、2.21：

* **交换窗口**：原三档每段交换 50 步、首段起点 64；xhard 的 swap 速度 ×1.5（B4）
  ⇒ ``round(50 / 1.5) = 33`` 步一段，起点 64 不变。:func:`scaled_window_steps` 在倍率为 1 时
  **原样返回整数基数**，原三档的调度与改动前逐项相同。
* **干扰容器**（B3 / B13 / H1）：3 个额外容器放在现 region 之外的外环
  ``max(|x|,|y|) ∈ [0.2675, 0.45]``、相机可见处，1~2 个内含「其他颜色」方块（B2 色池），
  单独存 ``distractor_bins``，**不进 ``spawned_bins``**（天然不被选作交换搭档、不进揭示动画、
  不进最近邻），但**必须进碰撞检查**：本模块在 reset 时按确定性的交换序列预演每一段扫掠，
  候选位置与任何一段扫掠相交就拒绝重抽；运行时的初态与扫掠检查另由环境显式并入干扰容器。
* **随机流（N5）**：干扰容器的全部抽样走**独立的专用流**（种子 = 本局 seed + 固定盐），
  主流一次都不多抽——原三档根本不进这里，xhard 的主流取值序列也与不加干扰容器时相同。

本模块只在 ``difficulty == "xhard"`` 分支被调用；原三档从不 import 这里的函数参与取值。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import torch

from .bin_collision import (
    ObjectState,
    bin_actor_pose,
    bin_shape_specs,
    check_swap_sweep,
    object_state_from_actor,
)
from .SceneGenerationError import SceneGenerationError
from .xhard import DISTRACTOR_COLORS

# ── 交换窗口（B4）──────────────────────────────────────────────────────────────
#: 首段交换的起点（控制步）；原三档与 xhard 相同，预交换锁定段 [0, 64) 的终点必须等于它。
SWAP_WINDOW_START = 64
#: 原三档每段交换的步数（速度倍率 1）。
SWAP_WINDOW_STEPS = 50
#: xhard 的交换速度倍率（用户原文「swap 速度 x1.5」）。
XHARD_SWAP_SPEED_MULTIPLIER = 1.5


def scaled_window_steps(base_steps: int, multiplier) -> int:
    """按速度倍率把每段交换步数取整：``round(base / multiplier)``。

    倍率恰为 1 时不做浮点运算、原样返回 ``int(base_steps)``，保证原三档逐字不变。
    """
    m = float(multiplier)
    if not math.isfinite(m) or m <= 0:
        raise ValueError(f"swap_speed_multiplier 必须是正有限数，收到 {multiplier!r}")
    if m == 1.0:
        return int(base_steps)
    steps = int(round(float(base_steps) / m))
    if steps < 1:
        raise ValueError(f"倍率 {multiplier} 使每段交换步数小于 1")
    return steps


# ── 干扰容器（B3 / B13）────────────────────────────────────────────────────────
#: decision.xhard.distractor 的申报值（两个环境共用同一份）。
XHARD_DISTRACTOR = {
    # 额外容器个数（B3：3 个）
    "count": 3,
    # 其中装方块的个数，闭区间（B13：3 个里 1~2 个有）
    "with_cube_range": [1, 2],
    # 外环 max(|x|,|y|) 的上下界（B13 实测推荐值）
    "ring_half_extent": [0.2675, 0.45],
    # 干扰容器外接圆与其他对象外接圆之间的最小间隙，米（B13 推导外环下界时用的 min_gap）
    "min_gap": 0.04,
    # 方块颜色池（B2：黄／青／品红，全局共用）
    "colors": [item["name"] for item in DISTRACTOR_COLORS],
}

#: 干扰容器每个的拒绝采样预算；用尽即抛 SceneGenerationError（2.2④：不许静默截断）。
DISTRACTOR_MAX_TRIALS = 512
#: 专用随机流的种子盐：种子 = seed + 盐，与主流完全分开（N5）。
DISTRACTOR_STREAM_SALT = 0x5D157AC7

# 相机可见 ∩ 桌面（B13 实测表，前视相机 eye=[0.3,0,0.4]、target=[0,0,-0.2]、fov 90°）：
# x ≤ 0.43；可见 y 半宽随 x 线性收窄，表中 7 个点可由 0.49 − 0.45·x 逐点复现（误差 ≤ 0.005）。
VISIBLE_X_MAX = 0.43
VISIBLE_Y_AT_X0 = 0.49
VISIBLE_Y_SLOPE = 0.45


def bin_footprint_radius(cube_half_size: float) -> float:
    """容器外廓（正方形）外接圆半径；与 build_bin 同源：外廓半边 = (2.5·h + 0.005)/2。"""
    half = (cube_half_size * 2.5 + 0.005) * 0.5
    return half * math.sqrt(2.0)


def visible_on_camera(x: float, y: float, radius: float) -> bool:
    """以外接圆保守判断整个容器落在前视相机可见 ∩ 桌面内。"""
    far_x = x + radius
    if far_x > VISIBLE_X_MAX:
        return False
    return abs(y) + radius <= VISIBLE_Y_AT_X0 - VISIBLE_Y_SLOPE * far_x


def distractor_generator(seed: int) -> torch.Generator:
    """干扰容器专用随机流（N5：主流一次都不多抽）。"""
    generator = torch.Generator()
    generator.manual_seed((int(seed) + DISTRACTOR_STREAM_SALT) % (2**63))
    return generator


def predict_swap_sweeps(env, partner_axes: Sequence[int]) -> list[tuple[ObjectState, ObjectState]]:
    """按 ``step`` 的同一语义预演全部交换段，返回每段起态 ``(发起者, 搭档)``。

    发起者取 ``swap_pair{k}_idx1``；搭档是交换开始时 XY 最近的另一个 ``spawned_bins``
    （严格小于、并列取生成序靠前者，与 ``step`` 的扫描一致）；每段结束后两者位姿互换
    （``swap_flat_two_lane`` 的终态：位置与四元数都换到对方的起态）。干扰容器不在
    ``spawned_bins`` 里，因此不影响搭档选择——预演结果与是否有干扰容器无关。
    """
    bins = list(env.spawned_bins)
    states = [object_state_from_actor(actor, f"bin_{index}") for index, actor in enumerate(bins)]
    positions = [np.asarray(env._get_actor_position(actor), dtype=np.float32) for actor in bins]
    axes = list(partner_axes)
    sweeps = []
    for k in range(int(env.swap_times)):
        initiator = getattr(env, f"swap_pair{k + 1}_idx1")
        a = next(index for index, actor in enumerate(bins) if actor is initiator)
        b, best = None, float("inf")
        for index, position in enumerate(positions):
            if index == a:
                continue
            dist = np.linalg.norm(positions[a][axes] - position[axes])
            if dist < best:
                b, best = index, dist
        if b is None:
            break
        sweeps.append((states[a], states[b]))
        state_a, state_b = states[a], states[b]
        states[a] = ObjectState(name=state_a.name, p=state_b.p.copy(), q=state_b.q.copy(), shapes=state_a.shapes)
        states[b] = ObjectState(name=state_b.name, p=state_a.p.copy(), q=state_a.q.copy(), shapes=state_b.shapes)
        positions[a], positions[b] = positions[b].copy(), positions[a].copy()
    return sweeps


def sample_distractors(
    *,
    generator: torch.Generator,
    cfg: dict,
    obstacles: Sequence[tuple[Sequence[float], float]],
    sweeps: Sequence[tuple[ObjectState, ObjectState]],
    recorder,
    cube_half_size: float,
) -> dict[str, Any]:
    """在外环里拒绝采样全部干扰容器位置，返回 ``{"placements": [...], "cube_colors": [...]}``。

    ``obstacles``：已在场对象的 ``(xy, 外接圆半径)``（容器、按钮等）；
    ``sweeps``：:func:`predict_swap_sweeps` 的结果，候选与任一段扫掠相交即拒绝（H1）。
    每个取值点都经 ``recorder``（SpecRecorder）走一遍；请求数与实际数不等直接抛错。
    """
    lo, hi = (int(v) for v in cfg["with_cube_range"])
    count = int(cfg["count"])
    if not 0 <= lo <= hi <= count:
        raise ValueError(f"with_cube_range {cfg['with_cube_range']} 必须落在 [0, count={count}] 内")
    inner, outer = (float(v) for v in cfg["ring_half_extent"])
    min_gap = float(cfg["min_gap"])
    pool = list(cfg["colors"])
    known = {item["name"] for item in DISTRACTOR_COLORS}
    if not set(pool) <= known:
        raise ValueError(f"干扰色 {pool} 超出全局色池 {sorted(known)}")

    n_with_cube = recorder.value(
        "objects.distractors.n_with_cube",
        int(torch.randint(lo, hi + 1, (1,), generator=generator).item()),
        decision_key="xhard.distractor.with_cube_range",
    )
    order = torch.randperm(len(pool), generator=generator).tolist()
    cube_colors = recorder.value(
        "objects.distractors.cube_colors",
        [pool[i] for i in order][: int(n_with_cube)],
        decision_key="xhard.distractor.colors",
    )

    radius = bin_footprint_radius(cube_half_size)
    shapes = bin_shape_specs(cube_half_size)
    occupied = [(np.asarray(xy, dtype=np.float64)[:2], float(r)) for xy, r in obstacles]
    recorder.record("layout.distractors_requested", count)
    placements = []
    for i in range(count):
        chosen = None
        for _trial in range(DISTRACTOR_MAX_TRIALS):
            x = float((torch.rand(1, generator=generator).item() * 2.0 - 1.0) * outer)
            y = float((torch.rand(1, generator=generator).item() * 2.0 - 1.0) * outer)
            yaw = float(torch.rand(1, generator=generator).item() * 90.0)
            if max(abs(x), abs(y)) < inner:
                continue
            if not visible_on_camera(x, y, radius):
                continue
            here = np.array([x, y], dtype=np.float64)
            if any(np.linalg.norm(here - xy) < r + radius + min_gap for xy, r in occupied):
                continue
            p, q = bin_actor_pose([x, y], yaw, cube_half_size)
            candidate = ObjectState(name=f"distractor_bin_{i}", p=p, q=q, shapes=shapes)
            if any(check_swap_sweep(a, b, [candidate], sweep_index=k, stage="distractor")[1] is not None
                   for k, (a, b) in enumerate(sweeps)):
                continue
            chosen = (x, y, yaw)
            break
        if chosen is None:
            raise SceneGenerationError(
                f"干扰容器 {i} 在 {DISTRACTOR_MAX_TRIALS} 次尝试内找不到合法位置（外环 {inner}~{outer}）"
            )
        x, y, yaw = recorder.value(f"layout.distractors.{i}", list(chosen))
        placements.append({"xy": [float(x), float(y)], "yaw_deg": float(yaw)})
        occupied.append((np.array([x, y], dtype=np.float64), radius))
    recorder.record("layout.distractors_placed", len(placements))
    if len(placements) != count:
        raise SceneGenerationError(f"干扰容器请求 {count} 个、实际 {len(placements)} 个")
    return {"placements": placements, "cube_colors": list(cube_colors)}


def build_distractors(env, layout: dict, build_bin, spawn_fixed_cube, cube_divisor: float = 1.2):
    """按 :func:`sample_distractors` 的结果建干扰容器与方块；前 ``len(cube_colors)`` 个容器装方块。

    命名一律 ``distractor_bin_<i>`` / ``distractor_cube_<色名>``，**不设 ``bin_<i>`` 属性**，
    避免被按 ``bin_<i>`` 扫描的揭示／交换逻辑误收。
    """
    rgba = {item["name"]: item["rgba"] for item in DISTRACTOR_COLORS}
    bins, cubes = [], []
    for i, entry in enumerate(layout["placements"]):
        x, y = entry["xy"]
        bins.append(build_bin(env, callsign=f"distractor_bin_{i}", position=[x, y, 0.002],
                              z_rotation_deg=entry["yaw_deg"]))
    for i, color in enumerate(layout["cube_colors"]):
        x, y = layout["placements"][i]["xy"]
        cubes.append(spawn_fixed_cube(
            env,
            position=[x, y],
            half_size=env.cube_half_size / cube_divisor,
            color=rgba[color],
            name_prefix=f"distractor_cube_{color}",
            yaw=0.0,
            dynamic=True,
        ))
    return bins, cubes
