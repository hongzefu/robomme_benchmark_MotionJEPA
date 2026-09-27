"""图 3：S5 算法一局示例时间线（同一 G 下对比 S1）。数据：p2_inner_VideoUnmaskSwap.json 里一局真实布局的 G。"""
import json
import numpy as np
import matplotlib.pyplot as plt
import vizlib as V

POS = {0: (-0.05, -0.1), 1: (-0.05, 0.1), 2: (0.1, 0.1), 3: (0.1, -0.1)}
TASK = "VideoUnmaskSwap"; SEED = 9100039; S5_RNG = 0; S1_RNG = None
R = {r["seed"]: r for r in json.load(open(f"p2_inner_{TASK}.json"))}
rec = R[SEED]; G = V.g_dict(rec["G"]); n = rec["n"]

# S5：逐趟记录，便于画出被「整条重排」丢弃的那一趟
rng = np.random.default_rng(S5_RNG)
attempts = []
for t in range(20):
    lg = V.run_s5_once(G, n, rng); attempts.append(lg)
    if V.spread(lg) <= 1:
        break
# S1：同一 G，找一条典型的「有撤销、失衡」的序列（挑选只为示意，统计见图 4）
for s in range(200):
    l1 = V.run_s1(G, n, np.random.default_rng(1000 + s))
    if l1 and V.spread(l1) >= 4 and sum(x["undo"] for x in l1) >= 3:
        S1_RNG = 1000 + s; break
print("G", rec["G"], "n", n, "S5 趟数", len(attempts), [V.spread(a) for a in attempts], "S1 rng", S1_RNG, V.spread(l1))


def ladder(ax, log, kind, title):
    for o in range(V.N):
        ax.axhline(o, color=V.OBJ_COLORS[o], lw=1, alpha=0.35, zorder=0)
    for e in log:
        k = e["k"] + 1; a, b = e["pair"]
        col = "#c92a2a" if e["undo"] else ("#2b8a3e" if kind == "S5" else "#495057")
        ax.plot([k, k], [a, b], color=col, lw=3, zorder=2)
        ax.scatter([k, k], [a, b], s=90, c=[V.OBJ_COLORS[a], V.OBJ_COLORS[b]], edgecolors="k", zorder=3)
        sa, sb = e["occ"][a], e["occ"][b]
        ax.text(k, -0.3, f"槽{min(sa,sb)}↔{max(sa,sb)}", ha="center", va="bottom", fontsize=8.5, color="#495057")
        if kind == "S5":
            nf = len(e["feas"]); nc = len(e["cand"]); nb = len(e["best"])
            lines = [f"可行{nf}", f"−上一对→{nc}", f"最少者{nb}"]
            if nb > 1:
                lines.append(f"平局抽1/{nb}")
        else:
            lines = [f"可行{len(e['feas'])}", "均匀抽"]
        if e["undo"]:
            lines.append("撤销!")
        ax.text(k, 3.35, "\n".join(lines), ha="center", va="top", fontsize=8.5,
                color="#c92a2a" if e["undo"] else "#343a40", linespacing=1.15)
    ax.set_yticks(range(V.N)); ax.set_yticklabels([f"bin_{o}" for o in range(V.N)])
    ax.set_ylim(5.9, -0.9); ax.set_xlim(0.4, n + 0.6); ax.set_xticks(range(1, n + 1))
    ax.set_title(title, fontsize=12, loc="left")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def counts(ax, log, label_end=True):
    C = np.array([[0] * V.N] + [e["cnt_after"] for e in log])
    ks = np.arange(0, n + 1)
    for o in range(V.N):
        ax.step(ks, C[:, o] + (o - 1.5) * 0.06, where="post", color=V.OBJ_COLORS[o], lw=2, label=f"bin_{o}")
    for k in range(1, n + 1):
        sp = C[k].max() - C[k].min()
        ax.text(k, C.max() + 0.9, f"{sp}", ha="center", fontsize=9, color="#c92a2a" if sp > 1 else "#2b8a3e",
                fontweight="bold")
    ax.text(0.2, C.max() + 0.9, "极差", ha="center", fontsize=9)
    ax.set_xlim(-0.2, n + 0.6); ax.set_ylim(-0.3, C.max() + 1.6)
    ax.set_xticks(range(0, n + 1)); ax.set_ylabel("累计参与次数"); ax.grid(alpha=0.25)
    ax.set_xlabel("交换窗口序号")
    fin = C[-1]
    ax.text(n + 0.55, 0.1, f"终局 {fin.tolist()}  极差 {fin.max()-fin.min()}", ha="right", va="bottom", fontsize=10.5,
            bbox=dict(fc="white", ec="#adb5bd"))


