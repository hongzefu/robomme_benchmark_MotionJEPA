"""PickXtimes / SwingXtimes xhard 布局采样的纯几何复刻（不起 sapien 场景）。

逐字复刻 _load_scene 里对同一个 torch.Generator(seed) 的全部抽样顺序：
  PickXtimes xhard : button rand(2) → randperm(3) → randint(3) → 圆盘(每 trial 2 次 rand)
                     → 3 有色方块(每 trial 3 次 rand，u1/u2 经 corner_push) → randint(3) 目标
                     → [V4 不开 recovery，无抽样] → 3 干扰方块(每 trial 3 次 rand)
  SwingXtimes xhard: button rand(2) → randperm(3) → randint(3) → 3 有色方块 → 圆盘0 → 圆盘1
                     → randint(3) 目标 → 3 干扰方块(避让两个圆盘的预制 OBB)
已放方块的 2D OBB 有两种模式：
  obb_mode="trimesh"  与仓库一致：get_actor_obb → trimesh bounding_box_oriented → _trimesh_box_to_obb2d
                      （约 37.6% 的 yaw 下退化为线段，见 obb_check.py）
  obb_mode="exact"    正确的 yaw 正方形（用来量化退化的影响）
另有若干 V5 候选开关（见 pick_layout 的参数）。
"""
from __future__ import annotations
import math
import numpy as np
import torch
import trimesh
import sapien
from robomme.robomme_env.utils.object_generation import (
    _build_new_cube_obb2d, _obb2d_intersect, _trimesh_box_to_obb2d, create_button_obb, _yaw_to_quat_tensor)
from robomme.robomme_env.utils.xhard import corner_push

HS = 0.02  # cube_half_size（panda）
_OBB_CACHE = {}


def cube_obb2d(x, y, yaw, mode="trimesh"):
    if mode == "exact":
        c, A, h = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=0.0)
        return (c, A, h)
    q = _yaw_to_quat_tensor(yaw, device="cpu")[0].numpy()
    # actor 位姿以 float32 张量建（Pose.create_from_pq），这里同样走 float32
    p = np.array([x, y, HS], dtype=np.float32)
    pose = sapien.Pose(p=p, q=q.astype(np.float32))
    mesh = trimesh.creation.box(extents=2 * np.array([HS, HS, HS], dtype=np.float32))
    mesh.apply_transform(pose.to_transformation_matrix())
    return _trimesh_box_to_obb2d(mesh.bounding_box_oriented)


def rand1(g):
    return torch.rand(1, generator=g).item()


def build_button(g, center=(-0.2, 0.0), rr=(0.1, 0.4), scale=1.5):
    off = torch.rand(2, generator=g) - 0.5
    cx = float(center[0]) + float(off[0]) * float(rr[0])
    cy = float(center[1]) + float(off[1]) * float(rr[1])
    half = max(0.025 * scale, 0.025 * scale) * 1.5
    return (cx, cy), create_button_obb(center_xy=(cx, cy), half_size=half)


def spawn_cube(g, obbs, circles, region_center, region_half, corner_bias=0.0, min_gap=HS,
               max_trials=256, obb_mode="trimesh", extra_reject=None):
    """复刻 spawn_random_cube 的拒绝采样；返回 (x,y,yaw,trials) 或 None。obbs: 预制 OBB 列表。"""
    c = np.array(region_center, dtype=np.float64)
    ah = np.array([float(region_half)] * 2) if np.isscalar(region_half) else np.array(region_half, dtype=np.float64)
    xl, xh = c[0] - ah[0] + HS, c[0] + ah[0] - HS
    yl, yh = c[1] - ah[1] + HS, c[1] + ah[1] - HS
    for t in range(max_trials):
        u1 = rand1(g); u2 = rand1(g)
        if corner_bias:
            u1 = corner_push(u1, corner_bias); u2 = corner_push(u2, corner_bias)
        x = float(xl + u1 * (xh - xl)); y = float(yl + u2 * (yh - yl))
        yaw = float(rand1(g) * 2 * np.pi)
        cn, An, hn = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=float(min_gap))
        if any(_obb2d_intersect(co, Ao, ho, cn, An, hn) for (co, Ao, ho) in obbs):
            continue
        if any(np.linalg.norm(np.array([x, y]) - xy) < R for (xy, R) in circles):
            continue
        if extra_reject is not None and extra_reject(x, y):
            continue
        return x, y, yaw, t + 1
    return None


def spawn_disk(g, obbs, circles, region_center, region_half, radius, min_gap, max_trials=256):
    """复刻 spawn_random_target（random_yaw=False ⇒ 每 trial 2 次 rand）。circles: [(xy, R)] 圆–圆判据。"""
    c = np.array(region_center, dtype=np.float64); a = float(region_half)
    xl, xh = c[0] - a + radius, c[0] + a - radius
    yl, yh = c[1] - a + radius, c[1] + a - radius
    for t in range(max_trials):
        x = float(rand1(g) * (xh - xl) + xl)
        y = float(rand1(g) * (yh - yl) + yl)
        pos = np.array([x, y]); rc = radius + min_gap
        hit = False
        for (co, Ao, ho) in obbs:
            lp = Ao.T @ (pos - co); cp = np.clip(lp, -ho, ho); cw = co + Ao @ cp
            if np.linalg.norm(pos - cw) < rc:
                hit = True; break
        if hit:
            continue
        if any(np.linalg.norm(pos - xy) < (rc + R) for (xy, R) in circles):
            continue
        return x, y, t + 1
    return None


