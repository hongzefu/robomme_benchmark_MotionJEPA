# BinFill xhard 摆放统计：均匀性 / 颜色-空间相关（置换检验）/ 生成顺序偏置 / min_gap 退化 / 颜色配额
import sys, json, pickle, numpy as np
from scipy import stats
D='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
sys.path.insert(0, D)
import binfill_sampler as bs
from robomme.robomme_env.utils.object_generation import _obb2d_intersect, _build_new_cube_obb2d
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
rng=np.random.default_rng(12345)
LO=bs.REGION_C-bs.REGION_H+bs.HS; HI=bs.REGION_C+bs.REGION_H-bs.HS
CI={'red':0,'blue':1,'green':2}
LINK=0.09  # 邻接阈值（中心距 < 9cm ≈ 两块方块面间距 < ~5cm，图像上看作「挨着」）
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

report={}
specs=spec_layouts()
sims=[L for L in pickle.load(open(D+'/sim_v4_exact.pkl','rb')) if L is not None]
simt=[L for L in pickle.load(open(D+'/sim_trueobb.pkl','rb')) if L is not None]
print('specs',len(specs),'sims',len(sims),'sims_trueobb',len(simt))

# ---------- A. 均匀性 ----------
def pooled(Ls): return np.concatenate([arr(L)[0] for L in Ls])
for name,Ls in (('specs10',specs),('sim_v4',sims),('sim_trueobb',simt)):
    P=pooled(Ls)
    ksx=stats.kstest((P[:,0]-LO[0])/(HI[0]-LO[0]),'uniform'); ksy=stats.kstest((P[:,1]-LO[1])/(HI[1]-LO[1]),'uniform')
    q=np.array([np.sum((P[:,0]<-0.1)&(P[:,1]<0)),np.sum((P[:,0]<-0.1)&(P[:,1]>=0)),np.sum((P[:,0]>=-0.1)&(P[:,1]<0)),np.sum((P[:,0]>=-0.1)&(P[:,1]>=0))])
    chi=stats.chisquare(q)
    # 6x6 网格密度（相对均匀的比值）
    H,_,_=np.histogram2d(P[:,0],P[:,1],bins=[6,6],range=[[LO[0],HI[0]],[LO[1],HI[1]]])
    rel=H/H.mean()
    print(f'[A] {name}: n={len(P)} KS_x D={ksx.statistic:.4f} p={ksx.pvalue:.2e} | KS_y D={ksy.statistic:.4f} p={ksy.pvalue:.2e} | quadrants(x<-.1&y<0, x<-.1&y>=0, x>=-.1&y<0, x>=-.1&y>=0)={q.tolist()} chi2 p={chi.pvalue:.2e} | 6x6 rel density min={rel.min():.2f} max={rel.max():.2f} cv={rel.std():.3f}')
    if name=='sim_v4':
        np.set_printoptions(precision=2,suppress=True)
        print('    6x6 相对密度（行=x 从 -0.28 到 0.08，列=y 从 -0.23 到 0.23）:\n', rel)
        # x 方向 12 bin 边缘密度
        hx,ex=np.histogram(P[:,0],bins=12,range=(LO[0],HI[0])); print('    x marginal rel:', np.round(hx/hx.mean(),2).tolist(), 'edges', np.round(ex,3).tolist())
        hy,ey=np.histogram(P[:,1],bins=12,range=(LO[1],HI[1])); print('    y marginal rel:', np.round(hy/hy.mean(),2).tolist())

# 参考：独立均匀于「区域−按钮−孔板」自由空间（无方块互斥），同一批按钮/孔板
def free_uniform(Ls,k=12):
    out=[]
    for L in Ls:
        obst=[bs.create_button_obb(center_xy=L['button'],half_size=0.05625)]+bs.board_strips(L['board'][0],L['board'][1])
        got=0
        while got<k:
            u=rng.random(3); x=LO[0]+u[0]*(HI[0]-LO[0]); y=LO[1]+u[1]*(HI[1]-LO[1]); yaw=u[2]*2*np.pi
            cn,An,hn=_build_new_cube_obb2d(x,y,bs.HS,yaw,pad_xy=bs.MIN_GAP)
            if any(_obb2d_intersect(c,A,h,cn,An,hn) for (c,A,h) in obst): continue
            out.append((x,y)); got+=1
    return np.array(out)
