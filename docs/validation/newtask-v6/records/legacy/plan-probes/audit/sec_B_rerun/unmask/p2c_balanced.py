"""P2c：在 P2 存下的每局可行槽对图 G 上补测「计数均衡贪心」S5（可行对里取两者已参与次数 max、再 sum 最小者，
不许立即撤销除非别无选择，并列均匀），不再调碰撞判定。"""
import json, sys
import numpy as np
from scipy.stats import chisquare
N=4; PAIRS=[(a,b) for a in range(N) for b in range(a+1,N)]
for task in sys.argv[1:]:
    R=json.load(open(f"p2_inner_{task}.json"))
    part=np.zeros(N); cover=[]; spread=[]; undo=[]; ok=0
    for r in R:
        G={p:bool(g) for p,g in zip(PAIRS,r["G"])}
        rng=np.random.default_rng(r["seed"]+17)
        occ=list(range(N)); cnt=[0]*N; last=None; seq=[]; fail=False
        for k in range(r["n"]):
            allf=[(a,b) for a,b in PAIRS if G[(min(occ[a],occ[b]),max(occ[a],occ[b]))]]
            c=[p for p in allf if p!=last] or allf
            if not c: fail=True; break
            key=[(max(cnt[a],cnt[b]),cnt[a]+cnt[b]) for a,b in c]; m=min(key)
            c=[p for p,kk in zip(c,key) if kk==m]; a,b=c[rng.integers(len(c))]
            if last is not None: undo.append((a,b)==last)
            cnt[a]+=1; cnt[b]+=1; occ[a],occ[b]=occ[b],occ[a]; last=(a,b); seq.append((a,b))
        if fail: continue
        ok+=1
        for a,b in seq: part[a]+=1; part[b]+=1
        cc=np.array(cnt); cover.append((cc>0).all()); spread.append(cc.max()-cc.min())
    chi=chisquare(part)
    print(f"  {task} S5 计数均衡贪心: 可行局 {ok/len(R):.4f} 参与频率 {(part/part.sum()).round(4).tolist()} χ²={chi.statistic:.1f} p={chi.pvalue:.3g} 全员参与 {np.mean(cover):.3f} 局内极差均值 {np.mean(spread):.2f} 极差分布 {dict(zip(*np.unique(spread,return_counts=True)))} 撤销率 {np.mean(undo):.3f}")
