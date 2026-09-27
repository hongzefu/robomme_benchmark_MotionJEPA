"""图 2：可行槽对图 G（6 条边的可行率、G 连通率、典型 G 形态）。数据：p2_inner_*.json（每局 6 个槽对的仓库精确判定）。"""
import collections, json
import numpy as np
import matplotlib.pyplot as plt
import vizlib as V

# 槽的示意坐标：两环境的锚点都是长方形 region4 的四角（槽0/1 在一条短边、槽2/3 在另一条），对角线 = (0,2)、(1,3)
POS = {0: (-0.05, -0.1), 1: (-0.05, 0.1), 2: (0.1, 0.1), 3: (0.1, -0.1)}
TASKS = ["VideoUnmaskSwap", "ButtonUnmaskSwap"]
R = {t: json.load(open(f"p2_inner_{t}.json")) for t in TASKS}


def draw_graph(ax, rates=None, edges=None, small=False):
    for (a, b) in V.PAIRS:
        (x1, y1), (x2, y2) = POS[a], POS[b]
        if rates is not None:
            r = rates[V.PAIRS.index((a, b))]
            diag = (a, b) in ((0, 2), (1, 3))
            ax.plot([x1, x2], [y1, y2], color="#c92a2a" if diag else "#1864ab", lw=1 + 13 * r,
                    alpha=0.9, solid_capstyle="round", zorder=1)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            off = {(0, 1): (-0.035, 0), (2, 3): (0.035, 0), (1, 2): (0, 0.03), (0, 3): (0, -0.03),
                   (0, 2): (0.028, -0.045), (1, 3): (-0.028, -0.045)}[(a, b)]
            ax.text(mx + off[0], my + off[1], f"{r*100:.1f}%", ha="center", va="center", fontsize=11,
                    color="#c92a2a" if diag else "#1864ab", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85), zorder=3)
        else:
            if edges[V.PAIRS.index((a, b))]:
                ax.plot([x1, x2], [y1, y2], color="#1864ab", lw=2.2, zorder=1)
            else:
                ax.plot([x1, x2], [y1, y2], color="#dee2e6", lw=0.8, ls=":", zorder=1)
    for i, (x, y) in POS.items():
        ax.scatter([x], [y], s=110 if small else 900, c="#fff3bf", edgecolors="#c92a2a", linewidths=1.5, zorder=4)
        ax.text(x, y, f"{i}" if small else f"槽{i}", ha="center", va="center", fontsize=7 if small else 11, zorder=5)
    ax.set_xlim(-0.12, 0.17); ax.set_ylim(-0.15, 0.15); ax.set_aspect("equal"); ax.axis("off")


fig = plt.figure(figsize=(20, 14))
gs = fig.add_gridspec(3, 1, height_ratios=[1.35, 0.62, 0.62], hspace=0.38, top=0.91, bottom=0.03, left=0.03, right=0.98)
top = gs[0].subgridspec(1, 3, width_ratios=[1, 1, 1.25], wspace=0.15)
stats = {}
for c, t in enumerate(TASKS):
    G = np.array([r["G"] for r in R[t]])
    rates = G.mean(0)
    conn = np.mean([V.connected(g) for g in G])
    stats[t] = (rates, conn, G)
    ax = fig.add_subplot(top[c])
    draw_graph(ax, rates=rates)
    ax.set_title(f"{V.TASK_ZH[t]}：6 个槽对的可行率（{len(G)} 局）\n边越粗越常可行；红 = 长方形两条对角线", fontsize=12)
    ax.text(0.5, -0.02, f"两条对角线几乎不可行：{rates[1]*100:.1f}% / {rates[4]*100:.1f}%\n"
            f"G 连通（4 个槽经可行交换互达）：{conn*100:.1f}%", transform=ax.transAxes, ha="center", va="top", fontsize=11.5,
            color="#c92a2a")
# 右上：每局 G 的边数分布 + 连通率
ax = fig.add_subplot(top[2])
w = 0.38
for i, t in enumerate(TASKS):
    G = stats[t][2]
    ne = G.sum(1)
    cnt = np.array([(ne == k).mean() for k in range(7)])
    cc = np.array([np.mean([V.connected(g) for g in G[ne == k]]) if (ne == k).any() else 0 for k in range(7)])
    xs = np.arange(7) + (i - 0.5) * w
    col = ["#1864ab", "#e8590c"][i]
    ax.bar(xs, cnt * 100, w, color=col, alpha=0.35, label=f"{t[:1]}{'US' if t[0]=='V' else 'US'} 全部局".replace("VUS", "VUS").replace("BUS", "BUS"))
    ax.bar(xs, cnt * cc * 100, w, color=col, alpha=0.95, label=f"其中 G 连通")
    for x, v in zip(xs, cnt):
        if v > 0.004:
            ax.text(x, v * 100 + 0.8, f"{v*100:.1f}", ha="center", fontsize=8.5)
h, l = ax.get_legend_handles_labels()
ax.legend(h, ["VUS 全部局", "VUS 其中 G 连通", "BUS 全部局", "BUS 其中 G 连通"], fontsize=10, loc="upper left")
ax.set_xlabel("一局 G 里可行的槽对（边）数"); ax.set_ylabel("占局数 %")
ax.set_title(f"G 的边数分布与连通率\nG 连通率：VUS {stats[TASKS[0]][1]*100:.1f}%　BUS {stats[TASKS[1]][1]*100:.1f}%（不连通则 reset 拒绝重抽）", fontsize=12)
ax.set_xticks(range(7)); ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0, 78)

# 下两行：最常见的 G 形态（精确边集）
for r, t in enumerate(TASKS):
    G = stats[t][2]
    ctr = collections.Counter(tuple(g) for g in G.tolist())
    common = ctr.most_common(8)
    sub = gs[1 + r].subgridspec(1, 9, width_ratios=[0.55] + [1] * 8, wspace=0.05)
    lab = fig.add_subplot(sub[0]); lab.axis("off")
    cov = sum(v for _, v in common) / len(G)
    lab.text(0.5, 0.5, f"{t[:1]}US\n最常见的\n8 种 G\n（合计 {cov*100:.1f}%）", ha="center", va="center", fontsize=12,
             fontweight="bold")
    for j, (edges, n) in enumerate(common):
        ax = fig.add_subplot(sub[1 + j])
        draw_graph(ax, edges=edges, small=True)
        ok = V.connected(list(edges))
        ax.set_title(f"{n/len(G)*100:.1f}%　{'连通' if ok else '不连通 → 拒'}", fontsize=11,
                     color="#2b8a3e" if ok else "#c92a2a")
fig.suptitle("图 2　可行槽对图 G：交换在窗口末精确对换位姿 ⇒ 4 个位姿槽固定，一对能不能换只看所占两个槽；reset 时对 6 个槽对各跑一次 check_swap_sweep_prefiltered",
             fontsize=13.5, y=0.985)
V.savefig(fig, "feasible_slot_graph.png")
for t in TASKS:
    print(t, stats[t][0].round(4), stats[t][1])
