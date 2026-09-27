# 汇总 big_sim 的输出：均匀性表、交换方案表、逐生成序号效应、逐轴直方图
import sys, json, numpy as np, itertools
from scipy import stats
path = sys.argv[1]
R = json.load(open(path))
seeds = sorted(R, key=int)
methods = list(R[seeds[0]].keys())
XL, XH, YL, YH = -0.28, 0.08, -0.23, 0.23
print(f"文件 {path}  layouts(seeds)={len(seeds)}")
print("\n== 摆放成功率与均匀性（每个成功布局一行统计后取均值；括号内为比例）==")
hdr = "method      ok%    trials  nn_mean  min_pair  CE_R   clump3%  max_cell>=3%  empty_cells  cover_r  side<=1%  far_half(x>-0.1)  nn_comp  init_ok%"
print(hdr)
for m in methods:
    recs = [R[s][m] for s in seeds]
    ok = [r for r in recs if r["ok"]]
    U = [r["uni"] for r in ok]
    f = lambda k: np.mean([u[k] for u in U])
    print(f"{m:10s} {100*len(ok)/len(recs):6.2f} {np.mean([r['trials'] for r in ok]):7.1f}  {f('nn_mean'):.4f}  {f('min_pair'):.4f}   {f('ce_R'):.3f}  {100*np.mean([u['clump3'] for u in U]):6.1f}   {100*np.mean([u['max_cell']>=3 for u in U]):6.1f}        {f('empty_cells'):.2f}      {f('cover_radius'):.3f}   {100*np.mean([u['side_min']<=1 for u in U]):6.1f}     {f('far_half'):.2f}             {np.mean([r['nn_comp'] for r in ok]):.2f}   {100*np.mean([r['init_ok'] for r in ok]):.1f}")
print("\n== 分位：最近邻均值 / 最小对距（5%,50%,95%）==")
for m in methods:
    ok = [R[s][m] for s in seeds if R[s][m]["ok"]]
    a = np.array([r["uni"]["nn_mean"] for r in ok]); b = np.array([r["uni"]["min_pair"] for r in ok]); c = np.array([r["uni"]["cover_radius"] for r in ok])
    print(f"{m:10s} nn_mean {np.percentile(a,[5,50,95]).round(3)}  min_pair {np.percentile(b,[5,50,95]).round(3)}  cover_r {np.percentile(c,[5,50,95]).round(3)}")
print("\n== 逐轴边缘分布（8 等分箱，占比%；与均匀的卡方 p 值）==")
for m in methods:
    ok = [R[s][m] for s in seeds if R[s][m]["ok"]]
    P = np.concatenate([np.array(r["P"]) for r in ok])
    hx, _ = np.histogram(P[:, 0], bins=8, range=(XL, XH)); hy, _ = np.histogram(P[:, 1], bins=8, range=(YL, YH))
    px = stats.chisquare(hx).pvalue; py = stats.chisquare(hy).pvalue
    print(f"{m:10s} x(近机器人→远): {(100*hx/hx.sum()).round(1)} p={px:.2g} | y: {(100*hy/hy.sum()).round(1)} p={py:.2g}")
print("\n== 生成序号效应（V4）：第 i 块的 |x-(-0.1)|、|y|、到先前各块的最近距离 ==")
for m in [mm for mm in methods if mm in ("v4", "bc8", "hc0.12", "grid6of8")]:
    ok = [R[s][m] for s in seeds if R[s][m]["ok"]]
    Ps = np.array([r["P"] for r in ok])  # (L,6,2)
    rows = []
    for i in range(6):
        dx = np.abs(Ps[:, i, 0] + 0.1).mean(); dy = np.abs(Ps[:, i, 1]).mean()
        if i:
            dprev = np.linalg.norm(Ps[:, :i] - Ps[:, i:i+1], axis=-1).min(1).mean()
        else:
            dprev = float("nan")
        rows.append(f"i{i}:|dx|={dx:.3f},|y|={dy:.3f},d_prev={dprev:.3f}")
    print(f"{m:10s} " + "  ".join(rows))
print("\n== 交换方案（每个成功布局跑一次；D5 = 真实 check_swap_sweep，槽位不含演示抓放扰动）==")
print("method     scheme                      all6_part%  part_mean  init_mean  moved_net  tgt_moves  tgt_slots  tgt_home%  undo  rep_pairs dist_pairs  len_mean  len_max  ep_rej%  swap_rej%  first_rej%  infeas")
for m in methods:
    ok = [R[s][m] for s in seeds if R[s][m]["ok"]]
    for sc in ok[0]["schemes"]:
        E = [r["schemes"][sc] for r in ok]
        g = lambda k: np.mean([e[k] for e in E])
        print(f"{m:10s} {sc:27s} {100*np.mean([e['participants']==6 for e in E]):7.1f}   {g('participants'):6.2f}    {g('initiators'):6.2f}    {g('moved_net'):6.2f}    {g('target_moves'):6.2f}    {g('target_distinct_slots'):6.2f}    {100*g('target_home'):6.1f}   {g('undo'):5.2f}  {g('repeat_pairs'):5.2f}   {g('distinct_pairs'):5.2f}     {g('mean_len'):.3f}    {g('max_len'):.3f}  {100*g('any_rej'):6.1f}   {100*np.sum([e['n_rej'] for e in E])/np.sum([e['n_swaps'] for e in E]):6.1f}    {100*np.mean([e['first_rej']==0 for e in E]):6.1f}   {np.mean([e['infeasible']>0 for e in E])*100:5.1f}")
    print()
print("== 布局级：全部 15 个槽位对中扫掠可行的比例；以及「至少存在一个可行搭档」的槽位比例 ==")
for m in methods:
    ok = [R[s][m] for s in seeds if R[s][m]["ok"]]
    fr = [np.mean([not v for v in r["pair_rej"].values()]) for r in ok if r["pair_rej"]]
    print(f"{m:10s} 已计算槽位对里可行比例均值={np.mean(fr):.3f}")
