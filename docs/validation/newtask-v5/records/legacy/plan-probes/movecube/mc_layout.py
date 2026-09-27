#!/usr/bin/env python3
"""MoveCube xhard 布局的逐调用 torch 复刻（不起 sapien），外加 V5 中心拒绝方案的插桩。

复刻 src/robomme/robomme_env/MoveCube.py::MoveCube._load_scene 的全部随机调用（顺序、取值域、判据），
随后再抽一次 way_idx（_initialize_episode 第一次 randint(3)）。
center 参数为 None 时逐字等价 V4；否则按给定定义做「就地重抽」拒绝（xhard-only 设计）。

只读仓库：import 仓库函数（corner_push、_obb2d_intersect、_build_new_cube_obb2d），不写任何文件。
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch

REPO = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask")
sys.path.insert(0, str(REPO / "src"))
from robomme.robomme_env.utils.xhard import corner_push  # noqa: E402

HS = 0.02  # PICK_CUBE_CONFIGS['panda']['cube_half_size']

_TRIMESH_CACHE = {}


def demo_cube_obstacle(x, y, yaw):
    """逐字复刻 spawn_random_cube 对已存在方块的 2D OBB：actor 碰撞盒 → trimesh.bounding_box_oriented
    → object_generation._trimesh_box_to_obb2d。实测 trimesh 常把 OBB 的 x 轴取成竖直方向，投影后第一轴
    退化为零向量 ⇒ 障碍物实际只是一条沿方块某水平轴、半长 0.02 的线段（见 obb_inspect.py）。"""
    import trimesh
    from robomme.robomme_env.utils.object_generation import _trimesh_box_to_obb2d, _yaw_to_quat_tensor
    q = _yaw_to_quat_tensor(yaw, device="cpu")[0].numpy().astype(np.float64)  # wxyz, float32 精度
    p = np.array([x, y, HS], dtype=np.float32).astype(np.float64)
    w, qx, qy, qz = q
    R = np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * w), 2 * (qx * qz + qy * w)],
        [2 * (qx * qy + qz * w), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * w)],
        [2 * (qx * qz - qy * w), 2 * (qy * qz + qx * w), 1 - 2 * (qx * qx + qy * qy)],
    ])
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = p
    mesh = trimesh.creation.box(extents=[2 * HS] * 3)
    mesh.apply_transform(T)
    return _trimesh_box_to_obb2d(mesh.bounding_box_oriented, extra_pad=0.0)


def _obb(x, y, half, yaw):
    c = np.array([x, y], dtype=np.float64)
    cy, sy = math.cos(yaw), math.sin(yaw)
    A = np.array([[cy, -sy], [sy, cy]], dtype=np.float64)
    return c, A, np.array([half, half], dtype=np.float64)


def _sat(c1, A1, h1, c2, A2, h2):
    d = c2 - c1
    for a in (A1[:, 0], A1[:, 1], A2[:, 0], A2[:, 1]):
        n = np.linalg.norm(a)
        a = a / n if n > 1e-12 else a
        r1 = abs(A1[:, 0] @ a) * h1[0] + abs(A1[:, 1] @ a) * h1[1]
        r2 = abs(A2[:, 0] @ a) * h2[0] + abs(A2[:, 1] @ a) * h2[1]
        if abs(d @ a) > r1 + r2:
            return False
    return True


# ---------------------------------------------------------------------------
# 「中心区域」判据：输入对象自身采样盒的归一化坐标 t∈[-1,1]^2，返回 True = 落在中心（拒绝）
# ---------------------------------------------------------------------------
def in_center(t, kind, s):
    tx, ty = abs(t[0]), abs(t[1])
    if kind == "square":      # 中心正方形：max(|tx|,|ty|) < s
        return max(tx, ty) < s
    if kind == "disk":        # 中心圆：|t| < s
        return math.hypot(tx, ty) < s
    if kind == "cross":       # 十字（任一轴居中即拒）：min(|tx|,|ty|) < s ⇒ 只留四角
        return min(tx, ty) < s
    raise ValueError(kind)


@dataclass
class CenterCfg:
    """各对象的禁区（绝对米制，None = 该对象不做中心拒绝）。

    peg_w：杆根点相对自身抖动盒中心 (0, base_y) 的禁区半边/半径；
    goal_w_demo / goal_w_exec：goal 相对 (0,0) 的禁区；cube_w：方块相对 (0,0) 的禁区；
    cube_apply："cand" 只判候选中心，"final" 只判最终 xy，"both" 两者都判。
    kind：square（Chebyshev）/ disk（欧氏）/ cross（任一轴居中即拒）。
    peg_abs_w：若给，杆根点改用相对公共中心 (0,0) 的禁区（绝对定义 c）。
    """
    kind: str = "square"
    peg_w: float | None = None
    goal_w_demo: float | None = None
    goal_w_exec: float | None = None
    cube_w: float | None = None
    cube_apply: str = "both"
    peg_abs_w: float | None = None
    max_trials_obj: int = 128


@dataclass
class Layout:
    ok: bool = True
    fail: str = ""
    seg: dict = field(default_factory=dict)
    draws: int = 0
    rejects: dict = field(default_factory=dict)
    way_idx: int = -1
    obj_sample: int = -1


def zone(dx, dy, w, kind):
    """(dx,dy) 为相对禁区中心的位移；w 为半边/半径；返回 True = 在禁区里。"""
    if w is None:
        return False
    return in_center((dx / w, dy / w), kind, 1.0)


def simulate(seed: int, bias: float = 0.5, center: CenterCfg | None = None, yaw_xhard=True,
             obstacle: str = "square", exec_avoid_demo: bool = True) -> Layout:
    """obstacle："trimesh"=逐字复刻真实（退化线段）障碍；"square"=理想正方形（偏保守）。
    exec_avoid_demo=False：模拟 V5 修复「执行段方块不再避让演示段方块」（include_existing=False）。"""
    from robomme.robomme_env.utils.object_generation import _obb2d_intersect, _build_new_cube_obb2d
    g = torch.Generator()
    g.manual_seed(int(seed))
    n = [0]

    def rand():
        n[0] += 1
        return torch.rand(1, generator=g).item()

    def randint(k):
        n[0] += 1
        return int(torch.randint(0, k, (1,), generator=g).item())

    out = Layout()
    rej = {"peg_demo": 0, "peg_exec": 0, "goal_demo": 0, "goal_exec": 0,
           "cand_demo": 0, "cand_exec": 0, "cube_demo": 0, "cube_exec": 0}

    rand(); rand()  # length / radius（R8）
    span, off = (2 * math.pi, math.pi) if yaw_xhard else (math.pi / 2, math.pi / 4)

    pegs = {}
    for segname in ("demo", "exec"):
        base_y = -0.2 if rand() < 0.5 else 0.2
        xj = (corner_push(rand(), bias) - 0.5) * 0.1
        yj = (corner_push(rand(), bias) - 0.5) * 0.1
        if center is not None and (center.peg_w is not None or center.peg_abs_w is not None):
            k = 0
            while True:
                if center.peg_abs_w is not None:
                    bad = zone(xj, base_y + yj, center.peg_abs_w, center.kind)
                else:
                    bad = zone(xj, yj, center.peg_w, center.kind)
                if not bad:
                    break
                k += 1
                rej[f"peg_{segname}"] += 1
                if k >= center.max_trials_obj:
                    out.ok, out.fail = False, f"peg_{segname}"
                    return out
                xj = (corner_push(rand(), bias) - 0.5) * 0.1
                yj = (corner_push(rand(), bias) - 0.5) * 0.1
        yaw = rand() * span - off
        pegs[segname] = (np.array([xj, base_y + yj]), yaw)

    out.obj_sample = randint(2)
    randint(2)  # dir_sample（未消费，R8）

    goals = {}
    for segname, half in (("demo", 0.15), ("exec", 0.1)):
        lo = 0.0 - half + 0.04
        hi = 0.0 + half - 0.04
        k = 0
        while True:
            gx = float(rand() * (hi - lo) + lo)
            gy = float(rand() * (hi - lo) + lo)
            if center is None:
                break
            gw = center.goal_w_demo if segname == "demo" else center.goal_w_exec
            bad = zone(gx, gy, gw, center.kind)
            if not bad:
                break
            k += 1
            rej[f"goal_{segname}"] += 1
            if k >= 256:  # spawn_random_target 的 max_trials
                out.ok, out.fail = False, f"goal_{segname}"
                return out
        # 目标位姿以 float32 存进 actor，再被读回做距离判据
        goals[segname] = np.array([gx, gy], dtype=np.float32).astype(np.float64)

    cubes = {}
    demo_obb = None
    for segname in ("demo", "exec"):
        gxy = goals[segname]
        cand = None
        for _ in range(128):
            cx = corner_push(rand(), bias) * 0.2 + -0.1
            cy = corner_push(rand(), bias) * 0.2 + -0.1
            if np.linalg.norm(np.array([cx, cy]) - gxy) > HS * 5:
                if center is not None and center.cube_apply in ("cand", "both"):
                    bad = zone(cx, cy, center.cube_w, center.kind)
                    if bad:
                        rej[f"cand_{segname}"] += 1
                        continue
                cand = (cx, cy)
                break
            rej[f"cand_{segname}"] += 0  # 与 goal 太近的拒绝不计入中心拒绝
        if cand is None:
            out.ok, out.fail = False, f"cand_{segname}"
            return out
        cx, cy = cand
        x_low, x_high = cx - 0.05 + HS, cx + 0.05 - HS
        y_low, y_high = cy - 0.05 + HS, cy + 0.05 - HS
        placed = None
        for _ in range(256):
            u1 = rand(); u2 = rand()
            if bias:
                u1 = corner_push(u1, bias); u2 = corner_push(u2, bias)
            x = float(x_low + u1 * (x_high - x_low))
            y = float(y_low + u2 * (y_high - y_low))
            yaw = float(rand() * 2 * np.pi)
            if segname == "exec" and demo_obb is not None and exec_avoid_demo:
                c2, A2, h2 = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=0.005)
                # obb2d_list 里演示段方块出现两次（self.cube 与 _spawned_cubes[0]），判据相同，测一次即可
                if _obb2d_intersect(*demo_obb, c2, A2, h2):
                    continue
            if center is not None and center.cube_apply in ("final", "both"):
                bad = zone(x, y, center.cube_w, center.kind)
                if bad:
                    rej[f"cube_{segname}"] += 1
                    continue
            placed = (x, y, yaw)
            break
        if placed is None:
            out.ok, out.fail = False, f"cube_{segname}"
            return out
        cubes[segname] = placed
        if segname == "demo":
            if obstacle == "trimesh":
                demo_obb = demo_cube_obstacle(placed[0], placed[1], placed[2])
            else:
                demo_obb = _obb(placed[0], placed[1], HS, placed[2])

    out.way_idx = randint(3)
    out.draws = n[0]
    out.rejects = rej
    for segname in ("demo", "exec"):
        out.seg[segname] = {"peg_root": pegs[segname][0], "peg_yaw": pegs[segname][1],
                            "goal": goals[segname], "cube": np.array(cubes[segname][:2]),
                            "cube_yaw": cubes[segname][2]}
    return out
