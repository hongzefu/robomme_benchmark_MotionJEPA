#!/usr/bin/env python3
"""画 w_results.png：上排三列俯视图（每种 way 一列），下排按「最远物体离基座距离」分箱的成功率。"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
HERE = Path(__file__).resolve().parent
WAYS = ["peg_push", "gripper_push", "grasp_putdown"]
WAY_ZH = {"peg_push": "peg_push（用杆钩）", "gripper_push": "gripper_push（夹爪推）", "grasp_putdown": "grasp_putdown（抓放）"}
BASE = np.array([-0.615, 0.0])
OK_C, FAIL_C = "#2a9d8f", "#d62828"


def far_dist(L):
    return max(np.hypot(L[f"{s}_{o}_x"] - BASE[0], L[f"{s}_{o}_y"] - BASE[1])
               for s in ("demo", "exec") for o in ("cube", "goal"))


def main():
    dirs = sys.argv[1:] or [str(HERE), str(HERE / "supp")]
    rs = []
    for d in dirs:
        rs += [json.loads(l) for l in (Path(d) / "results.jsonl").open()]
    fig = plt.figure(figsize=(16, 10.5))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.35, 1], hspace=0.32, wspace=0.18)
    bins = np.array([0.40, 0.50, 0.60, 0.70, 0.80, 0.82])
    for col, way in enumerate(WAYS):
        sub = [r for r in rs if r["way"] == way]
        ax = fig.add_subplot(gs[0, col])
        th = np.linspace(0, 2 * np.pi, 400)
        for rr in (0.06, 0.24):
            ax.plot(rr * np.cos(th), rr * np.sin(th), color="0.45", lw=1, ls="--")
        ax.axvline(0.20, color="0.3", lw=1, ls=":")
        ax.text(0.205, -0.27, "x=0.20", fontsize=8, color="0.3")
        # 失败局画在上层
        for r in sorted(sub, key=lambda r: r["ok"], reverse=True):
            L = r["layout"]
            c = OK_C if r["ok"] else FAIL_C
            a = 0.45 if r["ok"] else 0.95
            for s, mk_fill in (("demo", True), ("exec", False)):
                fc = c if mk_fill else "none"
                ax.scatter(L[f"{s}_cube_x"], L[f"{s}_cube_y"], marker="s", s=26, facecolors=fc, edgecolors=c, alpha=a, lw=1)
                ax.scatter(L[f"{s}_goal_x"], L[f"{s}_goal_y"], marker="o", s=26, facecolors=fc, edgecolors=c, alpha=a, lw=1)
                ax.scatter(L[f"{s}_peg_x"], L[f"{s}_peg_y"], marker="^", s=22, facecolors=fc, edgecolors=c, alpha=a, lw=1)
        ok = sum(r["ok"] for r in sub)
        ax.set_title(f"{WAY_ZH[way]}：成功 {ok}/{len(sub)}", fontsize=12)
        ax.set_xlim(-0.30, 0.30)
        ax.set_ylim(-0.30, 0.30)
        ax.set_aspect("equal")
        ax.set_xlabel("桌面 x（m，+x 远离机器人）")
        if col == 0:
            ax.set_ylabel("桌面 y（m）")
        ax.annotate("", xy=(-0.29, 0.0), xytext=(-0.22, 0.0), arrowprops=dict(arrowstyle="->", color="0.2"))
        ax.text(-0.295, 0.015, "基座 (-0.615,0)\n方向", fontsize=8, color="0.2")
        ax.grid(alpha=0.25)
        # 下排：按最远物体离基座距离分箱
        bx = fig.add_subplot(gs[1, col])
        d = np.array([far_dist(r["layout"]) for r in sub])
        okv = np.array([r["ok"] for r in sub])
        idx = np.clip(np.digitize(d, bins) - 1, 0, len(bins) - 2)
        rates, ns = [], []
        for b in range(len(bins) - 1):
            m = idx == b
            ns.append(int(m.sum()))
            rates.append(okv[m].mean() if m.any() else np.nan)
        xs = np.arange(len(bins) - 1)
        bx.bar(xs, np.nan_to_num(rates), color=[OK_C] * len(xs), alpha=0.8)
        for x, rt, n in zip(xs, rates, ns):
            txt = "无样本" if n == 0 else f"{rt * 100:.0f}%\nn={n}"
            bx.text(x, (0 if np.isnan(rt) else rt) + 0.03, txt, ha="center", va="bottom", fontsize=9)
        bx.set_xticks(xs)
        bx.set_xticklabels([f"{bins[i]:.2f}–{bins[i + 1]:.2f}" for i in xs], fontsize=9)
        bx.set_ylim(0, 1.3)
        bx.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        bx.set_yticklabels(["0", "25%", "50%", "75%", "100%"])
        bx.set_xlabel("本局最远物体（方块/goal，两段取最大）离基座距离（m）")
        if col == 0:
            bx.set_ylabel("演示成功率")
        bx.grid(axis="y", alpha=0.25)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker="s", ls="", color="0.3", label="方块"),
               Line2D([], [], marker="o", ls="", color="0.3", label="goal"),
               Line2D([], [], marker="^", ls="", color="0.3", label="杆根"),
               Line2D([], [], marker="s", ls="", mfc="0.3", mec="0.3", label="实心=演示段"),
               Line2D([], [], marker="s", ls="", mfc="none", mec="0.3", label="空心=执行段"),
               Line2D([], [], marker="o", ls="", color=OK_C, label="成功局"),
               Line2D([], [], marker="o", ls="", color=FAIL_C, label="失败局"),
               Line2D([], [], ls="--", color="0.45", label="环带 0.06/0.24")]
    fig.legend(handles=handles, loc="upper center", ncol=8, fontsize=10, bbox_to_anchor=(0.5, 0.965), frameon=False)
    n = len(rs)
    fig.suptitle(f"MoveCube 放宽区域 W 实测（{n} 局真实演示，杆/方块 yaw 全 2π）", fontsize=15, y=0.995)
    out = HERE / "w_results.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
