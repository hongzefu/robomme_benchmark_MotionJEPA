"""P1 进程内猴补丁（不落盘、不改任何被跟踪文件）：把 PickXtimes xhard 换成 V5 规则。

- corner_bias 取消（全部均匀）；
- 6 块（3 有色 + 3 干扰）两两中心距 ≥ min_center_dist（0.08），在既有 OBB/圆判据之后求值，自身不抽随机数；
- avoid 里已放的方块 actor 换成按真实 yaw 的精确 OBB 三元组（模拟计划中的 cube_obb2d_exact(pose, half)）；
- 方块 max_trials 1024；
- 方块区域半宽（有色 + 干扰）= hw；圆盘区域仍 0.2；
- 可选强制 num_repeats 范围（只改 __init__ 里独立 generator 的 randint 上下界，不影响布局随机流）。

实现：替换 PickXtimes 模块命名空间里的 spawn_random_cube。拒绝循环逐字复刻原函数的抽样（每 trial 3 次 rand），
接受后走原函数的 fixed_xy 分支建 actor（同一个 _finalize_cube），recorder.value 在此之前调用。
非 xhard 调用原样转发。"""
from __future__ import annotations

import math
import sys

import numpy as np
import torch

ACCEPTED = []   # 本局每块：(spec_path, x, y, yaw, trials)


def _pose_xy_yaw(actor):
    p = actor.pose.p; q = actor.pose.q
    if isinstance(p, torch.Tensor):
        p = p[0].detach().cpu().numpy(); q = q[0].detach().cpu().numpy()
    w, x, y, z = [float(v) for v in q]
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return float(p[0]), float(p[1]), yaw


def cube_obb2d_exact(actor, half):
    x, y, yaw = _pose_xy_yaw(actor)
    c, s = math.cos(yaw), math.sin(yaw)
    return (np.array([x, y], dtype=np.float64), np.array([[c, -s], [s, c]], dtype=np.float64),
            np.array([half, half], dtype=np.float64))


def apply_patch(hw=0.2, min_center_dist=0.08, max_trials=1024, num_range=None):
    import robomme.robomme_env  # noqa: F401
    PX = sys.modules["robomme.robomme_env.PickXtimes"]
    og = sys.modules["robomme.robomme_env.utils.object_generation"]
    orig = og.spawn_random_cube
    get_actor_obb = og.get_actor_obb

    xd = PX.XHARD_DECISION
    xd["target_cube_position_policy"]["region_half_size"] = hw
    xd["target_cube_position_policy"]["corner_bias"] = 0.0
    xd["distractor"]["region_half_size"] = hw
    if num_range is not None:
        PX.PickXtimes.config_xhard["number_min"], PX.PickXtimes.config_xhard["number_max"] = num_range

    def v5_spawn_random_cube(self, **kw):
        if getattr(self, "difficulty", None) != "xhard":
            return orig(self, **kw)
        gen = kw["generator"]; hs = float(kw["half_size"]); min_gap = float(kw["min_gap"])
        center = np.array(kw["region_center"], dtype=np.float64); ah = float(kw["region_half_size"])
        xl, xh = center[0] - ah + hs, center[0] + ah - hs
        yl, yh = center[1] - ah + hs, center[1] + ah - hs
        obbs, centers = [], []
        for it in kw.get("avoid") or []:
            if isinstance(it, tuple):
                if len(it) == 3 and isinstance(it[0], np.ndarray):
                    obbs.append(it)
                else:
                    raise RuntimeError("P1 补丁未覆盖 (actor, pad) 形式")
            elif hasattr(it, "_cube_half_size"):
                obbs.append(cube_obb2d_exact(it, float(it._cube_half_size)))
                x0, y0, _ = _pose_xy_yaw(it); centers.append((x0, y0))
            else:
                try:
                    obbs.append(og._trimesh_box_to_obb2d(get_actor_obb(it, to_world_frame=True, vis=False)))
                except Exception:
                    pass   # 与原函数一致：无网格的视觉 actor（圆盘）忽略，靠预制三元组避让
        for trial in range(int(max_trials)):
            u1 = torch.rand(1, generator=gen).item(); u2 = torch.rand(1, generator=gen).item()
            x = float(xl + u1 * (xh - xl)); y = float(yl + u2 * (yh - yl))
            yaw = float(torch.rand(1, generator=gen).item() * 2 * np.pi)
            cn, An, hn = og._build_new_cube_obb2d(x, y, hs, yaw, pad_xy=min_gap)
            if any(og._obb2d_intersect(c, A, h, cn, An, hn) for (c, A, h) in obbs):
                continue
            if any(math.hypot(x - px, y - py) < min_center_dist for (px, py) in centers):
                continue
            rec, sp = kw.get("recorder"), kw.get("spec_path")
            if rec is not None and sp is not None:
                x, y, yaw = rec.value(sp, [x, y, yaw])
            ACCEPTED.append((sp, x, y, yaw, trial + 1))
            return orig(self, region_center=kw["region_center"], region_half_size=ah, half_size=hs,
                        color=kw["color"], name_prefix=kw["name_prefix"], min_gap=min_gap,
                        include_existing=False, include_goal=False, fixed_xy=(x, y), fixed_yaw=yaw)
        raise RuntimeError("spawn_random_cube(P1): no feasible position found")

    PX.spawn_random_cube = v5_spawn_random_cube
    return PX
