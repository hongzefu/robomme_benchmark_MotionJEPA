"""汇总 study.py 的结果：成功率、对象层面均匀性（卡方）、局内均衡、与槽位可行度/按钮距离的相关、路径长度、拒绝采样预算。"""
import sys, json, collections
import numpy as np
from scipy.stats import chi2 as CHI2

D = json.load(open(sys.argv[1])); A = D["args"]; eps = D["eps"]; N = A["n_cubes"]
placed = [e for e in eps if e["placed"]]
print(f"# {sys.argv[1]}：{A['M']} 局，N={N}，dmin={A['dmin']}，n_swaps∈{A['swaps']}")
print(f"摆放成功 {len(placed)}/{A['M']} = {len(placed)/A['M']:.4f}；每局 trial 均值 {np.mean([e['trials'] for e in placed]):.0f}")
deg = np.array([e["deg"] for e in placed])
iso = (deg == 0).any(1)
print(f"槽位可行度（每槽可与几个槽位换）均值 {deg.mean():.2f}；分布 {dict(sorted(collections.Counter(deg.ravel().tolist()).items()))}")
print(f"存在孤立槽位（该块整局无法交换）的局 {iso.mean():.4f}；可行图无边 {(deg.sum(1)==0).mean():.4f}")
print(f"可行性矩阵计算耗时 均值 {np.mean([e['t_feas'] for e in placed])*1e3:.0f} ms，p95 {np.percentile([e['t_feas'] for e in placed],95)*1e3:.0f} ms")
bmin_all = np.array([min(e["btn_dist"]) for e in placed])


def chi(counts):
    counts = np.asarray(counts, float); E = counts.sum() / len(counts)
    x = ((counts - E) ** 2 / E).sum(); return x, CHI2.sf(x, len(counts) - 1)


rows = []
for name in A["names"]:
    R = [(e, e["res"][name]) for e in placed]
    ok = [(e, r) for e, r in R if r["ok"]]
    succ = len(ok) / A["M"]
    part = np.array([r["part"] for e, r in ok]); ini = np.array([r["ini"] for e, r in ok]); par = np.array([r["par"] for e, r in ok])
    nsw = np.array([e["n_swaps"] for e, r in ok])
    spread = part.max(1) - part.min(1)
    all_in = (part.min(1) >= 1).mean()
    # 标签层面卡方（跨局累计）
    x_part, p_part = chi(part.sum(0)); x_ini, p_ini = chi(ini.sum(0)); x_par, p_par = chi(par.sum(0))
    pc = collections.Counter()
    for e, r in ok:
        pc.update(r["pairs"])
    allpairs = [f"{a}-{b}" for a in range(N) for b in range(a + 1, N)]
    x_pair, p_pair = chi([pc[k] for k in allpairs])
    # 局内均匀性：每局对 N 个计数做卡方（期望 2n/N），报均值与 p<0.05 占比
    within = [chi(c) for c in part]
    # 与初始槽位可行度的关系：参与率 = 次数 / (2n/N)
    rate = part / (2 * nsw[:, None] / N)
    dg = np.array([e["deg"] for e, r in ok])
    by_deg = {int(d): float(rate[dg == d].mean()) for d in sorted(set(dg.ravel().tolist())) if (dg == d).sum() > 50}
    bd = np.array([e["btn_dist"] for e, r in ok])
    near_btn = bd < 0.12
    rate_near_btn = float(rate[near_btn].mean()) if near_btn.any() else float("nan")
    rate_far_btn = float(rate[~near_btn].mean())
    Ls = np.concatenate([r["L"] for e, r in ok]); Lmax = np.array([max(r["L"]) for e, r in ok])
    tm = np.array([r["target_moves"] for e, r in ok]); home = np.mean([r["target_home"] for e, r in ok])
    maxrep = np.mean([r["maxrep"] for e, r in ok]); bf = np.mean([r["backforth"] for e, r in ok])
    acc_bmin = np.array([min(e["btn_dist"]) for e, r in ok])
    tries = [r["tries"] for e, r in R if r.get("tries")]
    print(f"\n## {name}")
    print(f"  成功率(相对全部抽样) {succ:.4f}；失败 {collections.Counter(str(r['fail_k']) for e, r in R if not r['ok']).most_common(8)}")
    print(f"  全员参与 {all_in:.4f}；局内极差(max-min)分布 {dict(sorted(collections.Counter(spread.tolist()).items()))}；极差≤1 占 {(spread<=1).mean():.4f}")
    print(f"  标签层面卡方(跨局累计)：参与 χ²={x_part:.1f} p={p_part:.3g}；发起 χ²={x_ini:.1f} p={p_ini:.3g}；搭档 χ²={x_par:.1f} p={p_par:.3g}；对({len(allpairs)}格) χ²={x_pair:.1f} p={p_pair:.3g}")
    print(f"  参与计数合计 {part.sum(0).tolist()}；对频数 min/max {min(pc[k] for k in allpairs)}/{max(pc[k] for k in allpairs)}")
    print(f"  局内卡方均值 {np.mean([w[0] for w in within]):.2f}，局内 p<0.05 占 {np.mean([w[1]<0.05 for w in within]):.4f}")
    print(f"  参与率 vs 初始槽位可行度 {({k: round(v,3) for k,v in by_deg.items()})}；按钮 12 cm 内的块 {rate_near_btn:.3f} vs 其余 {rate_far_btn:.3f}")
    print(f"  单段路径 均值 {Ls.mean():.3f} p95 {np.percentile(Ls,95):.3f} 最大 {Ls.max():.3f}；每局最长段 均值 {Lmax.mean():.3f} p95 {np.percentile(Lmax,95):.3f}；>0.30 m 段占 {(Ls>0.30).mean():.4f}")
    print(f"  目标被换次数 均值 {tm.mean():.2f}，P(=0) {(tm==0).mean():.4f}，P(≤2) {(tm<=2).mean():.4f}；目标回原位 {home:.4f}；同一对最多重复 {maxrep:.2f}；紧邻换回 {bf:.2f} 次/局")
    print(f"  布局选择偏差：被接受局「最近块到按钮中心」均值 {acc_bmin.mean():.4f} m（全部摆放成功局 {bmin_all.mean():.4f}）")
    if tries:
        t = np.array(tries); print(f"  整条拒绝采样尝试次数 均值 {t.mean():.2f} p95 {np.percentile(t,95):.0f} 最大 {t.max()}；预算耗尽 {sum(1 for e,r in R if r['fail_k']==-2)}")
    rows.append(dict(name=name, succ=succ, all_in=float(all_in), spread_le1=float((spread <= 1).mean()), chi_part_p=float(p_part),
                     chi_pair_p=float(p_pair), by_deg=by_deg, near_btn=rate_near_btn, far_btn=rate_far_btn,
                     L_mean=float(Ls.mean()), Lmax_p95=float(np.percentile(Lmax, 95)), L_max=float(Ls.max()),
                     tm_mean=float(tm.mean()), home=float(home), acc_bmin=float(acc_bmin.mean())))
json.dump(rows, open(sys.argv[1].replace(".json", "_summary.json"), "w"), ensure_ascii=False, indent=1)
