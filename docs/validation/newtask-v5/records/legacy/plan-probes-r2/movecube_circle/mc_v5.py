#!/usr/bin/env python3
"""MoveCube xhard 布局的逐调用 torch 离线副本（不起 sapien），带 V5 最终规则「桌面中心圆形共同禁区」插桩。

复刻 src/robomme/robomme_env/MoveCube.py::_load_scene 的全部随机调用（顺序、取值域、判据），随后抽 way_idx。
- R=None：逐字等价 V4（bias 参数可设 0.5 复现 v4-01）。
- R=float：V5 规则——corner_bias 删除（bias 必须为 0）；圆心 (0,0)、半径 R，按物体中心判：
    杆：轴线段 root−0.075u … root+0.025u 离原点最近距离 < R → 原地重抽 (x_jitter, y_jitter, yaw)；
    goal：圆盘中心 |c| < R → 原地重抽（spawn_random_target 循环内 continue）；
    方块候选：|c_cand| < R → 重抽（与 |c−g|>0.1 同一次试验，共用 128 次循环）；
    方块最终：|c_final| < R → 重抽（spawn_random_cube 循环内 continue）；
    每个取值点的中心拒绝次数达到 128 即判该局失败；执行段方块 include_existing=False。
只读仓库：从 worktree 的 src import 纯函数，不写任何被跟踪文件。
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field

import numpy as np
import torch

sys.path.insert(0, "/data/hongzefu/robomme_v5_probe_wt/src")
from robomme.robomme_env.utils.xhard import corner_push  # noqa: E402

HS = 0.02
MAXR = 128
POINTS = ("peg_demo", "peg_exec", "goal_demo", "goal_exec", "cand_demo", "cand_exec", "cube_demo", "cube_exec")


def seg_dist(root, yaw, a=-0.075, b=0.025):
    """杆轴线段 root+t·u（t∈[a,b]）到原点的最近距离。"""
    u = np.array([math.cos(yaw), math.sin(yaw)])
    t = float(np.clip(-(root @ u), a, b))
    return float(np.linalg.norm(root + t * u))


def demo_cube_obstacle(x, y, yaw):
    """逐字复刻 spawn_random_cube 对已存在方块的 2D OBB（trimesh 退化线段，见 plan-probes/movecube/obb_inspect.py）。"""
    import trimesh
    from robomme.robomme_env.utils.object_generation import _trimesh_box_to_obb2d, _yaw_to_quat_tensor
    q = _yaw_to_quat_tensor(yaw, device="cpu")[0].numpy().astype(np.float64)
    p = np.array([x, y, HS], dtype=np.float32).astype(np.float64)
    w, qx, qy, qz = q
    Rm = np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * w), 2 * (qx * qz + qy * w)],
        [2 * (qx * qy + qz * w), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * w)],
        [2 * (qx * qz - qy * w), 2 * (qy * qz + qx * w), 1 - 2 * (qx * qx + qy * qy)],
    ])
    T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = p
    mesh = trimesh.creation.box(extents=[2 * HS] * 3)
    mesh.apply_transform(T)
    return _trimesh_box_to_obb2d(mesh.bounding_box_oriented, extra_pad=0.0)


@dataclass
class Layout:
    ok: bool = True
    fail: str = ""
    seg: dict = field(default_factory=dict)
    draws: int = 0
    rej: dict = field(default_factory=dict)       # 各取值点中心拒绝（重抽）次数
    att: dict = field(default_factory=dict)       # 各取值点接受中心判据检查的抽样次数
    raw_in: dict = field(default_factory=dict)    # 各取值点「原始抽样落进圆」次数（不论其他判据）
    raw_n: dict = field(default_factory=dict)
    way_idx: int = -1
    way_idx_run: int = -1   # 第二次 _initialize_episode 抽到的 way（gym.make 与 reset 各初始化一次，演示实际用它）
    obj_sample: int = -1


def simulate(seed, bias=0.0, R=None, exec_avoid_demo=None, stat_R=(0.04, 0.05, 0.06), obstacle="square", peg_seg=(-0.075, 0.025)):
    """exec_avoid_demo 缺省：R=None（V4）时 True，V5 时 False（include_existing=False）。
    obstacle：V4 下执行段方块对演示段方块的障碍模型；"square"=满尺寸方块 OBB（v4-01 10/10 逐位一致），
    "trimesh"=旧探针的退化线段模型（5400500 上与真实不符）。V5 下 include_existing=False，此参数不起作用。
    peg_seg：杆轴线段在杆根坐标系里的区间 [a,b]（沿 yaw 方向 u）。缺省 (-0.075, 0.025) 为计划 2.9 口径；
    本机模拟器实测杆的物理/视觉范围是 (-0.15, 0.05)（head 以 root 为中心半长 0.05，tail 中心在 root−0.1u），作对照变体。
    stat_R：额外统计「原始抽样落进半径 r 圆」的比例（与是否拒绝无关），用于 R=0.04/0.06 参考。"""
    from robomme.robomme_env.utils.object_generation import _obb2d_intersect, _build_new_cube_obb2d
    if R is not None:
        assert bias == 0.0, "V5 规则下 corner_bias 已删除"
    if exec_avoid_demo is None:
        exec_avoid_demo = R is None
    g = torch.Generator(); g.manual_seed(int(seed))
    n = [0]

    def rand():
        n[0] += 1
        return torch.rand(1, generator=g).item()

    def randint(k):
        n[0] += 1
        return int(torch.randint(0, k, (1,), generator=g).item())

    out = Layout()
    out.rej = {p: 0 for p in POINTS}; out.att = {p: 0 for p in POINTS}
    out.raw_in = {(p, r): 0 for p in POINTS for r in stat_R}; out.raw_n = {p: 0 for p in POINTS}

    def raw(p, d):
        out.raw_n[p] += 1
        for r in stat_R:
            out.raw_in[(p, r)] += d < r

    def reject(p, d):
        """返回 True=该抽样被中心规则拒绝；拒绝次数达 MAXR 时抛 _Exhaust。"""
        out.att[p] += 1
        if R is not None and d < R:
            out.rej[p] += 1
            if out.rej[p] >= MAXR:
                raise _Exhaust(p)
            return True
        return False

    try:
        rand(); rand()
        pegs = {}
        for s in ("demo", "exec"):
            base_y = -0.2 if rand() < 0.5 else 0.2
            while True:
                xj = (corner_push(rand(), bias) - 0.5) * 0.1
                yj = (corner_push(rand(), bias) - 0.5) * 0.1
                root = np.array([xj, base_y + yj])
                yaw = rand() * 2 * math.pi - math.pi
                d = seg_dist(root, yaw, *peg_seg); raw(f"peg_{s}", d)
                if R is None or not reject(f"peg_{s}", d):
                    break
            pegs[s] = (root, yaw)
        out.obj_sample = randint(2); randint(2)

        goals = {}
        for s, half in (("demo", 0.15), ("exec", 0.1)):
            lo, hi = -half + 0.04, half - 0.04
            for _ in range(256):
                gx = float(rand() * (hi - lo) + lo); gy = float(rand() * (hi - lo) + lo)
                d = math.hypot(gx, gy); raw(f"goal_{s}", d)
                if R is None or not reject(f"goal_{s}", d):
                    break
            else:
                raise _Exhaust(f"goal_{s}_256")
            goals[s] = np.array([gx, gy], dtype=np.float32).astype(np.float64)

        cubes = {}; demo_obb = None
        for s in ("demo", "exec"):
            gxy = goals[s]; cand = None
            for _ in range(128):
                cx = corner_push(rand(), bias) * 0.2 - 0.1
                cy = corner_push(rand(), bias) * 0.2 - 0.1
                d = math.hypot(cx, cy); raw(f"cand_{s}", d)
                if np.linalg.norm(np.array([cx, cy]) - gxy) > HS * 5:
                    if R is not None and reject(f"cand_{s}", d):
                        continue
                    cand = (cx, cy); break
            if cand is None:
                raise _Exhaust(f"cand_{s}_loop128")
            cx, cy = cand
            xl, xh, yl, yh = cx - 0.03, cx + 0.03, cy - 0.03, cy + 0.03
            placed = None
            for _ in range(256):
                u1 = rand(); u2 = rand()
                if bias:
                    u1 = corner_push(u1, bias); u2 = corner_push(u2, bias)
                x = float(xl + u1 * (xh - xl)); y = float(yl + u2 * (yh - yl))
                yaw = float(rand() * 2 * np.pi)
                if s == "exec" and exec_avoid_demo:
                    c2, A2, h2 = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=0.005)
                    if _obb2d_intersect(*demo_obb, c2, A2, h2):
                        continue
                d = math.hypot(x, y); raw(f"cube_{s}", d)
                if R is not None and reject(f"cube_{s}", d):
                    continue
                placed = (x, y, yaw); break
            if placed is None:
                raise _Exhaust(f"cube_{s}_loop256")
            cubes[s] = placed
            if s == "demo":
                if obstacle == "trimesh":
                    demo_obb = demo_cube_obstacle(*placed)
                else:
                    x0, y0, w0 = placed
                    demo_obb = (np.array([x0, y0]), np.array([[math.cos(w0), -math.sin(w0)], [math.sin(w0), math.cos(w0)]]), np.array([HS, HS]))
        out.way_idx = randint(3)
        out.way_idx_run = randint(3)
    except _Exhaust as e:
        out.ok, out.fail = False, str(e)
        out.draws = n[0]
        return out
    out.draws = n[0]
    for s in ("demo", "exec"):
        out.seg[s] = {"peg_root": pegs[s][0], "peg_yaw": pegs[s][1], "goal": goals[s],
                      "cube": np.array(cubes[s][:2]), "cube_yaw": cubes[s][2]}
    return out


class _Exhaust(Exception):
    pass
