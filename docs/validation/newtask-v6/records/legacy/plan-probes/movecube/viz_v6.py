#!/usr/bin/env python3
"""MoveCube「往外推」采样分布可视化（俯视图）：V5 xhard 基线 vs 环带 T1/T2/T3。

用 mc_v6.simulate 的离线副本（已与 v5-01 逐值核对）跑 N 局，画：
  第 1 行：每方案一局示例布局（杆身线段、方块、goal 圆盘、禁区/环带、采样框、机器人基座方向）
  第 2 行：方块最终中心散点（演示段 + 执行段），叠禁区/环带
  第 3 行：goal 中心散点
  第 4 行：方块中心到桌面中心距离的直方图
输出 PNG 到本目录。
"""
from __future__ import annotations

import math
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
import numpy as np

from mc_v6 import V5, simulate, PEG_SEG

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
XCAP = 0.11
BASE = (-0.615, 0.0)

SCHEMES = {
    "V5 xhard（现状）\n禁区 R=0.05 圆，框 goal 0.11/0.06、方块 0.10": dict(),
    "环带 T1 [0.08,0.12]\n框 0.12，x≤0.11，离杆≥0.04": dict(ge_half=0.12, cand_half=0.12, gd_half=0.12, R=0.08, R_out=0.12, x_cap=XCAP, peg_gap=0.04, peg_gap_cand_extra=0.02),
    "环带 T2 [0.10,0.14]（建议）\n框 0.14，x≤0.11，离杆≥0.04": dict(ge_half=0.14, cand_half=0.14, gd_half=0.14, R=0.10, R_out=0.14, x_cap=XCAP, peg_gap=0.04, peg_gap_cand_extra=0.02),
    "环带 T3 [0.12,0.16]\n框 0.16，x≤0.11，离杆≥0.04": dict(ge_half=0.16, cand_half=0.16, gd_half=0.16, R=0.12, R_out=0.16, x_cap=XCAP, peg_gap=0.04, peg_gap_cand_extra=0.02),
}

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "Noto Serif CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def run(kw):
    cubes, goals, pegs, ok, example = [], [], [], 0, None
    for i in range(N):
        o = simulate(7_000_000 + i, **kw)
        if not o.ok:
            continue
        ok += 1
        for s in ("demo", "exec"):
            seg = o.seg[s]
            cubes.append(seg["cube"]); goals.append(seg["goal"]); pegs.append((seg["peg_root"], seg["peg_yaw"]))
        if example is None:
            example = o
    return np.array(cubes), np.array(goals), pegs, ok, example


def draw_ring(ax, kw):
    P = dict(V5); P.update(kw)
    ax.add_patch(Circle((0, 0), P["R"], fill=True, fc="#ffcccc", ec="red", lw=1, alpha=0.6))
    if P["R_out"] is not None:
        ax.add_patch(Circle((0, 0), P["R_out"], fill=False, ec="red", lw=1, ls="--"))
    if P["x_cap"] is not None:
        ax.axvline(P["x_cap"], color="red", lw=1, ls=":")
    # 采样框：goal 演示/执行、方块候选
    for h, c, lab in ((P["gd_half"], "tab:green", "goal 演示框"), (P["ge_half"], "tab:olive", "goal 执行框"), (P["cand_half"], "tab:blue", "方块候选框")):
        ax.add_patch(Rectangle((-h, -h), 2 * h, 2 * h, fill=False, ec=c, lw=0.8, ls="-."))


def draw_example(ax, o, kw):
    draw_ring(ax, kw)
    for s, col in (("demo", "tab:blue"), ("exec", "tab:orange")):
        seg = o.seg[s]
        root, yaw = seg["peg_root"], seg["peg_yaw"]
        u = np.array([math.cos(yaw), math.sin(yaw)])
        p0, p1 = root + PEG_SEG[0] * u, root + PEG_SEG[1] * u
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=col, lw=4, alpha=0.7, label=f"{s} 杆")
        ax.add_patch(Circle(seg["goal"], 0.04, fc=col, alpha=0.25, ec=col))
        c = seg["cube"]; yw = seg["cube_yaw"]
        sq = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]) * 0.02
        Rm = np.array([[math.cos(yw), -math.sin(yw)], [math.sin(yw), math.cos(yw)]])
        sq = sq @ Rm.T + c
        ax.plot(sq[:, 0], sq[:, 1], color=col, lw=1.5)
        ax.annotate("", xy=seg["goal"], xytext=c, arrowprops=dict(arrowstyle="->", color=col, lw=0.8, alpha=0.6))
    ax.annotate("机器人基座 →", xy=(-0.28, -0.27), fontsize=7, color="gray")
    ax.legend(fontsize=6, loc="upper right")


def main():
    fig, axes = plt.subplots(4, len(SCHEMES), figsize=(4.4 * len(SCHEMES), 18))
    lim = 0.30
    for j, (name, kw) in enumerate(SCHEMES.items()):
        cubes, goals, pegs, ok, ex = run(kw)
        ax = axes[0, j]; draw_example(ax, ex, kw)
        ax.set_title(f"{name}\n示例一局，布局成功 {ok}/{N}", fontsize=8)
        ax = axes[1, j]; draw_ring(ax, kw)
        ax.scatter(cubes[:, 0], cubes[:, 1], s=1.5, alpha=0.25, color="tab:blue")
        r = np.hypot(cubes[:, 0], cubes[:, 1])
        ax.set_title(f"方块中心（{len(cubes)} 个）  r 均值 {r.mean():.3f}，min {r.min():.3f}", fontsize=8)
        ax = axes[2, j]; draw_ring(ax, kw)
        ax.scatter(goals[:, 0], goals[:, 1], s=1.5, alpha=0.25, color="tab:green")
        rg = np.hypot(goals[:, 0], goals[:, 1])
        ax.set_title(f"goal 中心  r 均值 {rg.mean():.3f}，min {rg.min():.3f}", fontsize=8)
        for ax in axes[:3, j]:
            ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal")
            ax.axhline(0, color="gray", lw=0.3); ax.axvline(0, color="gray", lw=0.3)
            ax.set_xlabel("x（+x 远离机器人）", fontsize=7); ax.set_ylabel("y", fontsize=7)
            ax.tick_params(labelsize=6)
        ax = axes[3, j]
        d = np.linalg.norm(cubes - goals, axis=1)
        ax.hist(r, bins=40, range=(0, 0.25), alpha=0.6, label="方块中心离桌心 r")
        ax.hist(rg, bins=40, range=(0, 0.25), alpha=0.6, label="goal 中心离桌心 r")
        ax.hist(d, bins=40, range=(0, 0.45), alpha=0.4, label=f"方块-goal 距离（均值 {d.mean():.3f}）")
        ax.legend(fontsize=6); ax.tick_params(labelsize=6); ax.set_xlabel("m", fontsize=7)
    fig.suptitle("MoveCube xhard 采样分布俯视图：V5 现状 vs V6 环带候选（离线副本 2000 局；蓝=演示段，橙=执行段）", fontsize=11)
    fig.tight_layout(h_pad=2.5, rect=[0, 0, 1, 0.965])
    out = "movecube_v6_layouts.png"
    fig.savefig(out, dpi=110)
    print("WROTE", out)


if __name__ == "__main__":
    main()
