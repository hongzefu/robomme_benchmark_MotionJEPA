#!/usr/bin/env python3
"""第 2 问：逐对象 × 逐「中心」定义的拒绝率、有效区域、分布对比（纯 numpy，向量化）。

对象（均为各自 V4 采样盒）：
  peg   ：根点相对自身抖动盒中心 (0, ±0.2) 的偏移，盒半边 0.05（jitter_span 0.1）
  goalD ：演示段 goal，(0,0) 为中心、盒半边 0.11（region_half_size 0.15 - radius 0.04）
  goalE ：执行段 goal，盒半边 0.06（0.1 - 0.04）
  cand  ：方块候选中心，盒半边 0.1（center_span 0.2、center_offset -0.1）
  cubeF ：方块最终 xy = cand + 局部偏移（局部半边 0.03 = region_half_size 0.05 - 半边长 0.02），支撑盒半边 0.13
V4 xhard：peg/cand/局部 u 经 corner_push(b=0.5)；goal 从未加偏置（均匀）。

    cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <本文件>
"""
from __future__ import annotations

import math
import sys

import numpy as np

sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/src")
from robomme.robomme_env.utils.xhard import CORNER_GAIN  # noqa: E402

N = 400_000
RNG = np.random.default_rng(20260924)


def push(u, b):
    """utils/xhard.py::corner_push 的向量化等价式（b=0 原样返回）。"""
    if b == 0:
        return u
    t = 2 * u - 1
    p = 1.0 / (1.0 + CORNER_GAIN * b)
    return (1 + np.sign(t) * np.abs(t) ** p) / 2


def sample(obj, b):
    u = RNG.random((N, 2))
    if obj == "peg":
        return (push(u, b) - 0.5) * 0.1
    if obj == "goalD":
        return u * 0.22 - 0.11                 # goal 在 V4 里从不加偏置
    if obj == "goalE":
        return u * 0.12 - 0.06
    if obj == "cand":
        return push(u, b) * 0.2 - 0.1
    if obj == "cubeF":
        c = push(u, b) * 0.2 - 0.1
        v = RNG.random((N, 2))
        return c - 0.03 + push(v, b) * 0.06
    raise ValueError(obj)


HALF = {"peg": 0.05, "goalD": 0.11, "goalE": 0.06, "cand": 0.1, "cubeF": 0.13}


def inzone(xy, w, kind):
    ax, ay = np.abs(xy[:, 0]), np.abs(xy[:, 1])
    if kind == "square":
        return np.maximum(ax, ay) < w
    if kind == "disk":
        return np.hypot(ax, ay) < w
    if kind == "cross":
        return np.minimum(ax, ay) < w
    raise ValueError(kind)


S_AREA_SQ = math.sqrt(0.3)                  # 30% 面积的中心正方形边长比
S_AREA_DISK = math.sqrt(0.3 * 4 / math.pi)   # 30% 面积的中心圆半径比
DEFS = [
    # 名称, kind, 每对象禁区尺寸的函数(对象) -> w（米）
    ("a 逐轴30%方(面积9%)", "square", lambda o: 0.3 * HALF[o]),
    ("b 面积30%方(边比0.548)", "square", lambda o: S_AREA_SQ * HALF[o]),
    ("b' 面积30%圆(半径比0.618)", "disk", lambda o: S_AREA_DISK * HALF[o]),
    ("a' 十字30%(只留四角)", "cross", lambda o: 0.3 * HALF[o]),
    ("b* cube 用候选盒尺度(0.0548)", "square", lambda o: S_AREA_SQ * (0.1 if o in ("cand", "cubeF") else HALF[o])),
]
ABS_DEFS = [  # 公共绝对中心 (0,0)（定义 c）；peg 根点永远 |y|>=0.15，对 c 类定义恒不拒
    ("c 公共中心方 w=0.03(=0.3×候选半跨0.1)", "square", 0.03),
    ("c 公共中心方 w=0.045(=0.3×demo goal 区半边0.15)", "square", 0.045),
    ("c 公共中心圆 R=0.075(=0.3×杆根点 |y| 上界0.25)", "disk", 0.075),
]


