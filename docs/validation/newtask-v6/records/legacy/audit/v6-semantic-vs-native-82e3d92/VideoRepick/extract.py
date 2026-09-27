import h5py, json, glob, os, re, numpy as np
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoRepick'
idx=json.load(open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['VideoRepick']
items=[]
for x in idx:
    items.append(dict(kind='new',difficulty=x['difficulty'],episode=x['episode'],seed=x['seed'],h5=x['h5'],mp4=x['mp4']))
for d in sorted(glob.glob(R+'/artifacts/newtask-v6/v1/base/B/VideoRepick_episode_*')):
    h5=glob.glob(d+'/hdf5_files/*.h5')[0]; mp4=sorted(glob.glob(d+'/videos/*.mp4'))
    items.append(dict(kind='native',episode=int(d.rsplit('_',1)[1]),h5=h5,mp4=mp4))
def s(v):
    v=v[()] if hasattr(v,'shape') else v
    if isinstance(v,bytes): return v.decode()
    if isinstance(v,np.ndarray): return [s(a) for a in v.tolist()]
    return v
out=[]
for it in items:
    f=h5py.File(it['h5'],'r'); g=f[list(f.keys())[0]]; st=g['setup']
    setup={k:s(st[k]) for k in st.keys() if st[k].shape==() or st[k].dtype==object}
    setup={k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in setup.items()}
    n=len([k for k in g.keys() if k.startswith('timestep_')])
    rows=[]
    for t in range(n):
        ts=g[f'timestep_{t}']
        rows.append(dict(t=t,ss=s(ts['info/simple_subgoal']),gs=s(ts['info/grounded_subgoal']),sso=s(ts['info/simple_subgoal_online']),gso=s(ts['info/grounded_subgoal_online']),
            b=bool(ts['info/is_subgoal_boundary'][()]),demo=bool(ts['info/is_video_demo'][()]),done=bool(ts['info/is_completed'][()]),
            ch=s(ts['action/choice_action']),grip=bool(ts['obs/is_gripper_close'][()]),eef=[round(float(a),4) for a in ts['obs/eef_state'][()][:3]]))
    # segments by simple_subgoal
    segs=[]
    for r in rows:
        key=(r['ss'],r['demo'])
        if not segs or segs[-1]['key']!=key: segs.append(dict(key=key,ss=r['ss'],gs=r['gs'],demo=r['demo'],start=r['t'],end=r['t'],choice=set()))
        segs[-1]['end']=r['t']; 
        if r['ch'] not in (None,'','None'): segs[-1]['choice'].add(str(r['ch'])[:200])
    for sg in segs: sg['choice']=sorted(sg['choice']); del sg['key']
    bounds=[r['t'] for r in rows if r['b']]
    # online subgoal segments
    osegs=[]
    for r in rows:
        if not osegs or osegs[-1]['sso']!=r['sso']: osegs.append(dict(sso=r['sso'],start=r['t'],end=r['t']))
        osegs[-1]['end']=r['t']
    # gripper close intervals
    gi=[];cur=None
    for r in rows:
        if r['grip'] and cur is None: cur=r['t']
        if not r['grip'] and cur is not None: gi.append([cur,r['t']-1]); cur=None
    if cur is not None: gi.append([cur,n-1])
    rec=dict(it, n_steps=n, setup=setup, segments=segs, boundaries=bounds, online_segments=osegs, gripper_closed_intervals=gi,
             demo_steps=sum(r['demo'] for r in rows), completed_last=rows[-1]['done'])
    spec=None
    if it['kind']=='new':
        sp=os.path.dirname(os.path.dirname(it['h5']))
        tierdir=R+'/artifacts/newtask-v6/v6-01/'+it['difficulty']
        for l in open(tierdir+'/specs.jsonl'):
            d=json.loads(l)
            if d.get('task')=='VideoRepick' and d.get('episode')==it['episode'] and d.get('seed')==it['seed'] and d.get('record')=='spec':
                spec=d['spec']
        rec['spec']=spec
    out.append(rec)
    json.dump(rows,open(E+f"/rows_{it['kind']}_{it.get('difficulty','nat')}_ep{it['episode']}.json",'w'))
json.dump(out,open(E+'/records_raw.json','w'),indent=1,default=str)
for r in out:
    print('=====',r['kind'],r.get('difficulty'),r['episode'],'n',r['n_steps'],'demo',r['demo_steps'],'done',r['completed_last'])
    print(' setup',{k:v for k,v in r['setup'].items() if 'intrinsic' not in k})
    if r.get('spec'): o=r['spec']['objects']; print(' spec target',o['target'],'nrep',o['num_repeats'],'nswap',o['n_swaps'],'plan',o['swap_plan'],'pairs',[ (v['initiator'],v['partner']) for v in r['spec']['actions']['swap_pairs'].values()])
    for sg in r['segments']: print('  ',sg['start'],sg['end'],'demo' if sg['demo'] else 'exec',repr(sg['ss']),'|',repr(sg['gs']),sg['choice'])
    print(' bounds',r['boundaries']); print(' grip',r['gripper_closed_intervals'])
