#!/usr/bin/env python3
"""V6 MoveCube 统一生成区域 U 的离线定义、采样器与面积/可行性评估。

依据（2026-09-25 实测，reach/A、reach/B、reach/C）：
  A  末端顶抓/推位姿：全 yaw 可达 = 离基座 r∈[0.31, 0.80]，桌面 x≤0.175；
  B  抓杆点（杆尾 root−0.10u）离基座 ≤0.80 时 12 个 yaw 全成功，0.80～0.85 仅 48%，≥0.85 为 0；<0.25 抓不到；
  C  144 局真演示：抓杆点 x>0.15 时 peg_push 2/17；推距 >0.30 时 gripper_push 12/22、≤0.30 时 23/26。

U 的定义（桌面坐标，原点桌心，基座 (-0.615,0)）——对方块中心、goal 中心、杆抓取点三者统一：
  (1) 离基座 R_B_LO ≤ |p−base| ≤ R_B_HI      （可达环带，A/B 硬边界各留 4 cm 余量）
  (2) |p| ≥ R_IN                               （去掉桌心区域）
  (3) |y| ≤ Y_CAP，X_LO ≤ x ≤ X_CAP            （避开 A 图左上楔形、机器人身侧与 +x 远端）
成对约束：
  (4) 0.10 ≤ |cube−goal| ≤ PUSH_MAX            （C：推距上限）
  (5) 推起点（cube − 0.10·d，peg_push 再侧移 ±0.10）离基座也在 [R_B_LO, R_B_HI] 内
  (6) 方块中心离杆身线段 ≥ 0.04；goal 中心离杆身 ≥ 0.02；杆身线段离桌心 ≥ R_IN（杆整体不进中心区）
朝向：杆 yaw ∈ U(−π, π)，方块 yaw ∈ U(0, 2π)。
"""
from __future__ import annotations

import math
import numpy as np

BASE = np.array([-0.615, 0.0])
EXT = (-0.15, 0.05)          # 杆身相对根沿 u 的范围（B 实测确认）
TAIL_T = -0.10               # 抓取点 = root + TAIL_T·u
P = dict(R_B_LO=0.35, R_B_HI=0.76, R_IN=0.14, Y_CAP=0.30, X_CAP=0.15, X_LO=-0.30,
         MIN_CG=0.10, PUSH_MAX=0.30, PEG_GAP=0.04, GOAL_PEG_GAP=0.02)


def in_u(p, P=P):
    r = np.linalg.norm(p - BASE)
    return (P["R_B_LO"] <= r <= P["R_B_HI"] and np.linalg.norm(p) >= P["R_IN"]
            and abs(p[1]) <= P["Y_CAP"] and P["X_LO"] <= p[0] <= P["X_CAP"])


def seg_dist(p, root, yaw, ext=EXT):
    u = np.array([math.cos(yaw), math.sin(yaw)])
    rel = p - root
    t = float(np.clip(rel @ u, ext[0], ext[1]))
    return float(np.linalg.norm(rel - t * u))


def draw_u(rng, P=P):
    lo = np.array([BASE[0] + P["R_B_LO"] * 0 - 0.35, -P["Y_CAP"]])
    hi = np.array([P["X_CAP"], P["Y_CAP"]])
    for _ in range(10000):
        p = rng.uniform(lo, hi)
        if in_u(p, P):
            return p
    raise RuntimeError("U 采样耗尽")


def push_ok(cube, goal, P=P):
    d = goal - cube
    n = np.linalg.norm(d)
    if not (P["MIN_CG"] <= n <= P["PUSH_MAX"]):
        return False
    d = d / n
    lat = np.array([-d[1], d[0]])
    for s in (0.0, 1.0, -1.0):
        start = cube - 0.10 * d - 0.10 * s * lat
        r = np.linalg.norm(start - BASE)
        if not (P["R_B_LO"] <= r <= P["R_B_HI"]):
            return False
    return True


def sample_segment(rng, P=P):
    """杆（抓取点 + yaw）→ goal → 方块；返回布局与各级尝试次数。"""
    peg_tries = 0
    while True:
        peg_tries += 1
        tail = draw_u(rng, P)
        yaw = float(rng.uniform(-math.pi, math.pi))
        u = np.array([math.cos(yaw), math.sin(yaw)])
        root = tail - TAIL_T * u
        if seg_dist(np.zeros(2), root, yaw) >= P["R_IN"]:
            break
    goal_tries = 0
    while True:
        goal_tries += 1
        goal = draw_u(rng, P)
        if seg_dist(goal, root, yaw) >= P["GOAL_PEG_GAP"]:
            break
    cube_tries = 0
    while True:
        cube_tries += 1
        cube = draw_u(rng, P)
        if seg_dist(cube, root, yaw) >= P["PEG_GAP"] and push_ok(cube, goal, P):
            break
        if cube_tries >= 200:   # goal 太偏时重抽 goal
            goal = draw_u(rng, P); cube_tries = 0; goal_tries += 1
    return dict(root=root, tail=tail, peg_yaw=yaw, goal=goal, cube=cube,
                cube_yaw=float(rng.uniform(0, 2 * math.pi)),
                peg_tries=peg_tries, goal_tries=goal_tries, cube_tries=cube_tries)


def area(P=P, n=1200):
    xs = np.linspace(-0.45, 0.25, n); ys = np.linspace(-0.35, 0.35, n)
    X, Y = np.meshgrid(xs, ys)
    pts = np.stack([X.ravel(), Y.ravel()], 1)
    rb = np.linalg.norm(pts - BASE, axis=1); rc = np.linalg.norm(pts, axis=1)
    ok = (rb >= P["R_B_LO"]) & (rb <= P["R_B_HI"]) & (rc >= P["R_IN"]) & (np.abs(pts[:, 1]) <= P["Y_CAP"]) & (pts[:, 0] <= P["X_CAP"]) & (pts[:, 0] >= P["X_LO"])
    cell = (xs[1] - xs[0]) * (ys[1] - ys[0])
    return float(ok.sum() * cell)


if __name__ == "__main__":
    import sys
    base_area = area(dict(P, R_IN=0.0))
    print(f"U（不挖中心）面积 {base_area:.4f} m²；V5 xhard 方块框 ±0.10 面积 {0.04:.4f}，goal 演示框 ±0.11 面积 {0.0484:.4f}")
    print("R_IN  面积m²  占不挖比例  平均尝试(杆/goal/方块)  推距均值  方块-基座均值  抓杆点x>0.10比例")
    for rin in (0.08, 0.10, 0.12, 0.14, 0.16):
        Pi = dict(P, R_IN=rin)
        rng = np.random.default_rng(1)
        segs = [sample_segment(rng, Pi) for _ in range(1500)]
        pl = np.mean([np.linalg.norm(s["goal"] - s["cube"]) for s in segs])
        cb = np.mean([np.linalg.norm(s["cube"] - BASE) for s in segs])
        tx = np.mean([s["tail"][0] > 0.10 for s in segs])
        tr = np.mean([[s["peg_tries"], s["goal_tries"], s["cube_tries"]] for s in segs], 0)
        print(f"{rin:.2f}  {area(Pi):.4f}  {area(Pi)/base_area:.2f}   {tr[0]:.1f}/{tr[1]:.1f}/{tr[2]:.1f}   {pl:.3f}   {cb:.3f}   {tx:.2f}")
