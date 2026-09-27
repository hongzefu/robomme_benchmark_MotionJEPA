"""BinFill xhard（clutter）摆放的纯 torch/numpy 复刻（不进仿真器）。

逐次复刻 BinFill.__init__（xhard 不抽 dynamic）→ _load_scene 的随机调用顺序：
button(rand 2) → board(rand×3) → color_pool randperm(3) → put_in_color randint → target 分配
→ total_spawn randint → 余量分配 → spawn_order randperm(n) → 每块拒绝采样(每 trial rand×3)。
碰撞判据直接 import 仓库的 _obb2d_intersect/_build_new_cube_obb2d/_trimesh_box_to_obb2d/_yaw_to_quat_tensor；
已放方块的 OBB 用 trimesh bounding_box_oriented（与 get_actor_obb 同源）以求逐位一致。
"""
import numpy as np, torch, trimesh
from robomme.robomme_env.utils.object_generation import (
    _obb2d_intersect, _build_new_cube_obb2d, _trimesh_box_to_obb2d, _yaw_to_quat_tensor, create_button_obb)

HS = 0.02
REGION_C = np.array([-0.1, 0.0]); REGION_H = np.array([0.2, 0.25])
MIN_GAP = 0.02
COLORS = ["red", "blue", "green"]

def board_strips(bx, by, board_side=0.1, hole_side=0.08, pad=0.0):
    out = []
    bh, hh = board_side / 2, hole_side / 2
    c = np.array([bx, by], dtype=np.float64)
    th = bh - hh
    A = np.eye(2)
    h_top = np.array([bh + pad, th / 2 + pad])
    out.append((c + np.array([0, hh + th / 2]), A, h_top))
    out.append((c + np.array([0, -(hh + th / 2)]), A, h_top))
    lw = bh - hh
    h_left = np.array([lw / 2 + pad, hh + pad])
    out.append((c + np.array([-(hh + lw / 2), 0]), A, h_left))
    out.append((c + np.array([hh + lw / 2, 0]), A, h_left))
    return out

import sapien
from mani_skill.utils.geometry.trimesh_utils import merge_meshes
_HALF32 = np.array([HS, HS, HS], dtype=np.float32)

def placed_cube_obb(x, y, yaw, exact=True):
    """exact=True：逐位复刻 get_actor_obb（sapien float32 位姿 + trimesh OBB，含轴退化怪癖）；
    exact=False：真实方块 OBB（修复后的判据，用于 V5 反事实）。"""
    if not exact:
        return _build_new_cube_obb2d(x, y, HS, yaw, 0.0)
    q = _yaw_to_quat_tensor(yaw, device="cpu")[0].numpy()
    p = np.array([x, y, HS], dtype=np.float32)
    T = sapien.Pose(p=p, q=q).to_transformation_matrix()
    m = merge_meshes([trimesh.creation.box(extents=2 * _HALF32)])
    m.apply_transform(T)
    return _trimesh_box_to_obb2d(m.bounding_box_oriented, 0.0)

def obb_is_degenerate(obb):
    A = obb[1]
    return bool(min(np.linalg.norm(A[:, 0]), np.linalg.norm(A[:, 1])) < 0.5)

def sample_layout(seed=None, generator=None, exact=True, max_trials=256,
                  place_fn=None, return_trials=False):
    g = generator if generator is not None else torch.Generator().manual_seed(int(seed))
    # 按钮
    off = torch.rand(2, generator=g) - 0.5
    cx = -0.2 + float(off[0]) * 0.1; cy = 0.0 + float(off[1]) * 0.4
    button = create_button_obb(center_xy=(cx, cy), half_size=max(0.025 * 1.5, 0.025 * 1.5) * 1.5)
    # 孔板
    xv = torch.rand(1, generator=g).item() * 0.2 - 0.2
    yv = torch.rand(1, generator=g).item() * 0.4 - 0.2
    yaw_deg = torch.rand(1, generator=g).item() * 40 - 20
    bx, by = 0.15 + xv, 0.0 + yv
    # 颜色配额
    color_pool = torch.randperm(3, generator=g).tolist()[:3]
    pic = torch.randint(2, 4, (1,), generator=g).item()
    pic = max(1, min(3, pic)); pic = min(pic, 3)
    active = color_pool[:pic]
    target = [0, 0, 0]
    if pic == 1:
        target[active[0]] = torch.randint(5, 8, (1,), generator=g).item()
    else:
        tt = torch.randint(5, 8, (1,), generator=g).item()
        for _ in range(tt):
            idx = torch.randint(0, len(active), (1,), generator=g).item(); target[active[idx]] += 1
    total_spawn = torch.randint(12, 13, (1,), generator=g).item()
    spawn = [0, 0, 0]
    for i in color_pool:
        spawn[i] = max(target[i], 1)
    rem = total_spawn - sum(spawn[i] for i in color_pool)
    for _ in range(max(0, rem)):
        idx = torch.randint(0, len(color_pool), (1,), generator=g).item(); spawn[color_pool[idx]] += 1
    tasks = [(COLORS[c], k) for c in range(3) for k in range(spawn[c])]
    order = torch.randperm(len(tasks), generator=g).tolist()
    tasks = [tasks[i] for i in order]
    obstacles = [button] + board_strips(bx, by)
    lo = REGION_C - REGION_H + HS; hi = REGION_C + REGION_H - HS
    cubes = []; trials_used = []
    for si, (col, k) in enumerate(tasks):
        placed = None
        for t in range(max_trials):
            u1 = torch.rand(1, generator=g).item(); u2 = torch.rand(1, generator=g).item()
            x = float(lo[0] + u1 * (hi[0] - lo[0])); y = float(lo[1] + u2 * (hi[1] - lo[1]))
            yaw = float(torch.rand(1, generator=g).item() * 2 * np.pi)
            cn, An, hn = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=MIN_GAP)
            if any(_obb2d_intersect(c, A, h, cn, An, hn) for (c, A, h) in obstacles):
                continue
            placed = (x, y, yaw); trials_used.append(t + 1); break
        if placed is None:
            return None  # 放不满（xhard 判失败）
        cubes.append(dict(color=col, idx=k, spawn_idx=si, x=placed[0], y=placed[1], yaw=placed[2]))
        obstacles.append(placed_cube_obb(*placed, exact=exact))
    out = dict(button=(cx, cy), board=(bx, by, yaw_deg), color_pool=color_pool, put_in_color=pic,
               target=target, spawn=spawn, order=order, cubes=cubes)
    if return_trials:
        out["trials"] = trials_used
    return out