def disk_obb(xy, clearance):
    return (np.array(xy, dtype=np.float64), np.eye(2), np.array([clearance, clearance]))


def pick_layout(seed, corner_bias=0.5, obb_mode="trimesh", distractor_corner_bias=0.0,
                colored_min_gap=HS, distractor_min_gap=HS, bias_target_only=False,
                min_center_dist=None, v5_order=None):
    """PickXtimes xhard 一局；返回 dict 或 {'fail': 阶段}。
    bias_target_only：V5 选项——只把目标块推角（需要预先知道目标 idx；这里用追加抽样实现，见说明）。
    min_center_dist：V5 选项——额外的中心距下限（对全部已放方块，含干扰物），以 extra_reject 实现。
    """
    g = torch.Generator(); g.manual_seed(seed)
    bxy, bobb = build_button(g)
    order = torch.randperm(3, generator=g).tolist()
    _tci = torch.randint(0, 3, (1,), generator=g).item()
    obbs = [bobb]
    d = spawn_disk(g, obbs, [], (-0.1, 0), 0.2, radius=2 * HS, min_gap=2 * HS)
    if d is None:
        return {"fail": "disk"}
    gx, gy, _ = d
    obbs.append(disk_obb((gx, gy), 2 * HS + 2 * HS - HS))
    names = ["red", "blue", "green"]
    colored = []
    placed = []

    def far_enough(x, y):
        if min_center_dist is None:
            return False
        return any(math.hypot(x - px, y - py) < min_center_dist for (px, py) in placed)

    for k, ci in enumerate(order):
        cb = corner_bias
        r = spawn_cube(g, obbs, [], (-0.1, 0), 0.2, corner_bias=cb, min_gap=colored_min_gap,
                       obb_mode=obb_mode, extra_reject=far_enough)
        if r is None:
            return {"fail": f"cube{k}"}
        x, y, yaw, _ = r
        colored.append((names[ci], x, y, yaw)); placed.append((x, y))
        obbs.append(cube_obb2d(x, y, yaw, obb_mode))
    tidx = torch.randint(0, 3, (1,), generator=g).item()
    dis = []
    for name in ["yellow", "cyan", "magenta"]:
        r = spawn_cube(g, obbs, [], (-0.1, 0), 0.2, corner_bias=distractor_corner_bias,
                       min_gap=distractor_min_gap, obb_mode=obb_mode, extra_reject=far_enough)
        if r is None:
            return {"fail": f"distractor_{name}"}
        x, y, yaw, _ = r
        dis.append((name, x, y, yaw)); placed.append((x, y))
        obbs.append(cube_obb2d(x, y, yaw, obb_mode))
    return {"button": bxy, "goal": (gx, gy), "colored": colored, "target_idx": tidx,
            "distractors": dis, "order": order}


def swing_layout(seed, obb_mode="trimesh", cube_corner_bias=0.0, min_center_dist=None,
                 colored_min_gap=HS, distractor_min_gap=HS):
    g = torch.Generator(); g.manual_seed(seed)
    bxy, bobb = build_button(g)
    order = torch.randperm(3, generator=g).tolist()
    _tci = torch.randint(0, 3, (1,), generator=g).item()
    obbs = [bobb]
    names = ["red", "blue", "green"]
    colored, placed = [], []

    def far_enough(x, y):
        if min_center_dist is None:
            return False
        return any(math.hypot(x - px, y - py) < min_center_dist for (px, py) in placed)

    for k, ci in enumerate(order):
        r = spawn_cube(g, obbs, [], (-0.1, 0), 0.25, corner_bias=cube_corner_bias, min_gap=colored_min_gap,
                       obb_mode=obb_mode, extra_reject=far_enough)
        if r is None:
            return {"fail": f"cube{k}"}
        x, y, yaw, _ = r
        colored.append((names[ci], x, y, yaw)); placed.append((x, y))
        obbs.append(cube_obb2d(x, y, yaw, obb_mode))
    disks = []
    circles = []
    for i, rc in enumerate([(-0.1, -0.2), (-0.1, 0.2)]):
        dd = spawn_disk(g, obbs, circles, rc, 0.1, radius=2 * HS, min_gap=HS)
        if dd is None:
            return {"fail": f"disk{i}"}
        disks.append((dd[0], dd[1])); circles.append((np.array(dd[:2]), 2 * HS))
    tidx = torch.randint(0, 3, (1,), generator=g).item()
    obbs2 = list(obbs) + [disk_obb(xy, HS * (2 + 1) - HS) for xy in disks]
    dis = []
    for name in ["yellow", "cyan", "magenta"]:
        r = spawn_cube(g, obbs2, [], (-0.1, 0), 0.25, min_gap=distractor_min_gap, obb_mode=obb_mode,
                       extra_reject=far_enough)
        if r is None:
            return {"fail": f"distractor_{name}"}
        x, y, yaw, _ = r
        dis.append((name, x, y, yaw)); placed.append((x, y))
        obbs2.append(cube_obb2d(x, y, yaw, obb_mode))
    return {"button": bxy, "disks": disks, "colored": colored, "target_idx": tidx,
            "distractors": dis, "order": order}
