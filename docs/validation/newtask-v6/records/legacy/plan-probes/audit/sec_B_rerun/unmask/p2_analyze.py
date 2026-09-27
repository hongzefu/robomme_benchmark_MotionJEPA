"""P2 结果汇总：各算法下对象级（bin_i）作发起者/参与者频率、卡方、局内均衡、配对频率、可行率。"""
import json, sys
import numpy as np
from scipy.stats import chisquare
N_OBJ = 4
PAIRS = [(a, b) for a in range(N_OBJ) for b in range(a + 1, N_OBJ)]
for task in sys.argv[1:]:
    R = json.load(open(f"p2_inner_{task}.json"))
    print(f"=== {task} layouts={len(R)}")
    G = np.array([r["G"] for r in R])
    print("  槽对可行率（(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)）:", G.mean(0).round(4).tolist(),
          " 可行对数分布:", {int(k): int(v) for k, v in zip(*np.unique(G.sum(1), return_counts=True))})
    D = np.array([r["dist"] for r in R])
    print("  槽对中心距均值 m:", D.mean(0).round(3).tolist())
    for rule in ("S0", "S1", "S1n", "S2", "S2n", "S3", "S4"):
        seqs = [r[rule] for r in R if (r.get(rule) is not None)]
        cand = [r for r in R if not (rule == "S4" and r.get("S4_tries") is None)]
        if not seqs:
            print(f"  {rule}: 无可行"); continue
        part = np.zeros(N_OBJ); init = np.zeros(N_OBJ); pc = np.zeros(len(PAIRS))
        cover = []; spread = []; undo = []; imb = []
        for r in cand:
            s = r.get(rule)
            if s is None: continue
            c = np.zeros(N_OBJ)
            for k, (a, b) in enumerate(s):
                part[a] += 1; part[b] += 1; c[a] += 1; c[b] += 1
                pc[PAIRS.index((min(a, b), max(a, b)))] += 1
                if k and tuple(s[k - 1]) == (a, b): undo.append(1)
                elif k: undo.append(0)
            cover.append((c > 0).all()); spread.append(c.max() - c.min())
            imb.append(r.get(rule + "_imb", 0) or 0)
        freq = part / part.sum()
        chi = chisquare(part)
        pfreq = pc / pc.sum()
        feas = len(seqs) / len(cand)
        print(f"  {rule}: 可行局 {feas:.4f}（{len(seqs)}/{len(cand)}）参与频率 {freq.round(4).tolist()} χ²={chi.statistic:.1f} p={chi.pvalue:.3g} | "
              f"对频率 {pfreq.round(3).tolist()} | 全员参与 {np.mean(cover):.3f} 局内极差均值 {np.mean(spread):.2f} 撤销率 {np.mean(undo):.3f} 失衡事件/局 {np.mean(imb):.2f}")
    if R[0].get("S0") is not None:
        # 现状发起者频率（swap_indices 解析）
        pass
    tr = [r["S4_tries"] for r in R if r.get("S4_tries") is not None]
    ok4 = [r for r in R if r.get("S4_tries") is not None and r.get("S4") is not None]
    print(f"  S4 子样本 {len(tr)} 局：16 次内接受 {len(ok4)/max(1,len(tr)):.3f}，接受者平均尝试 {np.mean([r['S4_tries'] for r in ok4]) if ok4 else float('nan'):.2f}")
