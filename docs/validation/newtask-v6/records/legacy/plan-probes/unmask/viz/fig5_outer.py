"""图 5：外环。① 一局 O4 示例（逐窗可行槽对、被选的对、未参与的槽）；② 每窗可行槽对数分布；③ 某窗无搭档的槽在桌面上的位置；
④ V5（O0）对 O4 的未参与率 / 撤销率 / 全员参与率（p3_outer_*_c10/14/18.json）。"""
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
import vizlib as V
from episode import build_episode, outer_window_graph
from replica import _world_yaw_axes, OUTER_HALF
from mclib import ux

TASK, SEED = "VideoUnmaskSwap", 9100000
ep = build_episode(TASK, SEED, 10)
n = len(ep["wins"]); count = 10
Gk = [outer_window_graph(ep, k) for k in range(n)]
xy = np.array([s.p[:2] for s in ep["outer"]])


def run_o(rule, rng):
    occ = list(range(count)); where = list(range(count)); cnt = [0] * count; last = None; log = []
    D = np.linalg.norm(xy[:, None] - xy[None], axis=-1)
    perm = rng.permutation(count).tolist()
    for k in range(n):
        feas = lambda a, b: Gk[k][(min(occ[a], occ[b]), max(occ[a], occ[b]))]
        allf = [(a, b) for a in range(count) for b in range(a + 1, count) if feas(a, b)]
        pair = None
        if rule == "O4":
            cands = [p for p in allf if p != last] or allf
            key = [(max(cnt[a], cnt[b]), cnt[a] + cnt[b]) for a, b in cands]
            best = [p for p, kk in zip(cands, key) if kk == min(key)]
            pair = best[rng.integers(len(best))]
        else:  # O0 = V5 现状：perm 轮转发起者 + 最近邻，不可行顺延
            for j in range(count):
                o = perm[(k + j) % count]; d = D[occ[o]].copy(); d[occ[o]] = 9
                p = where[int(np.argmin(d))]
                if feas(o, p):
                    pair = (min(o, p), max(o, p)); break
        a, b = pair
        log.append(dict(k=k, pair=pair, slots=(occ[a], occ[b]), feas_slots=[p for p, f in Gk[k].items() if f],
                        undo=pair == last))
        cnt[a] += 1; cnt[b] += 1; last = pair
        sa, sb = occ[a], occ[b]; occ[a], occ[b] = sb, sa; where[sa], where[sb] = b, a
    return log, cnt


log4, cnt4 = run_o("O4", np.random.default_rng(SEED))
log0, cnt0 = run_o("O0", np.random.default_rng(SEED))
print("O4 cnt", cnt4, "O0 cnt", cnt0)


def sq(ax, x, y, yaw, **kw):
    A = _world_yaw_axes(yaw)
    pts = np.array([x, y]) + (np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * OUTER_HALF) @ A.T
    ax.add_patch(Polygon(pts, closed=True, **kw))


