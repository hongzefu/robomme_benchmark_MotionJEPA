# V5 候选方案的反事实模拟：
#  V5a 真实方块 OBB（修退化）——用 sim_trueobb.pkl
#  V5b 摆放后按「最大同色连通块 ≤ T」重抽颜色排列（位置不动，追加抽样）
#  V5c best-candidate(Mitchell) k 选 1 的蓝噪声摆放（真实 OBB）
import sys, pickle, time, numpy as np, torch
from scipy import stats
D='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
sys.path.insert(0, D)
import binfill_sampler as bs
from analyze_lib import arr, stats_for, LINK
from robomme.robomme_env.utils.object_generation import _obb2d_intersect, _build_new_cube_obb2d
torch.set_num_threads(1)
rng=np.random.default_rng(7)
sims=[L for L in pickle.load(open(D+'/sim_v4_exact.pkl','rb')) if L]
simt=[L for L in pickle.load(open(D+'/sim_trueobb.pkl','rb')) if L]
LO=bs.REGION_C-bs.REGION_H+bs.HS; HI=bs.REGION_C+bs.REGION_H-bs.HS

def summarize(name, Ls, labels_override=None):
    comps=[]; fr=[]; nnd=[]; P_all=[]
    for i,L in enumerate(Ls):
        P,lab,_=arr(L)
        if labels_override is not None: lab=labels_override[i]
        s=stats_for(P,lab); comps.append(s[3][0]); fr.append(s[1][0])
        Dm=np.linalg.norm(P[:,None]-P[None],axis=-1); np.fill_diagonal(Dm,np.inf); nnd.append(Dm.min(1)); P_all.append(P)
    comps=np.array(comps); nnd=np.concatenate(nnd); P_all=np.concatenate(P_all)
    H,_,_=np.histogram2d(P_all[:,0],P_all[:,1],bins=[6,6],range=[[LO[0],HI[0]],[LO[1],HI[1]]]); rel=H/H.mean()
    print(f'[{name}] n={len(Ls)} P(comp>=4)={np.mean(comps>=4):.4f} P(comp>=3)={np.mean(comps>=3):.4f} meanS_frac={np.mean(fr):.3f} NN中心距 p5={np.percentile(nnd,5):.4f} 中位={np.median(nnd):.4f} | 6x6相对密度 min={rel.min():.2f} max={rel.max():.2f} cv={rel.std():.3f}')
    return comps

c4=summarize('V4 现状', sims)
ct=summarize('V5a 真实OBB', simt)

# V5b：颜色重排约束（在 V5a 位置上）
def redraw(L, T, K=64):
    P,lab,_=arr(L)
    s=stats_for(P,lab)[3][0]
    if s<=T: return lab,0,True
    best=(s,lab)
    for k in range(1,K+1):
        l2=rng.permutation(lab); s2=stats_for(P,l2)[3][0]
        if s2<=T: return l2,k,True
        if s2<best[0]: best=(s2,l2)
    return best[1],K,False
for T in (3,2):
    labs=[]; tries=[]; ok=[]
    for L in simt[:2000]:
        l,k,g=redraw(L,T); labs.append(l); tries.append(k); ok.append(g)
    tries=np.array(tries)
    print(f'[V5b T={T}] 首次即满足={np.mean(tries==0):.3f} 平均重抽次数={tries.mean():.2f} 最大={tries.max()} K=64 内满足={np.mean(ok):.4f}')
    summarize(f'V5b T={T}', simt[:2000], labs)
    # 过度混色检查：置换 p 值的分布（反聚集方向）
    ps=[]
    for L,l in zip(simt[:500],labs[:500]):
        P,_,_=arr(L); obs=stats_for(P,l)[1][0]
        perms=np.array([rng.permutation(l) for _ in range(300)]); ns=stats_for(P,perms)[1]
        ps.append((1+np.sum(ns<=obs))/301)
    ps=np.array(ps); print(f'    反聚集方向 S_frac 置换 p<0.05 比例={np.mean(ps<0.05):.3f}（均匀混色应≈≤0.05）')

