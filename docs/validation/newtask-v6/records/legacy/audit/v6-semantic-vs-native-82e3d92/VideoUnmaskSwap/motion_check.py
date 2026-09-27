import h5py, json, numpy as np, re, os
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
recs=json.load(open(E+'/raw_extract.json'))
specs={}
for t in ['xhard1','xhard2','xhard3','xhard4']:
    for line in open(f'{ROOT}/artifacts/newtask-v6/v6-01/{t}/specs.jsonl'):
        d=json.loads(line)
        if d.get('task')=='VideoUnmaskSwap' and d.get('record')=='spec': specs[(t,d['seed'])]=d['spec']
out=[]
for r in recs:
    # filename vs goal
    fn=[m for m in r['mp4'] if 'NO_OBJECT' not in os.path.basename(m)][0]
    base=os.path.basename(fn)[:-4]
    goal_slug=re.sub(r'[^a-z0-9]+','_',r['task_goal'][0].lower()).strip('_')
    fn_ok=base.endswith(goal_slug) and (('_'+r['tier']+'_') in base)
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    T=r['demo_last_step']
    ims=np.stack([g[f'timestep_{t}']['obs/front_rgb'][()].astype(np.int16) for t in range(0,T+1)])
    d=np.abs(np.diff(ims,axis=0)).mean(axis=(1,2,3))  # d[t] = |f[t+1]-f[t]|
    sp=specs.get((r['tier'],r['seed']))
    if sp:
        n=sp['objects']['n_swaps']; L=sp['actions']['swap_window']['duration_steps']
    else:
        n=None; L=50
    res=dict(tier=r['tier'],seed=r['seed'],filename_goal_match=fn_ok,demo_last=T)
    if n:
        wins=[(64+L*k,64+L*(k+1)) for k in range(n)]
        res['window_motion']=[round(float(d[a:b-1].mean()),3) for a,b in wins]
        res['post_last_end_motion']=round(float(d[64+L*n:T].mean()),4) if T>64+L*n else None
    else:
        # native: infer active windows from motion
        act=(d>0.05)
        res['active_steps_after64']=[int(t) for t in np.where(act)[0] if t>=60]
        runs=[];s=None
        for t in range(60,len(d)):
            if act[t] and s is None: s=t
            if not act[t] and s is not None: runs.append((s,t)); s=None
        if s is not None: runs.append((s,len(d)))
        res['motion_runs']=runs; del res['active_steps_after64']
    res['pre64_motion_32']=round(float(d[31]),3)
    res['quiet_33_63']=round(float(d[33:63].mean()),4)
    out.append(res); print(res)
json.dump(out,open(E+'/motion_check.json','w'),indent=1)
