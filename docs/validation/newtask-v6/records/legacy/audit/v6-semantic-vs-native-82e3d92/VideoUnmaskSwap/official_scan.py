import h5py, re, json, collections
f=h5py.File('/data/hongzefu/robomme_data_h5/record_dataset_VideoUnmaskSwap.h5','r')
def s(x):
    x=x[()]; return x.decode() if isinstance(x,bytes) else x
res=[]
for k in f:
    g=f[k]; st=g['setup']
    diff=s(st['difficulty']) if 'difficulty' in st else None
    goal=[x.decode() if isinstance(x,bytes) else x for x in st['task_goal'][()]] if 'task_goal' in st else None
    ts=sorted(int(t.split('_')[1]) for t in g if t.startswith('timestep_'))
    segs=[];prev=None
    for t in ts:
        gi=g[f'timestep_{t}']
        if 'info/grounded_subgoal' not in gi: continue
        gs=s(gi['info/grounded_subgoal'])
        if gs!=prev: segs.append((t,gs)); prev=gs
    picks=[x for x in segs if x[1].startswith('pick up')]
    nocoord=[x for x in picks if '<' not in x[1]]
    res.append(dict(ep=k,diff=diff,seed=int(s(st['seed'])) if 'seed' in st else None,goal=goal,n_picks=len(picks),nocoord=nocoord))
c=collections.Counter(); cn=collections.Counter()
for r in res:
    c[r['diff']]+=r['n_picks']; cn[r['diff']]+=len(r['nocoord'])
print('picks by diff',c); print('pick subgoals without coordinates by diff',cn)
for r in res:
    if r['nocoord']: print(r['ep'],r['diff'],r['seed'],r['nocoord'])
json.dump(res,open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap/official_hf_scan.json','w'),indent=1)