FU=free_uniform(sims[:1500])
PV=pooled(sims[:1500])
print(f'[A] free-space-uniform ref (1500 layouts): KS2 x D={stats.ks_2samp(PV[:,0],FU[:,0]).statistic:.4f} p={stats.ks_2samp(PV[:,0],FU[:,0]).pvalue:.2e}; y D={stats.ks_2samp(PV[:,1],FU[:,1]).statistic:.4f} p={stats.ks_2samp(PV[:,1],FU[:,1]).pvalue:.2e}')
hx1,_=np.histogram(PV[:,0],bins=12,range=(LO[0],HI[0])); hx2,_=np.histogram(FU[:,0],bins=12,range=(LO[0],HI[0]))
print('    x marginal RSA/free-uniform ratio:', np.round(hx1/np.maximum(hx2,1),2).tolist())
# 自由空间面积比例（区域内中心可行点中被按钮/孔板排除的比例），蒙特卡洛
fr=[]
for L in sims[:500]:
    obst=[bs.create_button_obb(center_xy=L['button'],half_size=0.05625)]+bs.board_strips(L['board'][0],L['board'][1])
    U=rng.random((400,3)); cnt=0
    for u in U:
        x=LO[0]+u[0]*(HI[0]-LO[0]); y=LO[1]+u[1]*(HI[1]-LO[1])
        cn,An,hn=_build_new_cube_obb2d(x,y,bs.HS,u[2]*2*np.pi,pad_xy=bs.MIN_GAP)
        cnt+= not any(_obb2d_intersect(c,A,h,cn,An,hn) for (c,A,h) in obst)
    fr.append(cnt/400)
print(f'[A] 区域内中心可行比例（扣按钮+孔板）mean={np.mean(fr):.3f} min={np.min(fr):.3f} max={np.max(fr):.3f}')

# ---------- E. 颜色配额 ----------
cnts=np.array([sorted(L['spawn'],reverse=True) for L in sims])
mx=cnts[:,0]
print('[E] 最多色块数分布:', {int(k):round(float(np.mean(mx==k)),4) for k in np.unique(mx)}, ' P(max>=7)=',round(float(np.mean(mx>=7)),4))
print('[E] specs10 max colour counts:', [max(L['spawn']) for L in specs])

# ---------- B. 颜色-空间相关 ----------
def run_perm(Ls, label, R=R_PERM):
    res=[perm_p(*arr(L)[:2],R=R) for L in Ls]
    ps={k:np.array([r[k] for r in res]) for k in ('p_nn','p_frac','p_join','p_comp')}
    z=np.array([r['z_nn'] for r in res])
    line=' '.join(f'{k}: frac<.05={np.mean(v<0.05):.3f} mean={v.mean():.3f}' for k,v in ps.items())
    print(f'[B] {label} n={len(Ls)} {line} | mean z_nn={z.mean():+.3f} (sd {z.std():.2f}, t-test p={stats.ttest_1samp(z,0).pvalue:.3f})')
    return res
res_specs=run_perm(specs,'specs10')
for L,r in zip(specs,res_specs):
    print(f'    seed {L["seed"]} ep{L["episode"]} spawn={L["spawn"]} S_nn={r["obs"][0]:.4f} S_frac={r["obs"][1]:.3f} S_join={r["obs"][2]:.3f} S_comp={int(r["obs"][3])} | p_nn={r["p_nn"]:.3f} p_frac={r["p_frac"]:.3f} p_join={r["p_join"]:.3f} p_comp={r["p_comp"]:.3f}')
res_sims=run_perm(sims[:2000],'sim_v4[:2000]',R=500)
# ep3 细看
ep3=[L for L in specs if L['seed']==4400300][0]
P3,l3,y3=arr(ep3)
r3=perm_p(P3,l3,R=20000)
print(f'[B] ep3 R=20000: obs S_nn={r3["obs"][0]:.4f} S_frac={r3["obs"][1]:.3f} S_join={r3["obs"][2]:.3f} S_comp={int(r3["obs"][3])} p_nn={r3["p_nn"]:.4f} p_frac={r3["p_frac"]:.4f} p_join={r3["p_join"]:.4f} p_comp={r3["p_comp"]:.4f}')
# 只看红色：红色最近邻均距 与 红色连通块
def red_stats(P,lab,red=0):
    Dm=np.linalg.norm(P[:,None]-P[None],axis=-1); np.fill_diagonal(Dm,np.inf)
    idx=np.nonzero(lab==red)[0]
    sub=Dm[np.ix_(idx,idx)]
    return sub.min(1).mean()
