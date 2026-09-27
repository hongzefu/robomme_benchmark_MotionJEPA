"""图 1：内环与外环分别长什么样（VUS / BUS 各一行；外环干扰数 10（V5 xhard）/ 14 / 18 各一列）。"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle, Circle
import vizlib as V
from episode import build_episode, outer_window_graph
from mclib import CH, ux
from replica import _world_yaw_axes, OUTER_HALF

SEEDS = {"VideoUnmaskSwap": None, "ButtonUnmaskSwap": None}
COUNTS = [10, 14, 18]
CUBE_RGB = {"yellow": "#f2c200", "cyan": "#00b7c7", "magenta": "#c2188b"}


def find_seed(task, base):
    for s in range(base, base + 400):
        eps = [build_episode(task, s, c) for c in COUNTS]
        if all(e is not None for e in eps):
            return s, eps
    raise RuntimeError("找不到三档都能放下的种子")


def square(ax, x, y, yaw, half, **kw):
    A = _world_yaw_axes(yaw)
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * half
    pts = np.array([x, y]) + corners @ A.T
    ax.add_patch(Polygon(pts, closed=True, **kw))


def visible_mask():
    xs = np.linspace(-0.75, 0.55, 261); ys = np.linspace(-0.6, 0.6, 241)
    X, Y = np.meshgrid(xs, ys)
    ok = ux.bins_visible_many(np.stack([X.ravel(), Y.ravel()], 1), CH).reshape(X.shape)
    return X, Y, ok


VIS = visible_mask()


def draw_panel(ax, ep, show_paths):
    task = ep["task"]; lay = ep["lay"]; L = ep["layout"]
    X, Y, ok = VIS
    ax.contourf(X, Y, ok.astype(float), levels=[0.5, 1.5], colors=["#eef6ee"], zorder=0)
    ax.contour(X, Y, ok.astype(float), levels=[0.5], colors=["#2b8a3e"], linewidths=1.2, zorder=1)
    # V4 保守楔形：x ≤ VISIBLE_X_MAX，|y| ≤ 0.49 − 0.45·x（容器中心 + 外接圆半径）
    xw = np.linspace(-0.75, ux.VISIBLE_X_MAX, 50)
    yw = ux.VISIBLE_Y_AT_X0 - ux.VISIBLE_Y_SLOPE * xw
    wedge = np.concatenate([np.stack([xw, yw], 1), np.stack([xw[::-1], -yw[::-1]], 1)])
    ax.add_patch(Polygon(wedge, closed=True, fill=False, ls=":", lw=1.2, ec="#5c940d", zorder=1))
    # 外环环带 max(|x|,|y|) ∈ [0.2675, 0.45]
    lo, hi = ep["layout"] and (0.2675, 0.45)
    ax.add_patch(Rectangle((-hi, -hi), 2 * hi, 2 * hi, fill=False, ls="--", lw=1.0, ec="#868e96", zorder=1))
    ax.add_patch(Rectangle((-lo, -lo), 2 * lo, 2 * lo, fill=False, ls="--", lw=1.0, ec="#868e96", zorder=1))
    # 机器人基座
    ax.add_patch(Circle((-0.615, 0), 0.06, fc="#495057", ec="k", zorder=3))
    ax.text(-0.615, -0.1, "机器人基座\n(-0.615, 0)", ha="center", va="top", fontsize=8)
    # 按钮（BUS）
    for bx, by in lay["buttons"]:
        ax.add_patch(Rectangle((bx - 0.05625, by - 0.05625), 0.1125, 0.1125, fc="#ffd8a8", ec="#e8590c", zorder=3))
        ax.add_patch(Circle((bx, by), 0.122, fill=False, ls="--", ec="#e8590c", lw=0.9, zorder=2))
        ax.text(bx, by, "按钮", ha="center", va="center", fontsize=7.5, color="#d9480f", zorder=4)
    if lay["buttons"]:
        bx, by = lay["buttons"][1]
        pass
    # 内环：4 个槽（= 4 个容器的初始位姿；一局内交换只在这 4 个位姿之间轮换）
    sel = set(lay["selected"])
    for i, (x, y, yaw) in enumerate(lay["bins"]):
        square(ax, x, y, yaw, OUTER_HALF, fc="#fff3bf" if i in sel else "white", ec="#c92a2a", lw=1.8, zorder=4)
        if i in sel:
            square(ax, x, y, yaw, 0.012, fc=V.OBJ_COLORS[i], ec="k", lw=0.5, zorder=5)
    # 槽号放在内环外侧，避免压住容器
    c = np.mean([[b[0], b[1]] for b in lay["bins"]], axis=0)
    for i, (x, y, yaw) in enumerate(lay["bins"]):
        d = np.array([x, y]) - c; d = d / (np.linalg.norm(d) + 1e-9)
        tag = f"槽{i}" + ("" if i in sel else "(空)")
        ax.text(x + d[0] * 0.085, y + d[1] * 0.085, tag, ha="center", va="center", fontsize=8.5, color="#c92a2a",
                fontweight="bold", zorder=6)
    # 外环干扰容器
    cube_of = {b: col for b, col in zip(L.cube_bins, L.cube_colors)}
    g0 = outer_window_graph(ep, 0)
    deg = np.zeros(ep["count"], int)
    for (a, b), f in g0.items():
        if f: deg[a] += 1; deg[b] += 1
    for i, (x, y, yaw) in enumerate(L.bins):
        ec = "#1864ab" if deg[i] > 0 else "#adb5bd"
        square(ax, x, y, yaw, OUTER_HALF, fc="white", ec=ec, lw=1.5, ls="-" if deg[i] else "--", zorder=4)
        if i in cube_of:
            square(ax, x, y, yaw, 0.012, fc=CUBE_RGB.get(cube_of[i], "#999"), ec="k", lw=0.4, zorder=5)
        ax.text(x, y - 0.048, str(i), ha="center", va="top", fontsize=7, color=ec, zorder=6)
    # 第 0 窗的交换路径
    if show_paths:
        w = ep["wins"][0]
        s = ux.path_samples(60)
        pa, pb = ux.lane_center_paths(w.states[w.a].p[:2], w.states[w.b].p[:2], s)
        ax.plot(pa[:, 0], pa[:, 1], color="#c92a2a", lw=1.6, zorder=7)
        ax.plot(pb[:, 0], pb[:, 1], color="#c92a2a", lw=1.6, ls="--", zorder=7)
        feas = [p for p, f in g0.items() if f]
        if feas:
            xy = np.array([st.p[:2] for st in ep["outer"]])
            o, q = min(feas, key=lambda p: np.linalg.norm(xy[p[0]] - xy[p[1]]))
            po, pq = ux.lane_center_paths(xy[o], xy[q], s)
            ax.plot(po[:, 0], po[:, 1], color="#1864ab", lw=1.6, zorder=7)
            ax.plot(pq[:, 0], pq[:, 1], color="#1864ab", lw=1.6, ls="--", zorder=7)
    n_zero = int((deg == 0).sum())
    ax.set_xlim(-0.72, 0.55); ax.set_ylim(-0.58, 0.58); ax.set_aspect("equal")
    ax.set_xlabel("x（m）"); ax.set_ylabel("y（m）")
    ax.grid(alpha=0.15)
    return n_zero, int(sum(g0.values())), len(g0)


def main():
    fig = plt.figure(figsize=(25, 13))
    gs = fig.add_gridspec(2, 4, width_ratios=[1, 1, 1, 0.95], wspace=0.15, hspace=0.28, top=0.89, bottom=0.05, left=0.04, right=0.99)
    info = {}
    for r, (task, base) in enumerate([("VideoUnmaskSwap", 9_100_000), ("ButtonUnmaskSwap", 9_300_000)]):
        seed, eps = find_seed(task, base)
        for c, ep in enumerate(eps):
            ax = fig.add_subplot(gs[r, c])
            nz, nf, npairs = draw_panel(ax, ep, show_paths=(c == 0))
            tag = "V5 xhard 现状" if ep["count"] == 10 else "干扰数加大，V6 候选"
            ax.set_title(f"{V.TASK_ZH[task].split('（')[0]} seed={seed}｜外环 {ep['count']} 个（{tag}）\n"
                         f"第 0 窗：{npairs} 个外环槽对中可行 {nf} 对\n无任何可行搭档的槽 {nz}/{ep['count']} 个", fontsize=10.5)
            info[(task, ep["count"])] = (nz, nf, npairs)
        print(task, seed, "n_swaps", eps[0]["lay"]["n_swaps"])
    # 图例
    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], marker="s", ls="", mfc="#fff3bf", mec="#c92a2a", ms=10, label="内环容器（4 个位姿槽）；小方块 = 藏 cube；槽3(空)=bin_3"),
        Line2D([], [], marker="s", ls="", mfc="white", mec="#1864ab", ms=10, label="外环干扰容器：第 0 窗至少有 1 个可行搭档"),
        Line2D([], [], marker="s", ls="", mfc="white", mec="#adb5bd", ms=10, label="外环干扰容器：第 0 窗没有任何可行搭档"),
        Line2D([], [], color="#2b8a3e", lw=1.2, label="容器整体可见的中心区域（V5 精确 8 角点判据）"),
        Line2D([], [], color="#5c940d", lw=1.2, ls=":", label="V4 保守楔形 x≤0.43，|y|≤0.49−0.45x"),
        Line2D([], [], color="#868e96", lw=1.0, ls="--", label="外环环带 max(|x|,|y|)∈[0.2675, 0.45]"),
        Line2D([], [], color="#c92a2a", lw=1.6, label="内环第 0 窗交换路径（双车道 lane 0.07）"),
        Line2D([], [], marker="s", ls="", mfc="#ffd8a8", mec="#e8590c", ms=10, label="BUS 按钮；橙色虚圈 0.122 m = 外环路径禁入"),
        Line2D([], [], color="#1864ab", lw=1.6, label="外环第 0 窗一对可行交换的路径"),
    ]
    tax = fig.add_subplot(gs[:, 3]); tax.axis("off")
    tax.legend(handles=handles, loc="upper left", fontsize=9.5, frameon=True, title="图例", title_fontsize=10)
    text = (
        "【内环】4 个容器 spawned_bins（bin_0..3）\n"
        "· VUS：4 个锚点（长方形 region4 随机旋转）各抽一个位姿；\n"
        "  BUS：长方形锚点在两个按钮右侧，y 方向各自错位。\n"
        "· bin_0..2 各藏 1 个 cube；xhard 下 bin_3 恒为空\n"
        "  （selected = randperm(3) 只覆盖 bin_0..2）。\n"
        "· 每窗（33 步）一对内环容器沿双车道路径对换，\n"
        "  窗口末【精确对换位姿】⇒ 一局里 4 个位姿槽不变，\n"
        "  容器只是在 4 个槽之间轮换；某对能否交换只取决于\n"
        "  它们此刻占的两个槽 ⇒ 可行槽对图 G（6 条边）。\n"
        "· V5：发起者 swap_indices[k%3]，搭档 = XY 最近邻；\n"
        "  V6：S5 均衡贪心（见图 3、图 6）。\n\n"
        "【外环】干扰容器 distractor_bins（10 个，V5 xhard）\n"
        "· 放在环带 [0.2675, 0.45] 内、相机可见处，\n"
        "  5 个装黄/青/品红 cube；独立随机流，不进 spawned_bins。\n"
        "· 每个内环窗口【同步】做一次外环交换，同样精确对换位姿\n"
        "  ⇒ 外环也是 10 个固定槽，但可行性随窗变化\n"
        "  （内环此窗在换哪一对会挡路）。\n"
        "· 一对外环可行须依次过 4 道判定：\n"
        "  vis 两条路径全程可见 → btn 离按钮中心 ≥0.122（BUS）\n"
        "  → inner_clear 离内环外接圆净距 ≥0.04\n"
        "  → exact 与内环对联合连续碰撞证明（外扩 5 mm）。\n"
        "· 结果：第 0 窗可行对很少，大量槽没有任何搭档\n"
        "  （灰色虚框）；干扰数 14/18 时更稀（见图 5）。"
    )
    tax.text(0.0, 0.52, text, va="top", ha="left", fontsize=10.2, linespacing=1.45,
             bbox=dict(boxstyle="round", fc="#f8f9fa", ec="#ced4da"))
    fig.suptitle("图 1　内环与外环分别长什么样（俯视图，按 V5 xhard 规则真实抽样；外环判定直接调仓库 evaluate_outer_candidate）",
                 fontsize=15, y=0.975)
    V.savefig(fig, "layout_inner_outer.png")
    print(info)


if __name__ == "__main__":
    main()
