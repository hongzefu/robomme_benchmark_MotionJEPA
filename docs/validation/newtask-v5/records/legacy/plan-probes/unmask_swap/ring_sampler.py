"""外环采样的推广版：与仓库 unmask_swap_xhard.sample_distractors 同一取值顺序与接受判据，
只把「max(|x|,|y|) ∈ [inner, outer]」换成任意环形区域（矩形环），并允许 count 任意。

取值顺序（与仓库一致）：n_with_cube randint → 色池 randperm → 逐容器 [每次尝试 x,y,yaw 三次 rand → 判据]。
V5 外部交换新增的取值（发起者）一律追加在全部放置之后（N5）。
"""
from __future__ import annotations

import numpy as np
import torch

from robomme.robomme_env.utils import unmask_swap_xhard as ux
from robomme.robomme_env.utils.bin_collision import ObjectState, bin_actor_pose, bin_shape_specs, check_swap_sweep

CUBE_HALF = 0.02
RADIUS = ux.bin_footprint_radius(CUBE_HALF)  # 0.04243
SHAPES = bin_shape_specs(CUBE_HALF)


class Ring:
    """矩形环：中心落在 outer 矩形内且不在 inner 矩形内（闭/开边界与仓库 in_ring 同向）。"""

    def __init__(self, name, inner, outer):
        self.name = name
        self.inner = inner  # (x0, x1, y0, y1)
        self.outer = outer

    def contains(self, x, y):
        ox0, ox1, oy0, oy1 = self.outer
        ix0, ix1, iy0, iy1 = self.inner
        if not (ox0 <= x <= ox1 and oy0 <= y <= oy1):
            return False
        return not (ix0 < x < ix1 and iy0 < y < iy1)

    def inside_inner(self, x, y):
        ix0, ix1, iy0, iy1 = self.inner
        return ix0 < x < ix1 and iy0 < y < iy1


V4_RING = Ring("v4", (-0.2675, 0.2675, -0.2675, 0.2675), (-0.45, 0.45, -0.45, 0.45))
# V4 外环向内收一个弯道侧移 0.07（中心带 [0.3375, 0.45]），相机可见判据半径同样 +0.07：
# 让任意方向的弯道都留在环带内、画面内（静态放置约束，只是候选变少）
V4PAD_RING = Ring("v4pad", (-0.3375, 0.3375, -0.3375, 0.3375), (-0.45, 0.45, -0.45, 0.45))


def tight_ring(task, gap=0.04):
    """紧贴内部锚点范围的矩形环（假设口径见报告）：
    内边界 = 内部容器中心范围 + 容器外廓半边 0.03（内部容器）+ 0.03（干扰容器）+ gap；
    宽度 = 一个容器外廓 0.06 + gap。
    内部容器中心范围（理论值）：VUS 旋转 region4，锚点半径 ≤ 0.1414，盒内偏移 ±0.0425 ⇒ 圆盘半径 0.2015；
    BUS 四点锚 x∈{0,0.1}、y∈{-0.1,0.1}+[0,0.1]，盒内偏移 ±0.0425 ⇒ x∈[-0.0425,0.1425]、y∈[-0.1425,0.2425]。
    """
    pad_in = 0.03 + 0.03 + gap
    width = 0.06 + gap
    if task == "VideoUnmaskSwap":
        c = (-0.2015, 0.2015, -0.2015, 0.2015)
    else:
        c = (-0.0425, 0.1425, -0.1425, 0.2425)
    inner = (c[0] - pad_in, c[1] + pad_in, c[2] - pad_in, c[3] + pad_in)
    outer = (inner[0] - width, inner[1] + width, inner[2] - width, inner[3] + width)
    return Ring(f"tight_gap{gap}", inner, outer)


def state(name, x, y, yaw):
    p, q = bin_actor_pose([x, y], yaw, CUBE_HALF)
    return ObjectState(name=name, p=p, q=q, shapes=SHAPES)


S_GRID = np.linspace(0.0, 1.0, 401)


def _sweep_paths(sa, sb, lane=0.07):
    a, b = sa.p[:2], sb.p[:2]
    d = b - a
    n = np.array([-d[1], d[0]])
    nn = np.linalg.norm(n)
    n = n / nn if nn > 1e-9 else np.zeros(2)
    s = S_GRID[:, None]
    off = lane * np.sin(np.pi * s)
    v = float(np.linalg.norm(d)) + lane * np.pi
    return a + d * s + n * off, b - d * s - n * off, v


def circle_certified_static(paths, xy):
    """静止候选对一段扫掠：外接圆中心距在 401 个 s 上都大于 2r + 相邻采样最大位移/2 ⇒ 严格证明分离。"""
    pa, pb, v = paths
    margin = v * (S_GRID[1] - S_GRID[0]) / 2
    dmin = min(float(np.min(np.linalg.norm(pa - xy, axis=1))), float(np.min(np.linalg.norm(pb - xy, axis=1))))
    return dmin - 2 * RADIUS > margin


def sample_ring(gen, *, ring, count, obstacles, sweeps, min_gap=0.04, with_cube_range=(1, 2), max_trials=512,
                check_static_sweeps=True, fast=True, vis_radius=None):
    """返回 placements [(x,y,yaw)]；放不满返回 None（对应仓库抛 SceneGenerationError）。

    fast=True：先用外接圆严格判据跳过必然分离的扫掠，只对有风险的段调仓库 check_swap_sweep；
    接受/拒绝的判定与逐段全调仓库相同（只跳过已证明分离的段），因此随机流消耗相同。
    """
    sweep_paths = [_sweep_paths(a, b) for a, b in sweeps] if fast else None
    lo, hi = with_cube_range
    int(torch.randint(lo, hi + 1, (1,), generator=gen).item())
    torch.randperm(3, generator=gen)
    ox0, ox1, oy0, oy1 = ring.outer
    occupied = [(np.asarray(xy, dtype=np.float64)[:2], float(r)) for xy, r in obstacles]
    placements = []
    for i in range(count):
        chosen = None
        for _ in range(max_trials):
            # 与仓库同式：(rand*2-1)*outer 在对称方框里均匀抽；矩形环改为在外矩形里均匀抽
            if ring.name == "v4":  # 与仓库逐式相同，保证 count=3 时与仓库逐值一致
                x = float((torch.rand(1, generator=gen).item() * 2.0 - 1.0) * ox1)
                y = float((torch.rand(1, generator=gen).item() * 2.0 - 1.0) * oy1)
            else:
                x = float(torch.rand(1, generator=gen).item() * (ox1 - ox0) + ox0)
                y = float(torch.rand(1, generator=gen).item() * (oy1 - oy0) + oy0)
            yaw = float(torch.rand(1, generator=gen).item() * 90.0)
            if not ring.contains(x, y):
                continue
            if not ux.visible_on_camera(x, y, RADIUS if vis_radius is None else vis_radius):
                continue
            here = np.array([x, y])
            if any(np.linalg.norm(here - xy) < r + RADIUS + min_gap for xy, r in occupied):
                continue
            if check_static_sweeps and sweeps:
                cand = state(f"distractor_bin_{i}", x, y, yaw)
                if any((not fast or not circle_certified_static(sweep_paths[k], here))
                       and check_swap_sweep(a, b, [cand], sweep_index=k, stage="distractor")[1] is not None
                       for k, (a, b) in enumerate(sweeps)):
                    continue
            chosen = (x, y, yaw)
            break
        if chosen is None:
            return None
        placements.append(chosen)
        occupied.append((np.array(chosen[:2]), RADIUS))
    return placements
