"""P2d：可行槽对图 G 连通（4 个槽都能经可行交换互达）的比例；只在连通布局上复测 S5 的局内均衡与边际均匀。
（设想：V6 新档把「G 连通」作为内环布局的 reset 级拒绝条件。）"""
import json, sys
import numpy as np
from scipy.stats import chisquare
N=4; PAIRS=[(a,b) for a in range(N) for b in range(a+1,N)]
def conn(G):
    e=[p for p,g in zip(PAIRS,G) if g]; seen={0}; st=[0]
    while st:
        u=st.pop()
        for a,b in e:
            for x,y in ((a,b),(b,a)):
                if x==u and y not in seen: seen.add(y); st.append(y)
    return len(seen)==N
for task in sys.argv[1:]:
    R=json.load(open(f"p2_inner_{task}.json"))
    C=[r for r in R if conn(r["G"])]
    part=np.zeros(N); spread=[]; undo=[]; nn=[]
    for r in C:
        G={p:bool(g) for p,g in zip(PAIRS,r["G"])}
        rng=np.random.default_rng(r["seed"]+17); occ=list(range(N)); cnt=[0]*N; last=None
        for k in range(r["n"]):
            allf=[(a,b) for a,b in PAIRS if G[(min(occ[a],occ[b]),max(occ[a],occ[b]))]]
            c=[p for p in allf if p!=last] or allf
            key=[(max(cnt[a],cnt[b]),cnt[a]+cnt[b]) for a,b in c]; m=min(key)
            c=[p for p,kk in zip(c,key) if kk==m]; a,b=c[rng.integers(len(c))]
            if last is not None: undo.append((a,b)==last)
            cnt[a]+=1; cnt[b]+=1; occ[a],occ[b]=occ[b],occ[a]; last=(a,b)
            part[a]+=1; part[b]+=1
        cc=np.array(cnt); spread.append(cc.max()-cc.min())
    chi=chisquare(part)
    print(f"  {task} G 连通比例 {len(C)/len(R):.4f}；连通布局上 S5：参与频率 {(part/part.sum()).round(4).tolist()} p={chi.pvalue:.3g} 局内极差分布 {dict(zip(*np.unique(spread,return_counts=True)))} 撤销率 {np.mean(undo):.3f}")