fig = plt.figure(figsize=(26, 19))
gs = fig.add_gridspec(3, 1, height_ratios=[1.05, 1.0, 0.14], hspace=0.3, top=0.93, bottom=0.02, left=0.03, right=0.99)
top = gs[0].subgridspec(2, 6, width_ratios=[1] * 5 + [1.15], wspace=0.06, hspace=0.18)
used = set()
for k in range(n):
    ax = fig.add_subplot(top[k // 5, k % 5])
    e = log4[k]; w = ep["wins"][k]
    for i, st in enumerate(w.states):
        yaw = ep["lay"]["bins"][0][2]
        ax.scatter([st.p[0]], [st.p[1]], marker="s", s=70, c="#fff3bf", edgecolors="#c92a2a", zorder=2)
    s = ux.path_samples(40)
    pa, pb = ux.lane_center_paths(w.states[w.a].p[:2], w.states[w.b].p[:2], s)
    ax.plot(pa[:, 0], pa[:, 1], color="#c92a2a", lw=1.2); ax.plot(pb[:, 0], pb[:, 1], color="#c92a2a", lw=1.2, ls="--")
    for (a, b) in e["feas_slots"]:
        ax.plot(xy[[a, b], 0], xy[[a, b], 1], color="#74c0fc", lw=1.3, zorder=1)
    sa, sb = e["slots"]
    ax.plot(xy[[sa, sb], 0], xy[[sa, sb], 1], color="#1864ab", lw=4, zorder=3)
    used |= {e["pair"][0], e["pair"][1]}
    deg = np.zeros(count, int)
    for a, b in e["feas_slots"]:
        deg[a] += 1; deg[b] += 1
    for i in range(count):
        ax.scatter([xy[i, 0]], [xy[i, 1]], s=120, c="white" if deg[i] else "#f1f3f5",
                   edgecolors="#1864ab" if deg[i] else "#adb5bd", linestyle="-" if deg[i] else "--", zorder=4)
        ax.text(xy[i, 0], xy[i, 1], str(i), ha="center", va="center", fontsize=7, zorder=5)
    ax.set_xlim(-0.5, 0.5); ax.set_ylim(-0.5, 0.5); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"第 {k+1} 窗：可行 {len(e['feas_slots'])}/45 对；选 槽{sa}↔槽{sb}"
                 + ("（撤销）" if e["undo"] else ""), fontsize=10.5)
axt = fig.add_subplot(top[:, 5]); axt.axis("off")
un4 = [i for i in range(count) if cnt4[i] == 0]; un0 = [i for i in range(count) if cnt0[i] == 0]
axt.text(0.0, 1.0,
         f"【① 一局外环 O4 示例】\nVUS seed={SEED}，n_swaps={n}，外环 10 个\n（内环按 V5 序列；外环槽 = 初始位姿，\n  交换同样精确对换位姿）\n\n"
         "· 浅蓝细线 = 本窗可行的外环槽对\n· 深蓝粗线 = O4 选中的一对\n· 灰色虚圈 = 本窗没有任何可行搭档的槽\n"
         "· 红方块/红线 = 内环容器与本窗内环交换路径\n\n"
         "O4 每窗：候选 = 本窗可行对 − 上一对，\n取两者参与次数（先比较大值再比和）\n最少者，平局均匀抽。\n\n"
         f"本局 O4 参与次数（按对象 0..9）：\n{cnt4}\n未参与 {len(un4)} 个：{un4}\n\n"
         f"同局 V5 现状 O0：\n{cnt0}\n未参与 {len(un0)} 个：{un0}\n\n"
         "可行对集中在少数几个槽上，\n算法再均衡也够不着其余槽。",
         va="top", fontsize=11, linespacing=1.4, bbox=dict(boxstyle="round", fc="#f8f9fa", ec="#ced4da"))

bot = gs[1].subgridspec(1, 4, width_ratios=[1, 1, 1, 1.3], wspace=0.22)
S = {t: json.load(open(V.HERE / f"outer_sample_{t}.json")) for t in ["VideoUnmaskSwap", "ButtonUnmaskSwap"]}
ax = fig.add_subplot(bot[0])
for i, (t, col) in enumerate([("VideoUnmaskSwap", "#1864ab"), ("ButtonUnmaskSwap", "#e8590c")]):
    nf = np.array([w["nfeas"] for r in S[t] for w in r["wins"]])
    zero = np.mean([d == 0 for r in S[t] for w in r["wins"] for d in w["deg"]])
    h = np.bincount(np.clip(nf, 0, 15), minlength=16) / len(nf) * 100
    ax.bar(np.arange(16) + (i - 0.5) * 0.4, h, 0.4, color=col,
           label=f"{t[:1]}US：均值 {nf.mean():.1f} 对；某窗零搭档的槽 {zero*100:.0f}%")
ax.set_xticks(range(16)); ax.set_xticklabels([str(i) for i in range(15)] + ["≥15"])
ax.set_xlabel("每窗 45 个外环槽对里可行的对数"); ax.set_ylabel("占窗口数 %")
ax.set_title(f"② 每窗可行槽对数分布\n（VUS {len(S['VideoUnmaskSwap'])} 局 / BUS {len(S['ButtonUnmaskSwap'])} 局，逐窗重算）", fontsize=12)
ax.legend(fontsize=9.5, loc="upper right"); ax.grid(axis="y", alpha=0.3)

for j, t in enumerate(["VideoUnmaskSwap", "ButtonUnmaskSwap"]):
    ax = fig.add_subplot(bot[1 + j])
    pts = np.array([r["xy"][i] for r in S[t] for i in range(10)])
    zfrac = np.array([np.mean([w["deg"][i] == 0 for w in r["wins"]]) for r in S[t] for i in range(10)])
    hb = ax.hexbin(pts[:, 0], pts[:, 1], C=zfrac, gridsize=16, cmap="Reds", vmin=0, vmax=1, reduce_C_function=np.mean,
                   extent=(-0.47, 0.47, -0.47, 0.47), mincnt=3)
    ax.add_patch(Rectangle((-0.45, -0.45), 0.9, 0.9, fill=False, ls="--", ec="#868e96"))
    ax.add_patch(Rectangle((-0.2675, -0.2675), 0.535, 0.535, fill=False, ls="--", ec="#868e96"))
    ax.scatter([-0.615], [0], s=1, alpha=0)
    ax.set_xlim(-0.5, 0.5); ax.set_ylim(-0.5, 0.5); ax.set_aspect("equal")
    ax.set_xlabel("x（m）")
    ax.set_title(f"③ {t[:1]}US：槽在该位置时「某窗零搭档」的比例\n（颜色 = 该槽在全部窗口中无可行搭档的窗占比）", fontsize=11.5)
    cb = fig.colorbar(hb, ax=ax, fraction=0.046, pad=0.02); cb.set_label("零搭档窗占比")
    ax.text(0.02, 0.02, "右侧（x 大，靠画面边缘）→ vis 拒\n环带内侧贴近内环 → inner_clear 拒" + ("\n按钮一侧 → btn 拒" if j else ""),
            transform=ax.transAxes, fontsize=9, va="bottom", bbox=dict(fc="white", ec="none", alpha=0.8))

# ④ O0 vs O4
ax = fig.add_subplot(bot[3])
rows = []
for t in ["VideoUnmaskSwap", "ButtonUnmaskSwap"]:
    for c in (10, 14, 18):
        R = [r for r in json.load(open(f"p3_outer_{t}_c{c}.json")) if r["status"] == "ok"]
        for rule in ("O0", "O4"):
            unv = []; undo = []; full = []
            for r in R:
                s = r[rule]
                if s is None: continue
                cc = np.zeros(c)
                for k, (a, b) in enumerate(s):
                    cc[a] += 1; cc[b] += 1
                    if k: undo.append(tuple(s[k - 1]) == (a, b))
                unv.append(np.mean(cc == 0)); full.append((cc > 0).all())
            rows.append((t, c, rule, np.mean(unv) * 100, np.mean(undo) * 100, np.mean(full) * 100))
labels = [f"{t[:1]}US c{c}" for t, c, r, *_ in rows if r == "O0"]
x = np.arange(len(labels)); ww = 0.2
o0 = [r for r in rows if r[2] == "O0"]; o4 = [r for r in rows if r[2] == "O4"]
for off, data, col, lab in [(-1.5, o0, "#adb5bd", "V5 现状 O0 未参与率"), (-0.5, o4, "#1864ab", "O4 未参与率"),
                            (0.5, o0, "#ffa8a8", "V5 现状 O0 撤销率"), (1.5, o4, "#c92a2a", "O4 撤销率")]:
    vals = [d[3] if "未参与" in lab else d[4] for d in data]
    ax.bar(x + off * ww, vals, ww, color=col, label=lab)
    for xi, v in zip(x + off * ww, vals):
        ax.text(xi, v + 1, f"{v:.0f}", ha="center", fontsize=8)
for xi, d in zip(x, o4):
    ax.text(xi, 88, f"全员参与\n{d[5]:.1f}%", ha="center", fontsize=8.5, color="#2b8a3e")
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
ax.set_ylim(0, 97); ax.set_ylabel("%")
ax.set_title("④ 未参与对象占比 / 撤销率：V5 现状 O0 对 O4\n（c10 各 10000 局，c14/c18 各 1000 局；绿字 = O4 全员参与的局）", fontsize=12)
ax.legend(fontsize=9.5, loc="upper left", ncol=2, bbox_to_anchor=(0.0, 0.83)); ax.grid(axis="y", alpha=0.3)
for t, c, r, u, d, f in rows:
    print(t, c, r, f"unvisited={u:.1f} undo={d:.1f} full={f:.2f}")

axc = fig.add_subplot(gs[2]); axc.axis("off")
axc.text(0.5, 0.5, "结论：外环局内均匀在 V5 路径约束下做不到（任何算法全员参与 ≤4.3%：VUS / BUS 每窗 45 对只有约 5.6 / 3.6 对可行，逐窗约 31% / 45% 的槽没有任何可行搭档）。"
         "\n可选：(a) 接受跨局均匀 + O4 尽量均衡（放置后序号 randperm 重排，推荐）；(b) 放宽「路径全程可见」（零搭档槽 31.7%→15.0%，交换会出画）；"
         "(c) 外环改沿环切向成对放置（改布局）。",
         ha="center", va="center", fontsize=13, color="#c92a2a", bbox=dict(boxstyle="round", fc="#fff5f5", ec="#ffa8a8"))
fig.suptitle("图 5　外环（10 个干扰容器随内环同步交换）：可行槽对极稀，局内均匀做不到，能做到的是跨局均匀 + O4 均衡贪心", fontsize=16, y=0.975)
V.savefig(fig, "outer_ring.png")
