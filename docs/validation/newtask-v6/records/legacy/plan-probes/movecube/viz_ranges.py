#!/usr/bin/env python3
"""MoveCube 现状（V5 xhard）三种物体各自的采样范围俯视图，与 V6 环带 T2 对照。

每列一物体：杆根 / 方块 / goal；每行一方案：V5 现状 / V6 T2。
框线 = 该物体的采样框（源码常量），散点 = 离线副本 2000 局的实际落点（蓝=演示段，橙=执行段）。
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

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

T2 = dict(ge_half=0.14, cand_half=0.14, gd_half=0.14, R=0.10, R_out=0.14, x_cap=0.11, peg_gap=0.04, peg_gap_cand_extra=0.02)
ROWS = [("V5 xhard 现状", dict()), ("V6 环带 T2（建议）", T2)]
COLS = ["杆根（peg root）与杆身", "方块（cube）最终中心", "goal 圆盘中心"]


def collect(kw):
    d = {s: dict(peg=[], yaw=[], cube=[], goal=[]) for s in ("demo", "exec")}
    for i in range(N):
        o = simulate(7_000_000 + i, **kw)
        if not o.ok:
            continue
        for s in ("demo", "exec"):
            seg = o.seg[s]
            d[s]["peg"].append(seg["peg_root"]); d[s]["yaw"].append(seg["peg_yaw"])
            d[s]["cube"].append(seg["cube"]); d[s]["goal"].append(seg["goal"])
    for s in d:
        for k in d[s]:
            d[s][k] = np.array(d[s][k])
    return d


def zone(ax, P):
    ax.add_patch(Circle((0, 0), P["R"], fc="#ffcccc", ec="red", lw=1, alpha=0.6, label=f"禁区 R={P['R']}"))
    if P["R_out"] is not None:
        ax.add_patch(Circle((0, 0), P["R_out"], fill=False, ec="red", lw=1, ls="--", label=f"环带外界 {P['R_out']}"))
    if P["x_cap"] is not None:
        ax.axvline(P["x_cap"], color="red", lw=1, ls=":", label=f"x ≤ {P['x_cap']}")


def main():
    fig, axes = plt.subplots(2, 3, figsize=(15, 12.5))
    lim = 0.32
    for r, (rname, kw) in enumerate(ROWS):
        P = dict(V5); P.update(kw)
        d = collect(kw)
        cols = {"demo": "tab:blue", "exec": "tab:orange"}
        # 杆
        ax = axes[r, 0]; zone(ax, P)
        for by in (-P["base_y_abs"], P["base_y_abs"]):
            j = P["jitter"] / 2
            ax.add_patch(Rectangle((-j, by - j), 2 * j, 2 * j, fill=False, ec="purple", lw=1.5, ls="-", label="杆根框 x∈±0.05, y∈±0.2±0.05" if by > 0 else None))
        for s, c in cols.items():
            roots, yaws = d[s]["peg"], d[s]["yaw"]
            for root, yaw in list(zip(roots, yaws))[:60]:
                u = np.array([math.cos(yaw), math.sin(yaw)])
                p0, p1 = root + PEG_SEG[0] * u, root + PEG_SEG[1] * u
                ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=c, lw=1, alpha=0.25)
            ax.scatter(roots[:, 0], roots[:, 1], s=2, color=c, alpha=0.4, label=f"{s} 杆根 ({len(roots)})")
        ax.set_title(f"{rname}｜{COLS[0]}", fontsize=9)
        ax.text(0, -0.31, "根在 y=±0.2 两带内均匀，yaw ±180°；杆身轴线离桌心 < R 则重抽；细线 = 前 60 局杆身", fontsize=6.5, ha="center", va="bottom", color="dimgray")
        # 方块
        ax = axes[r, 1]; zone(ax, P)
        h = P["cand_half"]
        ax.add_patch(Rectangle((-h, -h), 2 * h, 2 * h, fill=False, ec="tab:blue", lw=1.5, ls="-.", label=f"候选框 ±{h}"))
        h2 = h + P["local"]
        ax.add_patch(Rectangle((-h2, -h2), 2 * h2, 2 * h2, fill=False, ec="tab:blue", lw=0.8, ls=":", label=f"候选 ±{P['local']} 局部抖动后的最大范围 ±{h2:.2f}"))
        for s, c in cols.items():
            pts = d[s]["cube"]
            ax.scatter(pts[:, 0], pts[:, 1], s=2, color=c, alpha=0.3, label=f"{s} 方块 ({len(pts)})")
        ax.set_title(f"{rname}｜{COLS[1]}", fontsize=9)
        ax.text(0, -0.31, f"候选在框内均匀，离 goal > {P['min_cg']} 且不在禁区；最终位置在候选 ±{P['local']} 内再抽", fontsize=6.5, ha="center", va="bottom", color="dimgray")
        # goal
        ax = axes[r, 2]; zone(ax, P)
        gd, ge = P["gd_half"], P["ge_half"]
        ax.add_patch(Rectangle((-gd, -gd), 2 * gd, 2 * gd, fill=False, ec="tab:blue", lw=1.5, ls="-.", label=f"演示段 goal 框 ±{gd}"))
        ax.add_patch(Rectangle((-ge, -ge), 2 * ge, 2 * ge, fill=False, ec="tab:orange", lw=1.5, ls="-.", label=f"执行段 goal 框 ±{ge}"))
        for s, c in cols.items():
            pts = d[s]["goal"]
            ax.scatter(pts[:, 0], pts[:, 1], s=2, color=c, alpha=0.3, label=f"{s} goal ({len(pts)})")
        ax.set_title(f"{rname}｜{COLS[2]}", fontsize=9)
        ax.text(0, -0.31, f"演示段框 ±{gd}、执行段框 ±{ge}；中心不在禁区", fontsize=6.5, ha="center", va="bottom", color="dimgray")
        for ax in axes[r]:
            ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal")
            ax.axhline(0, color="gray", lw=0.3); ax.axvline(0, color="gray", lw=0.3)
            ax.set_xlabel("x（+x 远离机器人）", fontsize=7); ax.set_ylabel("y", fontsize=7)
            ax.tick_params(labelsize=6); ax.legend(fontsize=6, loc="upper right")
    fig.suptitle("MoveCube 三种物体各自的采样范围：V5 xhard 现状（上）vs V6 环带 T2（下）；离线副本 2000 局，蓝=演示段、橙=执行段", fontsize=11)
    fig.tight_layout(h_pad=3.0, rect=[0, 0, 1, 0.97])
    fig.savefig("movecube_sampling_ranges.png", dpi=110)
    print("WROTE movecube_sampling_ranges.png")


if __name__ == "__main__":
    main()
