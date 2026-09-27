import h5py, json, glob, os, re, numpy as np
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
OUT=f'{ROOT}/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmask'
idx=json.load(open(f'{ROOT}/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['VideoUnmask']
eps=[dict(tier=e['difficulty'],episode=e['episode'],seed=e['seed'],h5=e['h5'],mp4=e['mp4']) for e in idx]
for d in sorted(glob.glob(f'{ROOT}/artifacts/newtask-v6/v1/base/B/VideoUnmask_episode_*')):
    h5=glob.glob(d+'/hdf5_files/*.h5')[0]; mp4=sorted(glob.glob(d+'/videos/*.mp4'))
    t=re.search(r'_(easy|medium|hard)_',os.path.basename(mp4[0])).group(1)
    eps.append(dict(tier=t,episode=int(d.split('_')[-1]),seed=int(re.search(r'seed(\d+)',h5).group(1)),h5=h5,mp4=mp4))
def s(x):
    x=x[()]
    if isinstance(x,bytes): return x.decode()
    if isinstance(x,np.ndarray): return [y.decode() if isinstance(y,bytes) else str(y) for y in x.tolist()]
    return x if not isinstance(x,np.generic) else x.item()
recs=[]
for e in eps:
    f=h5py.File(e['h5'],'r'); g=f[[k for k in f.keys() if k.startswith('episode_')][0]]
    setup={k:s(g['setup'][k]) for k in ['available_multi_choices','difficulty','seed','task_goal']}
    ts=sorted([k for k in g if k.startswith('timestep_')],key=lambda k:int(k.split('_')[1]))
    rows=[]
    for k in ts:
        t=g[k]; i=t['info']
        rows.append(dict(t=int(k.split('_')[1]),simple=s(i['simple_subgoal']),grounded=s(i['grounded_subgoal']),
            simple_on=s(i['simple_subgoal_online']),grounded_on=s(i['grounded_subgoal_online']),
            boundary=bool(i['is_subgoal_boundary'][()]),demo=bool(i['is_video_demo'][()]),done=bool(i['is_completed'][()]),
            choice=s(t['action']['choice_action']),grip=bool(t['obs']['is_gripper_close'][()]),eef=[float(v) for v in t['obs']['eef_state'][()]]))
    segs=[]
    for r in rows:
        if not segs or segs[-1]['simple']!=r['simple'] or segs[-1]['grounded']!=r['grounded']:
            segs.append(dict(simple=r['simple'],grounded=r['grounded'],start=r['t'],end=r['t']))
        else: segs[-1]['end']=r['t']
    choices=[]
    for r in rows:
        if r['choice'] not in (None,'','None') and (not choices or choices[-1]['choice']!=r['choice']):
            choices.append(dict(t=r['t'],choice=r['choice']))
    e.update(setup=setup,n_steps=len(rows),segments=segs,boundaries=[r['t'] for r in rows if r['boundary']],
        demo_steps=[min([r['t'] for r in rows if r['demo']],default=None),max([r['t'] for r in rows if r['demo']],default=None),sum(r['demo'] for r in rows)],
        completed_first=next((r['t'] for r in rows if r['done']),None),choice_changes=choices,
        online_segments=None)
    osegs=[]
    for r in rows:
        if not osegs or osegs[-1]['simple_on']!=r['simple_on']:
            osegs.append(dict(simple_on=r['simple_on'],grounded_on=r['grounded_on'],start=r['t'],end=r['t']))
        else: osegs[-1]['end']=r['t']
    e['online_segments']=osegs
    grip=[r['grip'] for r in rows]
    e['grip_close_runs']=[]
    for r in rows:
        if r['grip'] and (not e['grip_close_runs'] or e['grip_close_runs'][-1][1]!=r['t']-1): e['grip_close_runs'].append([r['t'],r['t']])
        elif r['grip']: e['grip_close_runs'][-1][1]=r['t']
    recs.append(e)
json.dump(recs,open(f'{OUT}/raw_extract.json','w'),indent=1,ensure_ascii=False)
for e in recs:
    print('====',e['tier'],e['episode'],e['seed'],e['setup']['difficulty'],e['n_steps'],'demo',e['demo_steps'])
    print(' goal',e['setup']['task_goal']); print(' choices',e['setup']['available_multi_choices'])
    for sg in e['segments']: print('  seg',sg['start'],sg['end'],'|',sg['simple'],'|',sg['grounded'])
    print(' bnd',e['boundaries'],' grip',e['grip_close_runs'],' done@',e['completed_first'])
    print(' choice',e['choice_changes'][:12])
