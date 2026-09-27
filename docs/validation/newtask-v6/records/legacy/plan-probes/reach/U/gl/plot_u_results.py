#!/usr/bin/env python3
"""GL 复测 144 局结果俯视图：每种 way 一列，成功/失败着色，叠统一区域 U 轮廓；下排按最远物体离基座距离分箱的成功率。"""
import csv, json, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.lines import Line2D
import numpy as np
from region import P, BASE, EXT

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
lay = {int(r["episode"]): r for r in csv.DictReader(open("layouts.csv"))}
rs = [json.loads(l) for l in open("results.jsonl")]
WAYS = [("peg_push", "peg_push（用杆钩）"), ("gripper_push", "gripper_push（夹爪推）"), ("grasp_putdown", "grasp_putdown（抓放）")]


def u_outline(ax):
    xs = np.linspace(-0.45, 0.25, 600); ys = np.linspace(-0.35, 0.35, 600)
    X, Y = np.meshgrid(xs, ys)
    rb = np.hypot(X - BASE[0], Y); rc = np.hypot(X, Y)
    ok = (rb >= P["R_B_LO"]) & (rb <= P["R_B_HI"]) & (rc >= P["R_IN"]) & (np.abs(Y) <= P["Y_CAP"]) & (X <= P["X_CAP"]) & (X >= P["X_LO"])
    ax.contourf(X, Y, ok.astype(float), levels=[0.5, 1.5], colors=["#e4f2e4"])
    ax.contour(X, Y, ok.astype(float), levels=[0.5], colors=["green"], linewidths=1.0)


fig, axes = plt.subplots(2, 3, figsize=(16.5, 10.5))
for j, (w, wl) in enumerate(WAYS):
    ax = axes[0, j]; u_outline(ax)
    v = [r for r in rs if lay[r["episode"]]["way"] == w]
    for r in v:
        L = lay[r["episode"]]; col = "#2a9d8f" if r["ok"] else "#e63946"
        for seg, fill in (("demo", True), ("exec", False)):
            c = (float(L[f"{seg}_cube_x"]), float(L[f"{seg}_cube_y"])); g = (float(L[f"{seg}_goal_x"]), float(L[f"{seg}_goal_y"]))
            t = (float(L[f"{seg}_tail_x"]), float(L[f"{seg}_tail_y"]))
            kw = dict(color=col, alpha=0.75 if fill else 0.5, mfc=col if fill else "none", ms=5, ls="none", mew=1)
            ax.plot(*c, marker="s", **kw); ax.plot(*g, marker="o", **kw); ax.plot(*t, marker="^", **kw)
    ax.plot(*BASE, "ks", ms=6); ax.annotate("基座 (−0.615, 0)", xy=BASE, xytext=(-0.60, 0.03), fontsize=7, color="gray")
    ax.set_xlim(-0.66, 0.32); ax.set_ylim(-0.36, 0.36); ax.set_aspect("equal")
    ax.set_xlabel("桌面 x（m，+x 远离机器人）", fontsize=8); ax.set_ylabel("桌面 y（m）", fontsize=8); ax.tick_params(labelsize=7)
    ax.set_title(f"{wl}：成功 {sum(r['ok'] for r in v)}/{len(v)}", fontsize=10)
    # 下排
    ax = axes[1, j]
    def far(r):
        L = lay[r["episode"]]
        return max(float(L[f"{s}_{o}_base_d"]) for s in ("demo", "exec") for o in ("cube", "goal"))
    bins = [(0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 0.80)]
    labels, rates, ns = [], [], []
    for lo, hi in bins:
        a = [r["ok"] for r in v if lo <= far(r) < hi]
        labels.append(f"{lo:.2f}–{hi:.2f}"); ns.append(len(a)); rates.append(sum(a) / len(a) if a else np.nan)
    ax.bar(labels, [0 if np.isnan(x) else x for x in rates], color="#2a9d8f")
    for i, (x, n) in enumerate(zip(rates, ns)):
        ax.text(i, (0 if np.isnan(x) else x) + 0.03, ("无样本" if n == 0 else f"{x*100:.0f}%\nn={n}"), ha="center", fontsize=8)
    ax.set_ylim(0, 1.25); ax.set_yticks([0, .25, .5, .75, 1]); ax.set_yticklabels(["0", "25%", "50%", "75%", "100%"], fontsize=7)
    ax.set_xlabel("本局最远物体（方块/goal，两段取最大）离基座距离（m）", fontsize=8); ax.set_ylabel("演示成功率", fontsize=8); ax.tick_params(axis="x", labelsize=7)
handles = [Line2D([], [], marker="s", ls="none", color="gray", label="方块"), Line2D([], [], marker="o", ls="none", color="gray", label="goal"),
           Line2D([], [], marker="^", ls="none", color="gray", label="抓杆点（杆尾）"),
           Line2D([], [], marker="s", ls="none", color="gray", label="实心=演示段"), Line2D([], [], marker="s", ls="none", mfc="none", color="gray", label="空心=执行段"),
           Line2D([], [], marker="o", ls="none", color="#2a9d8f", label="成功局"), Line2D([], [], marker="o", ls="none", color="#e63946", label="失败局"),
           Line2D([], [], color="green", label="统一区域 U 轮廓")]
fig.legend(handles=handles, loc="upper center", ncol=8, fontsize=8, bbox_to_anchor=(0.5, 0.945), frameon=False)
tot = sum(r["ok"] for r in rs)
fig.suptitle(f"MoveCube 统一区域 U 复测（greatlakes A40，真实演示链路 144 局，成功 {tot}/144；杆/方块 yaw 全 2π）", fontsize=12)
fig.tight_layout(rect=[0, 0, 1, 0.93], h_pad=2.5)
fig.savefig("u_results.png", dpi=110); print("WROTE u_results.png")
