"""图 4：S1 / S1n / S5 局内均衡对比（p2_inner_*.json 的逐局 G 上重放；S1/S1n 直接用 JSON 里存的序列）。"""
import json
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import chisquare
import vizlib as V

TASKS = ["VideoUnmaskSwap", "ButtonUnmaskSwap"]
RULES = [("S1", "S1 可行对均匀抽", V.C_S1), ("S1n", "S1n 均匀抽+禁撤销", V.C_S1N),
         ("S5a", "S5 单趟（无重排）", "#8ce99a"), ("S5", "S5 +整条重排≤20", V.C_S5),
         ("S5G", "S5 +重排 +G 连通", V.C_S5G)]


def stats_of(seqs, n_total):
    part = np.zeros(V.N); spreads = []; undo = []
    for s in seqs:
        c = np.zeros(V.N)
        for k, (a, b) in enumerate(s):
            c[a] += 1; c[b] += 1
            if k: undo.append(tuple(s[k - 1]) == (a, b))
        part += c; spreads.append(int(c.max() - c.min()))
    return dict(freq=part / part.sum(), p=chisquare(part).pvalue, spreads=np.array(spreads), undo=np.mean(undo),
                ok=len(seqs) / n_total, n=len(seqs))


RES = {}
for t in TASKS:
    R = json.load(open(f"p2_inner_{t}.json"))
    out = {}
    out["S1"] = stats_of([r["S1"] for r in R if r["S1"] is not None], len(R))
    out["S1n"] = stats_of([r["S1n"] for r in R if r["S1n"] is not None], len(R))
    s5a, s5, s5g, rer = [], [], [], []
    for r in R:
        G = V.g_dict(r["G"])
        la = V.run_s5_once(G, r["n"], np.random.default_rng(r["seed"] + 17))
        if la is not None:
            s5a.append([e["pair"] for e in la])
        lg, tries, _ = V.run_s5(G, r["n"], np.random.default_rng(r["seed"] + 23))
        if lg is not None:
            s5.append([e["pair"] for e in lg]); rer.append(tries)
            if V.connected(r["G"]):
                s5g.append([e["pair"] for e in lg])
    out["S5a"] = stats_of(s5a, len(R)); out["S5"] = stats_of(s5, len(R))
    ng = sum(V.connected(r["G"]) for r in R)
    out["S5G"] = stats_of(s5g, len(R)); out["S5G"]["conn"] = ng / len(R)
    out["S5"]["tries_mean"] = float(np.mean(rer)); out["S5"]["reroll_frac"] = float(np.mean(np.array(rer) > 1))
    RES[t] = out
    for k, v in out.items():
        sp = v["spreads"]
        print(t, k, f"ok={v['ok']:.4f} p={v['p']:.3f} freq={v['freq'].round(4).tolist()} undo={v['undo']:.4f} "
              f"mean_spread={sp.mean():.2f} le1={np.mean(sp<=1):.4f} le2={np.mean(sp<=2):.4f}",
              {kk: vv for kk, vv in v.items() if kk in ("tries_mean", "reroll_frac", "conn")})

fig = plt.figure(figsize=(24, 14.5))
gs = fig.add_gridspec(2, 3, width_ratios=[1.35, 1, 1.1], hspace=0.42, wspace=0.22, top=0.9, bottom=0.1, left=0.05, right=0.98)
bins_lab = ["0", "1", "2", "3", "4", "5", "≥6"]
w = 0.16
for r, t in enumerate(TASKS):
    out = RES[t]
    ax = fig.add_subplot(gs[r, 0])
    for i, (key, lab, col) in enumerate(RULES):
        sp = np.clip(out[key]["spreads"], 0, 6)
        h = np.array([(sp == b).mean() for b in range(7)]) * 100
        ax.bar(np.arange(7) + (i - 2) * w, h, w, color=col, label=f"{lab}（均值 {out[key]['spreads'].mean():.2f}）",
               edgecolor="white", lw=0.5)
    ax.set_xticks(range(7)); ax.set_xticklabels(bins_lab)
    ax.set_xlabel("一局内 4 个对象参与次数的极差（max − min）"); ax.set_ylabel("占局数 %")
    ax.set_title(f"{V.TASK_ZH[t]}：局内极差分布（越靠左越均衡）", fontsize=12.5)
    ax.legend(fontsize=9.5, loc="upper right"); ax.grid(axis="y", alpha=0.3)
    # 边际频率
    ax = fig.add_subplot(gs[r, 1])
    for i, (key, lab, col) in enumerate(RULES):
        ax.bar(np.arange(V.N) + (i - 2) * w, out[key]["freq"] * 100, w, color=col,
               label=f"{lab.split(' ')[0]}  卡方 p={out[key]['p']:.3f}", edgecolor="white", lw=0.5)
    ax.axhline(25, color="k", ls="--", lw=1)
    ax.set_ylim(23.5, 26.8); ax.set_xticks(range(V.N)); ax.set_xticklabels([f"bin_{i}" for i in range(V.N)])
    ax.set_ylabel("跨局参与频率 %（虚线 = 25%）")
    ax.set_title("跨局边际频率：全部 p > 0.05 ⇒ 都跨局均匀\n（V5 现状 S0 为 p≈0，bin_3 约 20%）", fontsize=12)
    ax.legend(fontsize=9, loc="upper right", ncol=1)
    # 汇总条：撤销率 / 极差≤1 / 极差≤2 / 整局可行
    ax = fig.add_subplot(gs[r, 2])
    metrics = [("撤销率", lambda v: v["undo"] * 100), ("极差 ≤1 的局", lambda v: np.mean(v["spreads"] <= 1) * 100),
               ("极差 ≤2 的局", lambda v: np.mean(v["spreads"] <= 2) * 100)]
    for i, (key, lab, col) in enumerate(RULES):
        vals = [f(out[key]) for _, f in metrics]
        xs = np.arange(len(metrics)) + (i - 2) * w
        ax.bar(xs, vals, w, color=col, edgecolor="white", lw=0.5, label=lab)
        for x, v in zip(xs, vals):
            ax.text(x, v + 1.2, f"{v:.1f}" if v < 99.95 else "100", ha="center", va="bottom", fontsize=7.5, rotation=90)
    ax.set_xticks(range(len(metrics))); ax.set_xticklabels([m for m, _ in metrics])
    ax.set_ylim(0, 122); ax.set_ylabel("%"); ax.grid(axis="y", alpha=0.3)
    ax.set_title("撤销率与局内均衡达标率", fontsize=12.5)
    ax.legend(fontsize=9, loc="upper left")
    s5 = out["S5"]; g = out["S5G"]
    ax.text(0.5, -0.17, f"S5 平均用 {s5['tries_mean']:.2f} 趟，需要重排的局 {s5['reroll_frac']*100:.1f}%；"
            f"G 连通率 {g['conn']*100:.1f}%（不连通布局 reset 拒绝）",
            transform=ax.transAxes, ha="center", va="top", fontsize=10.5, color="#1864ab")
fig.suptitle("图 4　局内均衡对比：S1（可行对均匀抽）/ S1n（+禁止立即撤销）/ S5（参与次数最少者优先）"
             "\n每个环境 10000 局真实内环布局（p2 已存的 G 上重放；S1、S1n 用 p2 原序列）", fontsize=15, y=0.985)
V.savefig(fig, "balance_compare.png")
