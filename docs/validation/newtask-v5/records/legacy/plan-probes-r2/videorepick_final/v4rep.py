"""VideoRepick xhard 复位抽样的纯 CPU 逐位复刻（不起 sapien 场景）。

随机流顺序与 VideoRepick.__init__ / _load_scene / _load_cubes_xhard 一致：
  num_repeats randint(4,7) → n_swaps randint(8,13) → build_button rand(2) → 颜色 rand(3)
  → 6 块 × 每次尝试 rand(1)×3（x,y,yaw），拒绝采样判据用仓库自己的
     _build_new_cube_obb2d / _obb2d_intersect / _trimesh_box_to_obb2d
  → 目标 randint(0,6) → randperm(5)[:2]
已放方块的障碍 OBB 按 get_actor_obb 复刻：trimesh.creation.box + sapien.Pose(p,q).to_transformation_matrix()
（q 用仓库 _yaw_to_quat_tensor 在 CPU 上算）。
"""
import numpy as np, torch, trimesh, sapien
from robomme.robomme_env.utils.object_generation import (
    _build_new_cube_obb2d, _obb2d_intersect, _trimesh_box_to_obb2d, _yaw_to_quat_tensor, create_button_obb,
)
from robomme.robomme_env.utils.xhard import hsv_floor_rgb, HSV_FLOOR_COLOR

HS = 0.02
REGION_CENTER = (-0.1, 0.0)
REGION_HALF = (0.2, 0.25)
BTN_CENTER = (-0.2, 0.0)
BTN_RANGE = (0.1, 0.1)
BTN_OBB_HALF = 0.025 * 1.5 * 1.5


def cube_obb2d_like_actor(x, y, yaw, hs=HS):
    """复刻 get_actor_obb(actor) → _trimesh_box_to_obb2d 的 2D OBB（含退化情形）。"""
    q = _yaw_to_quat_tensor(yaw, device="cpu")[0].numpy().astype(np.float32)
    p = np.array([x, y, hs], dtype=np.float32)
    pose = sapien.Pose(p=p, q=q)
    T = pose.to_transformation_matrix()
    half = np.array([hs, hs, hs], dtype=np.float32)
    mesh = trimesh.creation.box(extents=2 * half)
    mesh.apply_transform(T)
    return _trimesh_box_to_obb2d(mesh.bounding_box_oriented, extra_pad=0.0)


def v4_reset(seed, n_cubes=6, min_gap=HS, max_trials=256, return_trials=False, obstacle_mode="actor"):
    g = torch.Generator(); g.manual_seed(seed)
    num_repeats = torch.randint(4, 7, (1,), generator=g).item()
    n_swaps = torch.randint(8, 13, (1,), generator=g).item()
    off = torch.rand(2, generator=g) - 0.5
    bx = BTN_CENTER[0] + float(off[0]) * BTN_RANGE[0]
    by = BTN_CENTER[1] + float(off[1]) * BTN_RANGE[1]
    obb_list = [create_button_obb(center_xy=(bx, by), half_size=BTN_OBB_HALF)]
    u = torch.rand(3, generator=g).tolist()
    rgb = hsv_floor_rgb(u, HSV_FLOOR_COLOR)
    x_low = REGION_CENTER[0] - REGION_HALF[0] + HS; x_high = REGION_CENTER[0] + REGION_HALF[0] - HS
    y_low = REGION_CENTER[1] - REGION_HALF[1] + HS; y_high = REGION_CENTER[1] + REGION_HALF[1] - HS
    cubes, trials = [], []
    for i in range(n_cubes):
        ok = False
        for t in range(max_trials):
            u1 = torch.rand(1, generator=g).item(); u2 = torch.rand(1, generator=g).item()
            x = float(x_low + u1 * (x_high - x_low)); y = float(y_low + u2 * (y_high - y_low))
            yaw = float(torch.rand(1, generator=g).item() * 2 * np.pi)
            c_new, A_new, h_new = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=float(min_gap))
            if any(_obb2d_intersect(c, A, h, c_new, A_new, h_new) for (c, A, h) in obb_list):
                continue
            cubes.append((x, y, yaw)); trials.append(t + 1); ok = True
            if obstacle_mode == "actor":
                obb_list.append(cube_obb2d_like_actor(x, y, yaw))
            else:  # 理想整方块
                cy_, sy_ = np.cos(yaw), np.sin(yaw)
                obb_list.append((np.array([x, y]), np.array([[cy_, -sy_], [sy_, cy_]]), np.array([HS, HS])))
            break
        if not ok:
            return None
    target = int(torch.randint(0, n_cubes, (1,), generator=g).item())
    remaining = [i for i in range(n_cubes) if i != target]
    perm = torch.randperm(len(remaining), generator=g).tolist()
    out = dict(seed=seed, num_repeats=num_repeats, n_swaps=n_swaps, button=(bx, by), rgb=rgb,
               cubes=cubes, target=target, perm_remaining=perm,
               initiators_v4=[target] + [remaining[i] for i in perm[:2]],
               initiators_all=[target] + [remaining[i] for i in perm])
    if return_trials:
        out["trials"] = trials
    return out
