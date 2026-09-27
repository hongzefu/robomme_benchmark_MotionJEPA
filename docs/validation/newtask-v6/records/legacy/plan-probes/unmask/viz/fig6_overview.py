"""图 6：Unmask 交换对象均匀化方案总览（reset 阶段 / 每窗选取，内环与外环两条线并列）。"""
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import vizlib as V

fig, ax = plt.subplots(figsize=(26, 15))
fig.subplots_adjust(top=0.93, bottom=0.01, left=0.01, right=0.99)
ax.set_xlim(0, 100); ax.set_ylim(0, 57); ax.axis("off")
BW, BH = 14.5, 5.6


def box(x, y, text, fc, ec, w=BW, h=BH, fs=12.3):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.2", fc=fc, ec=ec, lw=1.6, zorder=2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, linespacing=1.3, zorder=3)


def arrow(p1, p2, col="#495057", rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=18, color=col, lw=1.7, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", zorder=1))


def label(x, y, t, col="#495057", fs=11.5):
    ax.text(x, y, t, ha="center", va="center", fontsize=fs, color=col, zorder=4,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))


def poly(pts, col, t=None, tpos=None):
    xs, ys = zip(*pts)
    ax.plot(xs[:-1], ys[:-1], color=col, lw=1.7, ls="--", zorder=1)
    arrow(pts[-2], pts[-1], col=col, ls="--")
    if t:
        label(*tpos, t, col=col)


for x0, x1, lab in [(0.5, 49.5, "reset 阶段（每局一次）"), (50.5, 99.5, "每个交换窗口的选取（reset 内预规划整段，运行时照读）")]:
    ax.add_patch(FancyBboxPatch((x0, 0.6), x1 - x0, 54.6, boxstyle="round,pad=0.2", fc="#f8f9fa", ec="#ced4da", lw=1))
    ax.text((x0 + x1) / 2, 54.4, lab, ha="center", va="center", fontsize=14, fontweight="bold")
ax.plot([0.8, 99.2], [29.0, 29.0], color="#adb5bd", ls="--", lw=1)
ax.text(1.2, 41.5, "内\n环", fontsize=16, fontweight="bold", color="#c92a2a", va="center")
ax.text(1.2, 14.0, "外\n环", fontsize=16, fontweight="bold", color="#1864ab", va="center")

C = [9.0, 25.0, 41.0]          # reset 区三列
XS = [59.0, 75.0, 91.0]        # 每窗区三列


def lane(top, fc, ec, reset_txt, win_txt, gate_txt, gate_no, result, res_col):
    r1, r2, r3 = top, top - 8.0, top - 15.5
    box(C[0], r1, reset_txt[0], fc, ec); box(C[1], r1, reset_txt[1], fc, ec); box(C[2], r1, reset_txt[2], fc, ec)
    box(C[2], r2, gate_txt, "#fff9db", "#f08c00")
    box(C[2], r3, reset_txt[3], fc, ec)
    arrow((C[0] + BW / 2 + 0.3, r1), (C[1] - BW / 2 - 0.3, r1)); arrow((C[1] + BW / 2 + 0.3, r1), (C[2] - BW / 2 - 0.3, r1))
    arrow((C[2], r1 - BH / 2 - 0.3), (C[2], r2 + BH / 2 + 0.3))
    arrow((C[2], r2 - BH / 2 - 0.3), (C[2], r3 + BH / 2 + 0.3), col="#2b8a3e"); label(C[2] + 3.2, (r2 + r3) / 2, gate_no[1], "#2b8a3e")
    poly([(C[2] - BW / 2 - 0.3, r2), (C[0], r2), (C[0], r1 - BH / 2 - 0.3)], "#f08c00", gate_no[0], ((C[0] + C[1]) / 2 + 2, r2))
    # 每窗
    box(XS[0], r1, win_txt[0], fc, ec); box(XS[1], r1, win_txt[1], fc, ec); box(XS[2], r1, win_txt[2], fc, ec)
    box(XS[2], r2 - 1.0, win_txt[3][0], win_txt[3][1], win_txt[3][2])
    box((XS[0] + XS[1]) / 2 - 1, r2 - 1.0, win_txt[4], "#f1f3f5", "#495057", w=27)
    arrow((C[2] + BW / 2 + 0.3, r3), (XS[0] - BW / 2 - 0.3, r1 - 1.5), col="#2b8a3e")
    arrow((XS[0] + BW / 2 + 0.3, r1), (XS[1] - BW / 2 - 0.3, r1)); arrow((XS[1] + BW / 2 + 0.3, r1), (XS[2] - BW / 2 - 0.3, r1))
    arrow((XS[2] - 3, r1 + BH / 2 + 0.3), (XS[0] + 3, r1 + BH / 2 + 0.3), col="#868e96", rad=0.12)
    label((XS[0] + XS[2]) / 2, r1 + BH / 2 + 1.5, win_txt[5], "#868e96")
    arrow((XS[2], r1 - BH / 2 - 0.3), (XS[2], r2 - 1.0 + BH / 2 + 0.3)); label(XS[2] + 4.2, (r1 + r2 - 1) / 2, "k = n_swaps")
    arrow((XS[2] - BW / 2 - 0.3, r2 - 1.0), ((XS[0] + XS[1]) / 2 - 1 + 13.5 + 0.3, r2 - 1.0), col=win_txt[6])
    ax.text(75, r3 - 0.5, result, ha="center", va="center", fontsize=11.5, color=res_col, fontweight="bold")


