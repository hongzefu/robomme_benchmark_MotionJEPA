#!/usr/bin/env python3
"""统一区域 U 的目视图：区域形状（叠 A/B 实测硬边界）、2000 段采样散点、三局示例布局、距离直方图。"""
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Polygon
import numpy as np
from region import P, BASE, EXT, sample_segment, in_u, area

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def u_mask_patch(ax, P, color="#cde8cd"):
    xs = np.linspace(-0.45, 0.25, 700); ys = np.linspace(-0.35, 0.35, 700)
    X, Y = np.meshgrid(xs, ys)
    rb = np.hypot(X - BASE[0], Y - BASE[1]); rc = np.hypot(X - P["C0"][0], Y - P["C0"][1])
    ok = (rb >= P["R_B_LO"]) & (rb <= P["R_B_HI"]) & (rc >= P["R_IN"]) & (rc <= P["R_OUT"])
    ax.contourf(X, Y, ok.astype(float), levels=[0.5, 1.5], colors=[color], alpha=0.9)
    ax.contour(X, Y, ok.astype(float), levels=[0.5], colors=["green"], linewidths=1.2)


def frame(ax, lim=0.34):
    ax.set_xlim(-0.40, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal")
    ax.axhline(0, color="gray", lw=0.3); ax.axvline(0, color="gray", lw=0.3)
    ax.set_xlabel("x（m，+x 远离机器人）", fontsize=8); ax.set_ylabel("y（m）", fontsize=8); ax.tick_params(labelsize=7)


def main():
    rng = np.random.default_rng(2026)
    segs = [sample_segment(rng) for _ in range(2000)]
    fig, axes = plt.subplots(2, 3, figsize=(17, 11))
    # (0,0) 区域形状与硬边界
    ax = axes[0, 0]; u_mask_patch(ax, P)
    for r, ls, lab in ((0.31, ":", "A/B 实测：离基座 0.31 以内抓不到"), (0.80, ":", "A/B 实测：离基座 0.80 以外抓不到"),
                       (P["R_B_LO"], "--", f"U 内界 {P['R_B_LO']}"), (P["R_B_HI"], "--", f"U 外界 {P['R_B_HI']}")):
        ax.add_patch(Circle(BASE, r, fill=False, ec="red" if ls == ":" else "green", ls=ls, lw=1.2, label=lab))
    ax.add_patch(Circle(P["C0"], P["R_IN"], fc="#ffcccc", ec="red", lw=1, alpha=0.7, label=f"圆环内孔 R_IN={P['R_IN']}（挖掉）"))
    ax.add_patch(Circle(P["C0"], P["R_OUT"], fill=False, ec="green", lw=1.5, label=f"圆环外径 R_OUT={P['R_OUT']}"))
    ax.add_patch(Circle(P["C0"], 0.245, fill=False, ec="red", ls=":", lw=1, label="A 实测：此圆心最大可达圆 0.245"))
    ax.plot(*P["C0"], marker="+", color="green", ms=12, mew=2, label=f"圆心 C0={P['C0']}（可达环带中点）")
    ax.plot(0, 0, marker="+", color="gray", ms=8, mew=1, label="桌心 (0,0)")
    ax.add_patch(Rectangle((-0.10, -0.10), 0.2, 0.2, fill=False, ec="tab:blue", ls="-", lw=1, label="V5 xhard 方块候选框 ±0.10"))
    ax.add_patch(Rectangle((-0.06, -0.06), 0.12, 0.12, fill=False, ec="tab:orange", ls="-", lw=1, label="V5 执行段 goal 框 ±0.06"))
    for by in (-0.2, 0.2):
        ax.add_patch(Rectangle((-0.05, by - 0.05), 0.1, 0.1, fill=False, ec="tab:purple", lw=1, label="V5 杆根框" if by > 0 else None))
    ax.plot(*BASE, "ks", ms=7, label="机器人基座 (−0.615, 0)")
    frame(ax); ax.legend(fontsize=6.5, loc="lower left")
    ax.set_title(f"统一区域 U 第二版（绿圆环）：面积 {area():.3f} m²，V5 方块框 0.040 m²", fontsize=9)
    # (0,1) 抓取点与杆根散点
    ax = axes[0, 1]; u_mask_patch(ax, P)
    tails = np.array([s["tail"] for s in segs]); roots = np.array([s["root"] for s in segs])
    ax.scatter(tails[:, 0], tails[:, 1], s=2, color="tab:purple", alpha=0.35, label="抓杆点（杆尾中心）2000 段")
    ax.scatter(roots[:, 0], roots[:, 1], s=2, color="tab:brown", alpha=0.25, label="杆根（由抓杆点+yaw 推出）")
    for s in segs[:40]:
        u = np.array([math.cos(s["peg_yaw"]), math.sin(s["peg_yaw"])])
        p0, p1 = s["root"] + EXT[0] * u, s["root"] + EXT[1] * u
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color="tab:brown", lw=1, alpha=0.4)
    ax.add_patch(Circle(P["C0"], P["R_IN"], fill=False, ec="red", lw=1)); ax.plot(*BASE, "ks", ms=6)
    frame(ax); ax.legend(fontsize=7, loc="lower left")
    ax.set_title("杆：抓杆点在圆环内均匀，yaw 全 2π；杆身不进内孔（细线=前 40 段杆身）", fontsize=9)
    # (0,2) 方块与 goal 散点
    ax = axes[0, 2]; u_mask_patch(ax, P)
    cubes = np.array([s["cube"] for s in segs]); goals = np.array([s["goal"] for s in segs])
    ax.scatter(goals[:, 0], goals[:, 1], s=2, color="tab:green", alpha=0.35, label="goal 中心")
    ax.scatter(cubes[:, 0], cubes[:, 1], s=2, color="tab:blue", alpha=0.35, label="方块中心（yaw 全 2π）")
    ax.add_patch(Circle(P["C0"], P["R_IN"], fill=False, ec="red", lw=1)); ax.plot(*BASE, "ks", ms=6)
    frame(ax); ax.legend(fontsize=7, loc="lower left")
    ax.set_title(f"方块与 goal 在 U 内均匀；|方块−goal| ∈ [{P['MIN_CG']}, {P['PUSH_MAX']}]，推起点也在可达环带内", fontsize=9)
    # (1,0..1) 两局示例
    for k, ax in enumerate(axes[1, :2]):
        u_mask_patch(ax, P)
        for tag, col, s in (("演示段", "tab:blue", segs[2 * k]), ("执行段", "tab:orange", segs[2 * k + 1])):
            u = np.array([math.cos(s["peg_yaw"]), math.sin(s["peg_yaw"])])
            p0, p1 = s["root"] + EXT[0] * u, s["root"] + EXT[1] * u
            ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=col, lw=4, alpha=0.7, label=f"{tag} 杆")
            ax.plot(*s["tail"], marker="x", color=col, ms=7, mew=2)
            ax.add_patch(Circle(s["goal"], 0.04, fc=col, alpha=0.25, ec=col))
            sq = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]) * 0.02
            yw = s["cube_yaw"]; Rm = np.array([[math.cos(yw), -math.sin(yw)], [math.sin(yw), math.cos(yw)]])
            sq = sq @ Rm.T + s["cube"]; ax.plot(sq[:, 0], sq[:, 1], color=col, lw=1.5)
            ax.annotate("", xy=s["goal"], xytext=s["cube"], arrowprops=dict(arrowstyle="->", color=col, lw=0.8))
        ax.add_patch(Circle(P["C0"], P["R_IN"], fill=False, ec="red", lw=1)); ax.plot(*BASE, "ks", ms=6)
        frame(ax); ax.legend(fontsize=7, loc="lower left")
        ax.set_title(f"示例局 {k + 1}：杆身粗线、× 为抓杆点、方块小方框、goal 圆盘、箭头=推向", fontsize=9)
    # (1,2) 直方图
    ax = axes[1, 2]
    pl = np.linalg.norm(goals - cubes, axis=1)
    ax.hist(np.linalg.norm(cubes - BASE, axis=1), bins=40, range=(0.3, 0.85), alpha=0.5, label="方块离基座")
    ax.hist(np.linalg.norm(tails - BASE, axis=1), bins=40, range=(0.3, 0.85), alpha=0.5, label="抓杆点离基座")
    ax.hist(pl, bins=40, range=(0.0, 0.45), alpha=0.5, label=f"方块−goal 推距（均值 {pl.mean():.3f}）")
    ax.axvline(0.80, color="red", ls=":", lw=1); ax.axvline(0.31, color="red", ls=":", lw=1)
    ax.set_xlabel("m", fontsize=8); ax.tick_params(labelsize=7); ax.legend(fontsize=7)
    ax.set_title("距离分布（红点线 = A/B 实测的可达硬边界 0.31 / 0.80）", fontsize=9)
    fig.suptitle("MoveCube V6 统一生成区域 U 第二版：以可达范围中心为圆心的圆环，杆抓取点 / 方块 / goal 共用，朝向全随机（离线 2000 段）", fontsize=11)
    fig.tight_layout(h_pad=2.5, rect=[0, 0, 1, 0.965])
    fig.savefig("unified_region_v2.png", dpi=110)
    print("WROTE unified_region_v2.png")


if __name__ == "__main__":
    main()