fig = plt.figure(figsize=(23, 21))
gs = fig.add_gridspec(6, 2, width_ratios=[3.2, 1], height_ratios=[1.25, 0.8, 1.25, 0.8, 1.25, 0.8],
                      hspace=0.55, wspace=0.08, top=0.94, bottom=0.03, left=0.05, right=0.98)
u1 = sum(e["undo"] for e in l1)
ladder(fig.add_subplot(gs[0, 0]), l1, "S1", f"① S1（可行对里均匀抽，不看参与次数）：撤销 {u1} 次，终局极差 {V.spread(l1)}")
counts(fig.add_subplot(gs[1, 0]), l1)
a0 = attempts[0]
ladder(fig.add_subplot(gs[2, 0]), a0, "S5",
       f"② S5 第 1 趟：每窗都选参与次数最少者，但终局极差 {V.spread(a0)} > 1 ⇒ 整条丢弃重排（最多 20 趟）")
counts(fig.add_subplot(gs[3, 0]), a0)
af = attempts[-1]
ladder(fig.add_subplot(gs[4, 0]), af, "S5",
       f"③ S5 第 {len(attempts)} 趟（被采用）：撤销 0 次，终局极差 {V.spread(af)}")
counts(fig.add_subplot(gs[5, 0]), af)

# 右栏：本局 G + 规则说明
axg = fig.add_subplot(gs[0:2, 1])
for (a, b) in V.PAIRS:
    (x1, y1), (x2, y2) = POS[a], POS[b]
    ok = G[(a, b)]
    axg.plot([x1, x2], [y1, y2], color="#1864ab" if ok else "#dee2e6", lw=4 if ok else 1, ls="-" if ok else ":")
for i, (x, y) in POS.items():
    axg.scatter([x], [y], s=900, c="#fff3bf", edgecolors="#c92a2a", zorder=3)
    axg.text(x, y, f"槽{i}", ha="center", va="center", fontsize=11, zorder=4)
axg.set_xlim(-0.12, 0.17); axg.set_ylim(-0.16, 0.15); axg.set_aspect("equal"); axg.axis("off")
axg.set_title(f"本局 G（{TASK[:1]}US seed={SEED}，n_swaps={n}）\n可行边：槽1–2、槽2–3、槽0–3（一条链）\n"
              f"初始 bin_i 在槽 i", fontsize=11.5)
axt = fig.add_subplot(gs[2:6, 1]); axt.axis("off")
axt.text(0.0, 1.0,
         "【S5 每窗的判定】\n"
         "1. 可行 = G 里的边（按两者此刻\n    所占的槽查表，零碰撞计算）\n"
         "2. 候选 = 可行 − 上一对\n    （禁止立即撤销；别无选择才允许）\n"
         "3. 取「参与次数最少者」：先比两者\n    参与次数的较大值，再比和\n"
         "4. 平局 → 均匀抽（实施时用主流追加的\n    torch.rand(n_swaps) 打破）\n"
         "5. 整条跑完极差 > 1 → 整条重排，\n    ≤ 20 趟；仍不满足则接受极差 2\n\n"
         "【图例】\n"
         "· 竖线 = 该窗交换的两个对象；\n  上方「槽a↔b」= 它们此刻所占的槽\n"
         "· 红竖线 / 红字「撤销!」= 与上一窗\n  是同一对（刚换完又换回，观众白看）\n"
         "· 下方小图：各对象累计参与次数；\n  顶部数字 = 当前极差，红 = 大于 1\n\n"
         "【看点】\n"
         f"· S1：{u1} 次撤销，bin 参与次数\n  终局 {l1[-1]['cnt_after']}，极差 {V.spread(l1)}\n"
         f"· S5：0 次撤销，终局\n  {af[-1]['cnt_after']}，极差 {V.spread(af)}\n"
         "· 该 G 是一条链（槽1–2–3–0），\n  端点槽上的对象天然少参与，\n  所以第 1 趟可能失衡、需要重排",
         va="top", ha="left", fontsize=11.5, linespacing=1.45,
         bbox=dict(boxstyle="round", fc="#f8f9fa", ec="#ced4da"))
fig.suptitle("图 3　S5「计数均衡贪心」一局示例时间线：同一 G 下与 S1（可行对均匀抽）对比", fontsize=16, y=0.975)
V.savefig(fig, "s5_episode_timeline.png")