obs_r=red_stats(P3,l3)
perm_r=np.array([red_stats(P3,rng.permutation(l3)) for _ in range(20000)])
print(f'[B] ep3 red-only mean NN(red→red) obs={obs_r:.4f} null mean={perm_r.mean():.4f} p={(1+np.sum(perm_r<=obs_r))/20001:.4f}')
# 进程级尾概率：在 V4 模拟布局里，出现「最大同色连通块 ≥ ep3 值」的比例；以及同样色数（max>=7）条件下
comp_sims=np.array([stats_for(*arr(L)[:2])[3][0] for L in sims])
print(f'[B] V4 进程：P(最大同色连通块 >= {int(r3["obs"][3])}) = {np.mean(comp_sims>=r3["obs"][3]):.4f}; 分布', {int(k):round(float(np.mean(comp_sims==k)),3) for k in np.unique(comp_sims)})
print(f'[B]   条件 max colour>=7: P = {np.mean(comp_sims[mx>=7]>=r3["obs"][3]):.4f} (n={np.sum(mx>=7)})')
comp_t=np.array([stats_for(*arr(L)[:2])[3][0] for L in simt])
print(f'[B] trueOBB 反事实：P(最大同色连通块 >= {int(r3["obs"][3])}) = {np.mean(comp_t>=r3["obs"][3]):.4f}')
# 红色在 x 方向的分离：ep3 红色 x 均值 vs 非红色 x 均值
dx=P3[l3==0,0].mean()-P3[l3!=0,0].mean()
permdx=np.array([ (lambda l: P3[l==0,0].mean()-P3[l!=0,0].mean())(rng.permutation(l3)) for _ in range(20000)])
print(f'[B] ep3 红色与非红色 x 均值差 obs={dx:.4f} m, 置换 p(两侧)={(1+np.sum(np.abs(permdx)>=abs(dx)))/20001:.4f}')

# ---------- C. 生成顺序偏置 ----------
rows=[]
for L in sims:
    P,lab,yaw=arr(L)
    Dm=np.linalg.norm(P[:,None]-P[None],axis=-1); np.fill_diagonal(Dm,np.inf)
    for c,p,nnd in zip(L['cubes'],P,Dm.min(1)):
        border=min(p[0]-LO[0],HI[0]-p[0],p[1]-LO[1],HI[1]-p[1])
        rows.append((c['spawn_idx'],np.linalg.norm(p-bs.REGION_C),border,p[0],p[1],nnd,np.linalg.norm(p-np.array(L['button'])),np.linalg.norm(p-np.array(L['board'][:2]))))
R=np.array(rows)
names=['dist_center','dist_border','x','y','nn_dist','dist_button','dist_board']
print('[C] 按 spawn_idx 的均值（0..11）:')
for j,nm in enumerate(names,1):
    means=[R[R[:,0]==k,j].mean() for k in range(12)]
    rho=stats.spearmanr(R[:,0],R[:,j])
    kw=stats.kruskal(*[R[R[:,0]==k,j] for k in range(12)])
    print(f'    {nm:12s}', np.round(means,4).tolist(), f'spearman rho={rho.correlation:+.4f} p={rho.pvalue:.2e} KW p={kw.pvalue:.2e}')
# 生成顺序分组的空间分离：前 4 块 vs 后 8 块（与 ep3「4 绿先生成」同构）
pg=[]
for L in sims[:2000]:
    P,_,_=arr(L); grp=np.array([0 if c['spawn_idx']<4 else 1 for c in L['cubes']])
    pg.append(perm_p(P,grp,R=300))
for k in ('p_nn','p_frac','p_join','p_comp'):
    v=np.array([r[k] for r in pg]); print(f'[C] 分组(前4 vs 后8) {k}: frac<.05={np.mean(v<0.05):.3f} mean={v.mean():.3f}')
zg=np.array([r['z_nn'] for r in pg]); print(f'[C] 分组 z_nn mean={zg.mean():+.3f} t-test p={stats.ttest_1samp(zg,0).pvalue:.2e}')

# ---------- D. min_gap / OBB 退化 ----------
def gaps(Ls):
    mins=[]; pairs_lt=0; pairs=0
    for L in Ls:
        P,lab,yaw=arr(L); polys=[sq(*p,a) for p,a in zip(P,yaw)]; obbs=[_build_new_cube_obb2d(p[0],p[1],bs.HS,a,0.0) for p,a in zip(P,yaw)]
        n=len(P); G=np.full((n,n),np.inf)
        for i in range(n):
            for j in range(i+1,n):
                if np.linalg.norm(P[i]-P[j])>0.12: continue
                G[i,j]=G[j,i]=poly_gap(polys[i],polys[j],obbs[i],obbs[j])
        mins.append(G.min(1))
    return np.concatenate(mins)
g4=gaps(sims[:1000]); gt=gaps(simt[:1000])
for nm,g in (('V4(退化OBB)',g4),('trueOBB',gt)):
    print(f'[D] {nm}: 每块到最近方块的真实面间距 <0.02(min_gap) 比例={np.mean(g<0.02-1e-9):.3f}  <0.01={np.mean(g<0.01):.3f} <0.002={np.mean(g<0.002):.3f} 中位={np.median(g):.4f}')
g3=gaps([ep3])
print('[D] ep3 每块最近面间距:', {f"{c['color']}_{c['idx']}":round(float(v),4) for c,v in zip(ep3['cubes'],g3)})
deg=np.mean([c['degenerate'] for L in sims for c in L['cubes']])
print(f'[D] V4 已放方块 2D OBB 退化比例 = {deg:.4f}')