lane(48.5, "#fff5f5", "#c92a2a",
     ["① 抽内环布局\n4 个锚点各一个位姿槽\n（xhard 藏 cube 改\nrandperm(4)[:pick]，M5）",
      "② 6 个槽对各做一次精确判定\ncheck_swap_sweep_prefiltered\n（交换精确对换位姿 ⇒\n4 个槽一局不变）",
      "③ 可行槽对图 G\n对角线可行 VUS 6.6% / BUS 9.0%\n其余 4 条边 36%～99%",
      "⑤ 预规划整段序列\n主流追加一次 torch.rand(n_swaps)\n作平局打破"],
     ["⑥ 可行候选 =\nG 的边（按两者此刻所占槽查表）\n− 上一对（禁止立即撤销，\n别无选择才允许）",
      "⑦ 参与次数最少者优先\n先比两者参与次数的较大值\n再比两者之和",
      "⑧ 平局 → 均匀抽\n（用⑤的 torch.rand）\n交换、计数 +1",
      ("⑨ 整条跑完：极差 > 1？\n是 → 整条重排（≤20 趟）\n仍不满足 → 接受极差 2", "#fff9db", "#f08c00"),
      "⑩ 运行时：锁定循环里的搭档分支改读预规划\n（仿 VR _xhard_planned_partner），\n仍做 joint_sweep_from_actual 复核",
      "下一窗（k < n_swaps），G 不变", "#2b8a3e"],
     "④ G 连通？\nVUS 95.4%　BUS 66.5%", ("否：SceneGenerationError 重抽", "是"),
     "内环（10000 局）：边际卡方 p = 0.98 / 0.996；重排 + G 连通后局内极差 ≤1 的局 100% / 99.9%，撤销 0（VUS / BUS）",
     "#c92a2a")
lane(21.0, "#e7f5ff", "#1864ab",
     ["① 放置 10 个干扰容器\n环带 [0.2675, 0.45]、全可见\n独立流 distractor_generator\n（守卫改为覆盖 G 全部可行槽对）",
      "② 放置后追加一次\nrandperm(count) 重排序号\n（消除约 ±4% 的序号偏差）",
      "③ 每窗 45 个槽对逐一判定\nevaluate_outer_candidate：\nvis → btn → inner_clear → exact\n⇒ 每窗一张 G_k（随内环对变）",
      "⑤ 按窗顺序规划外环对\n（每窗恰一次，与内环同步）"],
     ["⑥ 可行候选 =\nG_k 的边（第 k 窗，\n按此刻所占槽查表）\n− 上一对（禁止立即撤销）",
      "⑦ 参与次数最少者优先\n（O4 均衡贪心，\n与内环同口径）",
      "⑧ 平局 → 均匀抽\n运行时 run_outer_swaps\n与本窗内环对同步交换",
      ("⑨ 不做「极差 > 1 重排」\n局内均匀做不到：\n全员参与 ≤ 4.3%", "#ffe3e3", "#c92a2a"),
      "⑩ 验收只报告：逐局未参与数、撤销数\nOUTER_SWAP_BALANCE=REPORT\n目标：未参与 VUS ≤30% / BUS ≤45%",
      "下一窗：换成 G_{k+1}", "#495057"],
     "④ 某窗 G_k 为空？\n每窗平均可行 VUS 5.6 / BUS 3.6 对", ("是：整段重抽（≤16 次）", "否"),
     "外环（10000 局）：O4 未参与 28% / 43%（V5 现状 40% / 54%），撤销 0.5% / 6.7%（V5 42% / 56%）；只保证跨局均匀",
     "#1864ab")
fig.suptitle("图 6　Unmask 交换对象均匀化方案总览（V6 计划 M6(a)：内环 S5 + G 连通；M7(a)：外环 O4 + 序号重排）", fontsize=17, y=0.975)
V.savefig(fig, "swap_scheme_overview.png")
