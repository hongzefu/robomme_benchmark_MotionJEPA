import h5py, json, glob, os, sys, re
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts'
OUT=ROOT+'/audit/v6-semantic-vs-native-82e3d92/VideoPlaceButton'
idx=json.load(open(ROOT+'/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['VideoPlaceButton']
def dec(x):
    v=x[()]
    if isinstance(v,bytes): return v.decode()
    if hasattr(v,'tolist'): v=v.tolist()
    if isinstance(v,list): return [a.decode() if isinstance(a,bytes) else a for a in v]
    return v
def read(h5):
    f=h5py.File(h5,'r'); ep=list(f.keys())[0]; g=f[ep]
    setup={k:dec(g['setup'][k]) for k in g['setup'] if 'intrinsic' not in k}
    ts=sorted([int(k.split('_')[1]) for k in g if k.startswith('timestep_')])
    segs=[]; prev=None; bounds=[]; choices=[]
    for t in ts:
        info=g[f'timestep_{t}/info']
        s=dec(info['simple_subgoal']); gs=dec(info['grounded_subgoal']); demo=bool(info['is_video_demo'][()])
        so=dec(info['simple_subgoal_online']); go=dec(info['grounded_subgoal_online'])
        if bool(info['is_subgoal_boundary'][()]): bounds.append(t)
        ca=dec(g[f'timestep_{t}/action/choice_action'])
        if ca not in (None,'','None','{}') and (not choices or choices[-1][1]!=ca): choices.append((t,ca))
        key=(s,gs,demo,so,go)
        if key!=prev:
            segs.append({'start':t,'simple':s,'grounded':gs,'simple_online':so,'grounded_online':go,'demo':demo}); prev=key
        segs[-1]['end']=t
    return {'h5':h5,'setup':setup,'n_steps':len(ts),'n_demo':sum(1 for s in segs if s['demo'] for _ in range(s['end']-s['start']+1)),'boundaries':bounds,'segments':segs,'choice_actions':choices}
recs=[]
for it in idx:
    r=read(it['h5']); r.update(difficulty=it['difficulty'],episode=it['episode'],seed=it['seed'],mp4=it['mp4'])
    tr=os.path.join(os.path.dirname(os.path.dirname(it['h5'])),'rng_trace.json')
    r['rng']={c['path']:c['drawn'] for c in json.load(open(tr))['calls']} if os.path.exists(tr) else None
    recs.append(r)
for d in sorted(glob.glob(ROOT+'/newtask-v6/v1/base/B/VideoPlaceButton_episode_*')):
    h5=glob.glob(d+'/hdf5_files/*.h5')[0]; mp4=sorted(glob.glob(d+'/videos/*.mp4'))
    tier=re.search(r'_(easy|medium|hard)_',os.path.basename(mp4[-1])).group(1)
    r=read(h5); r.update(difficulty=tier,episode=int(d.split('_')[-1]),mp4=mp4,rng=None); recs.append(r)
json.dump(recs,open(OUT+'/raw_extract.json','w'),indent=1,default=str)
print(len(recs))