# V5c：best-candidate 蓝噪声
def sample_bc(seed, k=4, max_trials=256):
    g=torch.Generator().manual_seed(seed)
    L=bs.sample_layout(generator=g, exact=False, max_trials=0)  # 只为了拿 meta？max_trials=0 会直接失败
    return None
def sample_layout_bc(seed, k=4, max_trials=256):
    g=torch.Generator().manual_seed(int(seed))
    # 复用 sample_layout 的 meta 抽样：通过 place_fn 钩子太绕，这里直接内联（与 binfill_sampler 同序）
    off=torch.rand(2,generator=g)-0.5; cx=-0.2+float(off[0])*0.1; cy=float(off[1])*0.4
    button=bs.create_button_obb(center_xy=(cx,cy),half_size=0.05625)
    xv=torch.rand(1,generator=g).item()*0.2-0.2; yv=torch.rand(1,generator=g).item()*0.4-0.2; torch.rand(1,generator=g)
    bx,by=0.15+xv,yv
    cp=torch.randperm(3,generator=g).tolist(); pic=torch.randint(2,4,(1,),generator=g).item(); active=cp[:pic]
    tgt=[0,0,0]; tt=torch.randint(5,8,(1,),generator=g).item()
    for _ in range(tt): tgt[active[torch.randint(0,len(active),(1,),generator=g).item()]]+=1
    torch.randint(12,13,(1,),generator=g)
    spawn=[0,0,0]
    for i in cp: spawn[i]=max(tgt[i],1)
    for _ in range(12-sum(spawn)): spawn[cp[torch.randint(0,3,(1,),generator=g).item()]]+=1
    tasks=[(bs.COLORS[c],kk) for c in range(3) for kk in range(spawn[c])]
    order=torch.randperm(len(tasks),generator=g).tolist(); tasks=[tasks[i] for i in order]
    obst=[button]+bs.board_strips(bx,by); cubes=[]; draws=0
    for si,(col,kk) in enumerate(tasks):
        cands=[]
        for _ in range(k):
            got=None
            for t in range(max_trials):
                u1=torch.rand(1,generator=g).item(); u2=torch.rand(1,generator=g).item(); yaw=float(torch.rand(1,generator=g).item()*2*np.pi); draws+=3
                x=float(LO[0]+u1*(HI[0]-LO[0])); y=float(LO[1]+u2*(HI[1]-LO[1]))
                cn,An,hn=_build_new_cube_obb2d(x,y,bs.HS,yaw,pad_xy=bs.MIN_GAP)
                if any(_obb2d_intersect(c,A,h,cn,An,hn) for (c,A,h) in obst): continue
                got=(x,y,yaw); break
            if got is None: break
            cands.append(got)
        if not cands: return None
        if cubes:
            Pp=np.array([[c['x'],c['y']] for c in cubes])
            score=[np.min(np.linalg.norm(Pp-np.array(c[:2]),axis=1)) for c in cands]
            best=cands[int(np.argmax(score))]
        else: best=cands[0]
        cubes.append(dict(color=col,idx=kk,spawn_idx=si,x=best[0],y=best[1],yaw=best[2]))
        obst.append(_build_new_cube_obb2d(best[0],best[1],bs.HS,best[2],0.0))
    return dict(cubes=cubes,button=(cx,cy),board=(bx,by,0),spawn=spawn,draws=draws)
for k in (2,4):
    t0=time.time(); Ls=[]; fails=0; dr=[]
    for i in range(1500):
        L=sample_layout_bc(91000000+i,k=k)
        if L is None: fails+=1; continue
        Ls.append(L); dr.append(L['draws'])
    print(f'[V5c k={k}] fails={fails}/1500 平均随机数调用={np.mean(dr):.0f}（V4 约 {3*12*1.6:.0f} 量级） wall={time.time()-t0:.0f}s')
    summarize(f'V5c k={k}', Ls)
# V4 平均每块 trial 数
tr=np.concatenate([L['trials'] for L in sims]); print(f'[V4] 每块平均 trial={tr.mean():.2f} p99={np.percentile(tr,99):.0f} max={tr.max()}  ⇒ 平均随机数调用≈{3*tr.mean()*12:.0f}/局')
