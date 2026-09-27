"""Read-only extractor: VPO HDF5 -> per-episode facts (segments, texts, choices)."""
import h5py, json, glob, os, re, sys
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
IDX=json.load(open(f'{ROOT}/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['VideoPlaceOrder']
eps=[]
for e in IDX:
    eps.append(dict(tier=e['difficulty'],episode=e['episode'],seed=e['seed'],h5=e['h5'],mp4=[m for m in e['mp4'] if not os.path.basename(m).startswith('success')][0]))
for d in sorted(glob.glob(f'{ROOT}/artifacts/newtask-v6/v1/base/B/VideoPlaceOrder_episode_*')):
    h5=glob.glob(d+'/hdf5_files/*.h5')[0]; mp4=[m for m in glob.glob(d+'/videos/*.mp4') if not os.path.basename(m).startswith('success')][0]
    tier=re.search(r'_(easy|medium|hard)_watch',os.path.basename(mp4)).group(1)
    eps.append(dict(tier=tier,episode=int(d.rsplit('_',1)[1]),seed=None,h5=h5,mp4=mp4))
def s(x):
    x=x[()] if hasattr(x,'shape') else x
    return x.decode() if isinstance(x,bytes) else (str(x) if not isinstance(x,(bool,int,float)) else x)
out=[]
for ep in eps:
    f=h5py.File(ep['h5'],'r'); g=f[[k for k in f.keys() if k.startswith('episode_')][0]]
    setup={k:(s(g['setup'][k]) if g['setup'][k].shape==() else [s(v) for v in g['setup'][k][()]]) for k in ['difficulty','seed','task_goal','available_multi_choices']}
    ts=sorted([int(k.split('_')[1]) for k in g if k.startswith('timestep_')])
    rows=[]
    for t in ts:
        gi=g[f'timestep_{t}/info']
        rows.append(dict(t=t,simple=s(gi['simple_subgoal']),grounded=s(gi['grounded_subgoal']),
            simple_on=s(gi['simple_subgoal_online']),grounded_on=s(gi['grounded_subgoal_online']),
            boundary=bool(gi['is_subgoal_boundary'][()]),demo=bool(gi['is_video_demo'][()]),done=bool(gi['is_completed'][()]),
            choice=s(g[f'timestep_{t}/action/choice_action'])))
    # segments by grounded_subgoal change
    segs=[]
    for r in rows:
        key=(r['simple'],r['grounded'],r['demo'])
        if not segs or segs[-1]['key']!=key:
            segs.append(dict(key=key,start=r['t'],end=r['t'],simple=r['simple'],grounded=r['grounded'],demo=r['demo']))
        else: segs[-1]['end']=r['t']
    for sg in segs: del sg['key']
    bounds=[r['t'] for r in rows if r['boundary']]
    choices=sorted({r['choice'] for r in rows if r['choice'] not in ('None','','{}')})
    online=[]
    for r in rows:
        k=(r['simple_on'],r['grounded_on'])
        if not online or online[-1]['key']!=k: online.append(dict(key=k,start=r['t'],text=r['grounded_on']))
    for o in online: del o['key']
    ep.update(setup=setup,n_steps=len(ts),first_nondemo=next((r['t'] for r in rows if not r['demo']),None),
              segments=segs,boundaries=bounds,choices=choices,online_segments=online,last_done=rows[-1]['done'])
    out.append(ep)
    print(ep['tier'],ep['episode'],setup['task_goal'][0],'steps',len(ts))
json.dump(out,open(f'{ROOT}/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceOrder/raw_extract.json','w'),indent=1,default=str)
