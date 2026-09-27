"""纯 numpy/torch 复刻两个 UnmaskSwap xhard 的布局抽样与内部交换序列（只读，不改仓库）。

复刻对象：
* VideoUnmaskSwap.__init__/_load_scene 的主流取值顺序（n_swaps、n_picks、region3_choice、rotate_points_random、
  4×spawn_random_bin、color_order、selected、target_choice、swap_initiator_indices、swap_initiator_third）；
* ButtonUnmaskSwap 同上（两按钮各 rand(2)、y/x 偏移 8 次 rand、region3_choice、4×spawn_random_bin ...）；
* 干扰容器：直接调仓库 unmask_swap_xhard.sample_distractors（专用流）；
* 交换预演：仓库 predict_swap_sweeps 的同一语义（发起者按 swap_indices[k%3] 循环，搭档 = XY 最近邻，
  严格小于、并列取生成序靠前者；交换后位姿互换）。

spawn_random_bin 的障碍 OBB 近似为「容器外廓正方形半边 0.03（按 world yaw 旋转）外扩 min_gap」，
按钮 OBB 为 create_button_obb 的轴对齐正方形（半边 0.05625，不外扩）。与真实 get_actor_obb 的差别只影响
极少数贴边试次；用 specs.jsonl 的 20 行逐值核对复刻精度。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path("/data/hongzefu/robomme_v5_probe_wt")
sys.path.insert(0, str(REPO / "src"))

from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402
from robomme.robomme_env.utils.bin_collision import (  # noqa: E402
    ObjectState,
    bin_actor_pose,
    bin_shape_specs,
    quat_to_matrix,
)
from robomme.robomme_env.utils.episode_spec import SpecRecorder  # noqa: E402

CUBE_HALF = 0.02
BIN_HALF = (CUBE_HALF * 2.5 + 0.005) * 0.5  # spawn_random_bin 的 bin_half_size = 0.0275
OUTER_HALF = CUBE_HALF * 2.5 * 0.5 + 0.005  # 外廓半边 0.03
SHAPES = bin_shape_specs(CUBE_HALF)
SPECS_PATH = REPO / "scripts/configs/newtask-v4/v4-01/specs.jsonl"


def bin_state(name, x, y, yaw_deg):
    p, q = bin_actor_pose([x, y], yaw_deg, CUBE_HALF)
    return ObjectState(name=name, p=p, q=q, shapes=SHAPES)


def _world_yaw_axes(yaw_deg):
    """build_bin 的 Rx(pi)Rz(yaw) 下，局部 x/y 轴在世界 XY 的投影（列为轴）。"""
    _, q = bin_actor_pose([0, 0], yaw_deg, CUBE_HALF)
    rot = quat_to_matrix(q)
    u = rot[:2, 0] / np.linalg.norm(rot[:2, 0])
    v = rot[:2, 1] / np.linalg.norm(rot[:2, 1])
    return np.stack([u, v], axis=1)


def spawn_random_bin_replica(gen, obbs, region_center, region_half, min_gap, yaw_scale=90.0, max_trials=256):
    cx, cy = float(region_center[0]), float(region_center[1])
    x_low, x_high = cx - region_half + BIN_HALF, cx + region_half - BIN_HALF
    y_low, y_high = cy - region_half + BIN_HALF, cy + region_half - BIN_HALF
    reach = BIN_HALF + min_gap
    for _ in range(max_trials):
        x = float(torch.rand(1, generator=gen).item() * (x_high - x_low) + x_low)
        y = float(torch.rand(1, generator=gen).item() * (y_high - y_low) + y_low)
        pos = np.array([x, y])
        hit = False
        for c, A, h in obbs:
            local = A.T @ (pos - c)
            closest = c + A @ np.clip(local, -h, h)
            if np.linalg.norm(pos - closest) < reach:
                hit = True
                break
        if hit:
            continue
        yaw = float(torch.rand(1, generator=gen).item() * yaw_scale)
        return x, y, yaw
    return None


def _bin_obb(x, y, yaw, pad):
    return (np.array([x, y]), _world_yaw_axes(yaw), np.array([OUTER_HALF + pad, OUTER_HALF + pad]))


def _tail_draws(gen, n_bins):
    """color_order、selected、target_choice、swap_initiator_indices、swap_initiator_third（两环境相同）。"""
    color_order = torch.randperm(3, generator=gen).tolist()
    selected = torch.randperm(3, generator=gen)[: min(3, n_bins)].tolist()
    target_choice = int(torch.randint(len(selected), (1,), generator=gen).item())
    init_idx = torch.randperm(len(selected), generator=gen)[:2].tolist()
    remaining = [i for i in range(n_bins) if i not in init_idx]
    third = remaining[torch.randint(0, len(remaining), (1,), generator=gen).item()]
    return dict(color_order=color_order, selected=selected, target_choice=target_choice,
                swap_initiator_indices=init_idx, swap_initiator_third=third)


def vus_layout(seed, swap_range=(8, 12)):
    g0 = torch.Generator(); g0.manual_seed(seed)
    n_swaps = int(torch.randint(swap_range[0], swap_range[1] + 1, (1,), generator=g0).item())
    gen = torch.Generator(); gen.manual_seed(seed)
    type_choice = int(torch.randint(0, 2, (1,), generator=gen).item())
    region4 = [[-0.05, -0.1], [-0.05, 0.1], [0.1, 0.1], [0.1, -0.1]]
    pts = torch.tensor(region4, dtype=torch.float32)
    angle = torch.rand(1, generator=gen) * (180 - 0) + 0
    c, s = torch.cos(angle), torch.sin(angle)
    rot = torch.tensor([[c, -s], [s, c]], dtype=pts.dtype).squeeze()
    region = torch.matmul(pts, rot.T).tolist()
    bins, obbs = [], []
    for i in range(4):
        out = spawn_random_bin_replica(gen, obbs, region[i], 0.07, CUBE_HALF * 1)
        if out is None:
            break
        bins.append(out)
        obbs.append(_bin_obb(*out, CUBE_HALF * 1))
    if len(bins) < 4:
        return dict(task="VideoUnmaskSwap", seed=seed, bins=bins, spawn_fail=True)
    tail = _tail_draws(gen, len(bins))
    return dict(task="VideoUnmaskSwap", seed=seed, n_swaps=n_swaps, bins=bins, type_choice=type_choice,
                theta=float(angle.item()), buttons=[], **tail)


def bus_layout(seed, swap_range=(6, 8)):
    g0 = torch.Generator(); g0.manual_seed(seed)
    n_swaps = int(torch.randint(swap_range[0], swap_range[1] + 1, (1,), generator=g0).item())
    gen = torch.Generator(); gen.manual_seed(seed)
    buttons = []
    for center in ([-0.2, -0.1], [-0.2, 0.1]):
        off = torch.rand(2, generator=gen) - 0.5
        buttons.append((center[0] + float(off[0]) * 0.05, center[1] + float(off[1]) * 0.05))
    y1 = torch.rand(1, generator=gen).item() * 0.1
    y2 = torch.rand(1, generator=gen).item() * 0.1
    region4 = [[0, -0.1 + y1], [0, 0.1 + y1], [0.1, 0.1 + y2], [0.1, -0.1 + y2]]
    for _ in range(6):
        torch.rand(1, generator=gen)
    type_choice = int(torch.randint(0, 2, (1,), generator=gen).item())
    half_btn = 0.025 * 1.5 * 1.5
    obbs = [(np.array(b, dtype=np.float64), np.eye(2), np.array([half_btn, half_btn])) for b in buttons]
    bins = []
    for i in range(4):
        out = spawn_random_bin_replica(gen, obbs, region4[i], 0.07, CUBE_HALF * 1)
        if out is None:
            break
        bins.append(out)
        obbs.append(_bin_obb(*out, CUBE_HALF * 1))
    if len(bins) < 4:
        return dict(task="ButtonUnmaskSwap", seed=seed, bins=bins, spawn_fail=True)
    tail = _tail_draws(gen, len(bins))
    return dict(task="ButtonUnmaskSwap", seed=seed, n_swaps=n_swaps, bins=bins, type_choice=type_choice,
                buttons=buttons, **tail)


def initiators(layout):
    idx = list(layout["swap_initiator_indices"]) + [layout["swap_initiator_third"]]
    return [idx[k % 3] for k in range(layout["n_swaps"])]


def nearest(positions, a, candidates=None):
    best, best_d = None, float("inf")
    for j, p in enumerate(positions):
        if j == a or (candidates is not None and j not in candidates):
            continue
        d = float(np.linalg.norm(np.asarray(positions[a][:2], dtype=np.float32) - np.asarray(p[:2], dtype=np.float32)))
        if d < best_d:
            best, best_d = j, d
    return best, best_d


def inner_sequence(layout):
    """返回每段 (a, b, dist, 起态位置表, 起态 yaw 表)；位置/yaw 在交换后互换。"""
    pos = [np.array(b[:2], dtype=np.float64) for b in layout["bins"]]
    yaw = [float(b[2]) for b in layout["bins"]]
    seq = []
    for a in initiators(layout):
        b, d = nearest(pos, a)
        seq.append((a, b, d, [p.copy() for p in pos], list(yaw)))
        pos[a], pos[b] = pos[b].copy(), pos[a].copy()
        yaw[a], yaw[b] = yaw[b], yaw[a]
    return seq


def distractors_from_repo(layout, cfg=None):
    """直接调仓库 sample_distractors；障碍 = 内部容器外接圆 +（BUS）按钮避让圆，约束 = 内部预演扫掠。"""
    cfg = cfg or dict(ux.XHARD_DISTRACTOR)
    radius = ux.bin_footprint_radius(CUBE_HALF)
    obstacles = [((b[0], b[1]), radius) for b in layout["bins"]]
    half_btn = 0.025 * 1.5 * 1.5
    for bx, by in layout["buttons"]:
        obstacles.append(((bx, by), float(np.linalg.norm([half_btn, half_btn]))))
    sweeps = []
    for a, b, _d, pos, yaw in inner_sequence(layout):
        sweeps.append((bin_state(f"bin_{a}", *pos[a], yaw[a]), bin_state(f"bin_{b}", *pos[b], yaw[b])))
    rec = SpecRecorder(None, layout["task"], {"seed": layout["seed"]}, difficulty="xhard")
    out = ux.sample_distractors(generator=ux.distractor_generator(layout["seed"]), cfg=cfg, obstacles=obstacles,
                                sweeps=sweeps, recorder=rec, cube_half_size=CUBE_HALF)
    return [(p["xy"][0], p["xy"][1], p["yaw_deg"]) for p in out["placements"]], out["cube_colors"]


def load_spec_rows(task=None):
    lines = SPECS_PATH.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines[1:]]
    return [r for r in rows if task is None or r["task"] == task]


def layout_from_spec(row):
    spec = row["spec"]
    bins = [tuple(spec["layout"]["bins"][str(i)]) for i in range(len(spec["layout"]["bins"]))]
    dis = [tuple(spec["layout"]["distractors"][str(i)]) for i in range(len(spec["layout"]["distractors"]))]
    o = spec["objects"]
    lay = dict(task=row["task"], seed=row["seed"], n_swaps=o["n_swaps"], bins=bins, distractors=dis,
               swap_initiator_indices=o["swap_initiator_indices"], swap_initiator_third=o["swap_initiator_third"],
               selected=o["selected"], buttons=[])
    if row["task"] == "ButtonUnmaskSwap":
        gen = torch.Generator(); gen.manual_seed(row["seed"])
        for center in ([-0.2, -0.1], [-0.2, 0.1]):
            off = torch.rand(2, generator=gen) - 0.5
            lay["buttons"].append((center[0] + float(off[0]) * 0.05, center[1] + float(off[1]) * 0.05))
    return lay