def main():
    print(f"N={N} 每对象每方案；seed=20260924；CORNER_GAIN={CORNER_GAIN}")
    base = {o: {b: sample(o, b) for b in (0.0, 0.5)} for o in HALF}
    # 杆根点在公共中心坐标下的位置（取 base_y=+0.2 一侧，另一侧对称）
    print("\n== 表 1：拒绝率（V5 = bias 0 + 拒绝；一次抽样落入禁区的概率）与 V4 b=0.5 仍落入禁区的比例 ==")
    print(f"{'定义':<38}{'对象':<7}{'禁区尺寸w(m)':>12}{'V5拒绝率':>10}{'E[抽样次数]':>12}{'P(128次全拒)':>14}{'V4 b0.5 落入':>13}{'V4 b0 落入':>11}")
    for name, kind, wf in DEFS:
        for o in HALF:
            w = wf(o)
            p = float(np.mean(inzone(base[o][0.0], w, kind)))
            p4 = float(np.mean(inzone(base[o][0.5], w, kind))) if o not in ("goalD", "goalE") else p
            print(f"{name:<38}{o:<7}{w:>12.4f}{p:>10.3f}{1/(1-p):>12.2f}{p**128:>14.1e}{p4:>13.3f}{p:>11.3f}")
    for name, kind, w in ABS_DEFS:
        for o in HALF:
            if o == "peg":
                xy = base[o][0.0] + np.array([0.0, 0.2])
            else:
                xy = base[o][0.0]
            p = float(np.mean(inzone(xy, w, kind)))
            xy4 = base[o][0.5] + (np.array([0.0, 0.2]) if o == "peg" else 0)
            p4 = float(np.mean(inzone(xy4, w, kind))) if o not in ("goalD", "goalE") else p
            e = f"{1/(1-p):>12.2f}" if p < 1 else f"{'不可行':>12}"
            print(f"{name:<38}{o:<7}{w:>12.4f}{p:>10.3f}{e}{p**128:>14.1e}{p4:>13.3f}{p:>11.3f}")

    # 有效区域（逐对象，b 定义）
    print("\n== 表 2：推荐定义 b（面积 30% 中心方）下的有效采样区域 ==")
    for o in HALF:
        w = S_AREA_SQ * HALF[o]
        ctr = "(0, ±0.2)" if o == "peg" else "(0,0)"
        print(f"{o:<6} 盒 {ctr} ± {HALF[o]:.3f}  禁区 max(|dx|,|dy|) < {w:.4f}  ⇒ 允许 max(|dx|,|dy|) ∈ [{w:.4f}, {HALF[o]:.3f}]")

    # 分布对比：Chebyshev 归一化半径 ρ=max(|tx|,|ty|) 的直方图
    print("\n== 表 3：Chebyshev 归一化半径 ρ=max(|x|,|y|)/半边 的分布（每格 0.1；数值=该格概率%）==")
    bins = np.linspace(0, 1, 11)
    for o in ("peg", "goalD", "cand", "cubeF"):
        rows = []
        u0 = base[o][0.0]
        rho0 = np.max(np.abs(u0), axis=1) / HALF[o]
        rho5 = np.max(np.abs(base[o][0.5]), axis=1) / HALF[o]
        w = S_AREA_SQ * (0.1 if o in ("cand", "cubeF") else HALF[o])
        keep = ~inzone(u0, w, "square")
        rhoR = rho0[keep]
        # cubeF 在推荐方案里是「候选+最终都判」，这里单独给出它的真实分布需联合模拟，见 joint.py；此处仅示意最终判
        for lab, r in (("均匀(V4 b=0)", rho0), ("V4 b=0.5", rho5), ("V5 拒绝 b", rhoR)):
            h, _ = np.histogram(r, bins=bins)
            h = h / len(r) * 100
            rows.append(f"  {lab:<14}" + " ".join(f"{v:5.1f}" for v in h) + f" | E[ρ]={r.mean():.3f}")
        print(f"{o}（禁区 w/半边={w/HALF[o]:.3f}）  ρ 格: " + " ".join(f"{bins[i]:.1f}-" for i in range(10)))
        print("\n".join(rows))

    # 四角集中度：落在 ρ_x>0.8 且 ρ_y>0.8 的四个角块的概率
    print("\n== 表 4：四角集中度 P(|tx|>0.8 且 |ty|>0.8)（均匀=4%）与 P(任一轴 |t|>0.9)==")
    for o in ("peg", "cand", "cubeF", "goalD"):
        for lab, b in (("V4 b=0", 0.0), ("V4 b=0.5", 0.5)):
            t = np.abs(base[o][b]) / HALF[o]
            print(f"  {o:<6}{lab:<10} 四角={np.mean((t[:,0]>0.8)&(t[:,1]>0.8)):.3f}  任一轴>0.9={np.mean(np.max(t,axis=1)>0.9):.3f}")
        t = np.abs(base[o][0.0]) / HALF[o]
        w = S_AREA_SQ * (0.1 if o in ("cand", "cubeF") else HALF[o]) / HALF[o]
        k = np.max(t, axis=1) >= w
        tk = t[k]
        print(f"  {o:<6}{'V5 拒绝b':<10} 四角={np.mean((tk[:,0]>0.8)&(tk[:,1]>0.8)):.3f}  任一轴>0.9={np.mean(np.max(tk,axis=1)>0.9):.3f}")


if __name__ == "__main__":
    main()
