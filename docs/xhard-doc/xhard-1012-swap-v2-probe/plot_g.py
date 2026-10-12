"""把 probe_g.json 画成俯视 2D 图：槽位、可行/不可行槽对、v1 与新策略的交换序列。"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from matplotlib import font_manager
font_manager.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
matplotlib.rcParams["font.family"] = [font_manager.FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc").get_name()]
HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "probe_g.json").read_text())
COL = ["#d1495b", "#2e86ab", "#edae49", "#66a182"]


def yaw(q):
    w, x, y, z = q
    return np.degrees(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


fig, axes = plt.subplots(2, 3, figsize=(18, 10.5), gridspec_kw={"height_ratios": [3, 1.3]})
for col, c in enumerate(data):
    ax = axes[0, col]
    P = np.array(c["slots"])
    half = 0.0275
    n = len(P)
    for a in range(n):
        for b in range(a + 1, n):
            ok = c["adj"][a][b]
            g = c["gaps"][f"{a}-{b}"] * 1000
            ax.plot(*zip(P[a], P[b]), color="#2a9d4b" if ok else "#c0392b", lw=3 if ok else 1.6,
                    ls="-" if ok else "--", zorder=1)
            t = 0.5 if ok else 0.3
            m = P[a] * (1 - t) + P[b] * t
            ax.text(m[0], m[1], f"{'可行' if ok else '撞'} {g:+.1f}mm", fontsize=10, ha="center", va="center",
                    color="#1e7a35" if ok else "#a93226",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9), zorder=3)
    for i, p in enumerate(P):
        ang = yaw(c["yaw_q"][i])
        r = Rectangle((p[0] - half, p[1] - half), 2 * half, 2 * half, angle=ang, rotation_point="center",
                      fc=COL[i], ec="black", alpha=0.85, zorder=2)
        ax.add_patch(r)
        ax.text(p[0], p[1], f"槽{i}", fontsize=12, ha="center", va="center", color="white", weight="bold", zorder=4)
    # 最近邻：小箭头提示
    status = "连通" if c["connected"] else "不连通"
    ax.set_title(f"{c['task']}  seed {c['seed']}\n可行槽对图 G：{sum(c['adj'][a][b] for a in range(n) for b in range(a+1, n))}/6 条边，{status}",
                 fontsize=13)
    ax.set_aspect("equal")
    pad = 0.07
    ax.set_xlim(P[:, 0].min() - pad, P[:, 0].max() + pad)
    ax.set_ylim(P[:, 1].min() - pad, P[:, 1].max() + pad)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.grid(alpha=0.3)

    tx = axes[1, col]
    tx.axis("off")
    lines = []
    if c["v1"]["error"]:
        lines.append("v1 最近邻：第 0 段就扫掠接触 → 整卡剔除")
    else:
        slot_of = list(range(n))
        sp_pairs = []
        for a, b in c["v1"]["pairs"]:
            sp_pairs.append((slot_of[a], slot_of[b]))
            slot_of[a], slot_of[b] = slot_of[b], slot_of[a]
        used1 = {tuple(sorted(x)) for x in sp_pairs}
        lines.append("v1 最近邻（槽对，前一个是发起者）：")
        lines.append("  " + " ".join(f"{a}{b}" for a, b in sp_pairs))
        lines.append(f"  参与次数 {c['v1']['usage']}  只用到 {len(used1)} 种槽对")
    v2 = c["v2_noconn"]
    used = sorted({tuple(sorted(p)) for p in v2["slot_pairs"]})
    lines.append("")
    lines.append("新策略（槽对，前一个是发起者）：")
    sp2 = " ".join(f"{a}{b}" for a, b in v2["slot_pairs"])
    lines.append("  " + sp2[:47])
    if len(sp2) > 47:
        lines.append("  " + sp2[47:])
    lines.append(f"  参与次数 {v2['counts']}  极差 {v2['spread']}  用到 {len(used)} 种槽对")
    lines.append("")
    if c["connected"]:
        verdict = "G 连通：照 V9 要求连通也能通过"
    elif v2["spread"] <= 1:
        verdict = "G 不连通（两对互不相通）：V9 会拒绝；\n若只要求「有边」则可行、且均衡"
    else:
        verdict = "G 不连通（槽3 一条可行边都没有）：V9 会拒绝；\n若只要求「有边」则可行，但槽3 的容器永远不动"
    lines.append(verdict)
    tx.text(0.0, 1.0, "\n".join(lines), fontsize=12.5, va="top", ha="left")

fig.suptitle("新交换策略实测（xhard20 布局，S=11/12）：绿实线=整段扫掠无接触可选，红虚线=会撞被排除，数字=最小间隙", fontsize=14)
fig.tight_layout(rect=(0, 0, 1, 0.96))
out = Path(sys.argv[1])
fig.savefig(out, dpi=110)
print("SAVED", out)
