# V5b 颜色重抽约束按「最多色块数」分层的通过率 / 重抽次数；以及 link 阈值敏感性
import sys, pickle, numpy as np
D='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
sys.path.insert(0,D)
import analyze_lib as al
rng=np.random.default_rng(3)
simt=[L for L in pickle.load(open(D+'/sim_trueobb.pkl','rb')) if L][:3000]
for link in (0.08,0.09,0.10):
    al.LINK=link
    comps=[]; mx=[]; first=[]; succ={2:[],3:[]}; tries={2:[],3:[]}
    for L in simt:
        P,lab,_=al.arr(L); s=al.stats_for(P,lab)[3][0]; comps.append(s); mx.append(max(L['spawn']))
        perms=np.array([rng.permutation(lab) for _ in range(64)])
        sp=al.stats_for(P,perms)[3]
        for T in (2,3):
            if s<=T: tries[T].append(0); succ[T].append(True); continue
            ok=np.nonzero(sp<=T)[0]
            tries[T].append(int(ok[0])+1 if len(ok) else 64); succ[T].append(len(ok)>0)
    comps=np.array(comps); mx=np.array(mx)
    print(f'link={link}: V5a 位置下 P(comp>=4)={np.mean(comps>=4):.4f} P(comp>=3)={np.mean(comps>=3):.4f}')
    for T in (2,3):
        t=np.array(tries[T]); s=np.array(succ[T])
        line=' '.join(f'max={m}:需重抽{np.mean(t[mx==m]>0):.3f}/K64失败{np.mean(~s[mx==m]):.4f}' for m in sorted(set(mx)) if np.sum(mx==m)>=10)
        print(f'   T={T}: 需重抽比例={np.mean(t>0):.4f} 平均重抽={t.mean():.3f} K=64 失败={np.mean(~s):.4f} | {line}')
