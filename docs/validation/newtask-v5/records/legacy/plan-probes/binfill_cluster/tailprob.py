# 「像 ep3 那样的一团同色」在 V4 过程（颜色与位置独立）下的出现概率：对每局取「各颜色(≥3块)×{同色最近邻, x 分离, y 分离}」的最小置换 p，
# 与 ep3 自身同口径的最小 p 比较（已含多重比较：挑颜色、挑轴）
import sys, pickle, numpy as np
D='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
sys.path.insert(0,D)
from analyze_lib import arr, spec_layouts
rng=np.random.default_rng(99)
def colour_stats(P,labs):
    # labs: (R,n)。返回 dict[colour] -> (nn_same_mean, dx, dy) 数组（R,）
    Dm=np.linalg.norm(P[:,None]-P[None],axis=-1); np.fill_diagonal(Dm,np.inf)
    out={}
    for c in range(3):
        m=(labs==c)
        k=m[0].sum()
        if k<3: continue
        Dc=np.where(m[:,:,None]&m[:,None,:],Dm[None],np.inf)
        nn=np.where(m, Dc.min(2), 0).sum(1)/k
        dx=np.abs((P[None,:,0]*m).sum(1)/k-(P[None,:,0]*~m).sum(1)/(~m).sum(1))
        dy=np.abs((P[None,:,1]*m).sum(1)/k-(P[None,:,1]*~m).sum(1)/(~m).sum(1))
        out[c]=(nn,dx,dy)
    return out
def min_p(P,lab,R=2000):
    obs=colour_stats(P,lab[None])
    perms=np.array([rng.permutation(lab) for _ in range(R)])
    null=colour_stats(P,perms)
    best=1.0; which=None
    for c,(nn,dx,dy) in obs.items():
        pn=(1+np.sum(null[c][0]<=nn[0]))/(R+1); px=(1+np.sum(null[c][1]>=dx[0]))/(R+1); py=(1+np.sum(null[c][2]>=dy[0]))/(R+1)
        for p,w in ((pn,f'c{c}-nn'),(px,f'c{c}-x'),(py,f'c{c}-y')):
            if p<best: best, which=p, w
    return best, which
specs=spec_layouts()
ep3=[L for L in specs if L['seed']==4400300][0]
P3,l3,_=arr(ep3)
p3,w3=min_p(P3,l3,R=20000)
print(f'ep3 最小 p（各颜色≥3块 × {{nn,x,y}}）={p3:.4f} 来自 {w3}')
for L in specs:
    P,l,_=arr(L); p,w=min_p(P,l,R=5000); print(f'   seed {L["seed"]} spawn={L["spawn"]} minp={p:.4f} ({w})')
sims=[L for L in pickle.load(open(D+'/sim_v4_exact.pkl','rb')) if L][:1500]
mp=np.array([min_p(*arr(L)[:2],R=1000)[0] for L in sims])
print(f'V4 过程 1500 局：P(minp <= ep3 的 {p3:.4f}) = {np.mean(mp<=p3):.4f}；P(minp<=0.01)={np.mean(mp<=0.01):.4f} P(minp<=0.05)={np.mean(mp<=0.05):.4f}')
mx=np.array([max(L['spawn']) for L in sims])
print(f'   条件 max colour>=7：P(minp<=ep3)={np.mean(mp[mx>=7]<=p3):.4f} (n={np.sum(mx>=7)})')
print(f'   每 3 局正式集至少 1 局 ≥ep3 程度: {1-(1-np.mean(mp<=p3))**3:.3f}；10 条候选至少 1 条: {1-(1-np.mean(mp<=p3))**10:.3f}')
