import sys, json, numpy as np
D='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
sys.path.insert(0, D)
import binfill_sampler as bs
from robomme.robomme_env.utils.object_generation import _obb2d_intersect, _build_new_cube_obb2d
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
rng=np.random.default_rng(12345)
LO=bs.REGION_C-bs.REGION_H+bs.HS; HI=bs.REGION_C+bs.REGION_H-bs.HS
CI={'red':0,'blue':1,'green':2}
LINK=0.09
R_PERM=1000
def spec_layouts():
    rows=[json.loads(l) for l in open(f'{ROOT}/scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
    out=[]
    for r in rows:
        if r.get('task')!='BinFill': continue
        s=r['spec']; o=s['objects']; L=s['layout']
        tasks=[(c,k) for c in ['red','blue','green'] for k in range(o['spawn_numbers'][CI[c]])]
        tasks=[tasks[i] for i in o['spawn_order']]
        cubes=[dict(color=c,idx=k,spawn_idx=si,x=L['cubes'][f'{c}_{k}'][0],y=L['cubes'][f'{c}_{k}'][1],yaw=L['cubes'][f'{c}_{k}'][2]) for si,(c,k) in enumerate(tasks)]
        out.append(dict(seed=r['seed'],episode=r['episode'],button=tuple(L['button_xy']),board=(0.15+L['board']['offsets'][0],L['board']['offsets'][1],L['board']['offsets'][2]),
                        spawn=o['spawn_numbers'],target=o['target_numbers'],cubes=cubes))
    return out

def arr(L):
    P=np.array([[c['x'],c['y']] for c in L['cubes']]); lab=np.array([CI[c['color']] for c in L['cubes']]); yaw=np.array([c['yaw'] for c in L['cubes']])
    return P,lab,yaw

def sq(x,y,yaw,h=bs.HS):
    c,s=np.cos(yaw),np.sin(yaw)
    loc=np.array([[h,h],[-h,h],[-h,-h],[h,-h]])
    return loc@np.array([[c,s],[-s,c]])+np.array([x,y])

def seg_pt(p,a,b):
    ab=b-a; t=np.clip(np.dot(p-a,ab)/np.dot(ab,ab),0,1); return np.linalg.norm(p-(a+t*ab))

def poly_gap(P1,P2,obb1,obb2):
    if _obb2d_intersect(*obb1,*obb2): return 0.0
    d=1e9
    for Pa,Pb in ((P1,P2),(P2,P1)):
        for p in Pa:
            for i in range(4): d=min(d,seg_pt(p,Pb[i],Pb[(i+1)%4]))
    return d

def stats_for(P,lab):
    """返回 (S_nn 同色最近邻均距, S_frac 最近邻同色比例, S_join 邻接边同色比例, S_comp 最大同色连通块)；批量支持 lab 为 (R,n)"""
    n=len(P); Dm=np.linalg.norm(P[:,None]-P[None],axis=-1); np.fill_diagonal(Dm,np.inf)
    nn=np.argmin(Dm,axis=1)
    adj=(Dm<LINK)
    iu=np.triu_indices(n,1); edges=adj[iu]
    L2=np.atleast_2d(lab)
    same=(L2[:,:,None]==L2[:,None,:])
    # S_nn
    Dsame=np.where(same,Dm[None],np.inf)
    mins=Dsame.min(axis=2); valid=np.isfinite(mins)
    S_nn=np.where(valid,mins,0).sum(1)/np.maximum(valid.sum(1),1)
    S_frac=(L2[:,nn]==L2).mean(1)
    se=same[:,iu[0],iu[1]][:,edges]
    S_join=se.mean(1) if edges.sum()>0 else np.zeros(len(L2))
    # 最大同色连通块（同色且中心距<LINK）
    S_comp=[]
    for l in L2:
        A=adj & (l[:,None]==l[None,:])
        seen=np.zeros(n,bool); best=0
        for s0 in range(n):
            if seen[s0]: continue
            st=[s0]; seen[s0]=True; cnt=0
            while st:
                u=st.pop(); cnt+=1
                for v in np.nonzero(A[u])[0]:
                    if not seen[v]: seen[v]=True; st.append(v)
            best=max(best,cnt)
        S_comp.append(best)
    return S_nn,S_frac,S_join,np.array(S_comp)

def perm_p(P,lab,R=R_PERM,need_comp=True):
    obs=[s[0] for s in stats_for(P,lab)]
    perms=np.array([rng.permutation(lab) for _ in range(R)])
    ns=stats_for(P,perms) if need_comp else stats_for(P,perms)
    # 单侧：聚集 ⇔ S_nn 小、S_frac 大、S_join 大、S_comp 大
    p_nn=(1+np.sum(ns[0]<=obs[0]))/(R+1)
    p_frac=(1+np.sum(ns[1]>=obs[1]))/(R+1)
    p_join=(1+np.sum(ns[2]>=obs[2]))/(R+1)
    p_comp=(1+np.sum(ns[3]>=obs[3]))/(R+1)
    z_nn=(obs[0]-ns[0].mean())/ns[0].std()
    return dict(obs=obs,p_nn=p_nn,p_frac=p_frac,p_join=p_join,p_comp=p_comp,z_nn=z_nn)

