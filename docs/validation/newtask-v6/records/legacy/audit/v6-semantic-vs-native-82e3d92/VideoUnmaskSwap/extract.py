import h5py, json, glob, os, re, sys
import numpy as np
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=ROOT+'/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
idx=json.load(open(ROOT+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['VideoUnmaskSwap']
eps=[]
for it in idx: eps.append(dict(tier=it['difficulty'],episode=it['episode'],seed=it['seed'],h5=it['h5'],mp4=it['mp4']))
B=ROOT+'/artifacts/newtask-v6/v1/base/B'
for d in sorted(glob.glob(B+'/VideoUnmaskSwap_episode_*')):
    h=glob.glob(d+'/hdf5_files/*.h5')[0]; m=glob.glob(d+'/videos/*.mp4')
    tier=re.search(r'_(easy|medium|hard)_',os.path.basename(m[0])).group(1)
    ep=int(d.rsplit('_',1)[1]); seed=int(re.search(r'seed(\d+)',h).group(1))
    eps.append(dict(tier=tier,episode=ep,seed=seed,h5=h,mp4=m))
def s(x):
    x=x[()]
    return x.decode() if isinstance(x,bytes) else x
out=[]
for e in eps:
    f=h5py.File(e['h5'],'r'); g=f[list(f.keys())[0]]
    st=g['setup']
    ts=sorted(int(k.split('_')[1]) for k in g if k.startswith('timestep_'))
    rec=dict(e); rec['difficulty_attr']=s(st['difficulty']); rec['task_goal']=[x.decode() for x in st['task_goal'][()]]
    rec['choices']=json.loads(s(st['available_multi_choices']))
    rec['n_steps']=len(ts); rec['ts_min']=ts[0]; rec['ts_max']=ts[-1]
    segs=[]; prev=None; demo_end=None; boundaries=[]; choice_steps=[]
    for t in ts:
        gi=g[f'timestep_{t}']
        ss=s(gi['info/simple_subgoal']); gs=s(gi['info/grounded_subgoal'])
        demo=bool(gi['info/is_video_demo'][()])
        if demo: demo_end=t
        if bool(gi['info/is_subgoal_boundary'][()]): boundaries.append(t)
        ca=json.loads(s(gi['action/choice_action']))
        if ca.get('choice'): choice_steps.append((t,ca))
        key=(ss,gs)
        if key!=prev:
            segs.append(dict(start=t,simple=ss,grounded=gs,simple_online=s(gi['info/simple_subgoal_online']),grounded_online=s(gi['info/grounded_subgoal_online']),demo=demo))
            prev=key
        segs[-1]['end']=t
    rec['segments']=segs; rec['demo_last_step']=demo_end; rec['boundaries']=boundaries
    # compress choice actions into unique runs
    runs=[];pc=None
    for t,ca in choice_steps:
        k=json.dumps(ca,sort_keys=True)
        if k!=pc: runs.append(dict(start=t,choice=ca)); pc=k
        runs[-1]['end']=t
    rec['choice_runs']=runs
    rec['completed_last']=bool(g[f'timestep_{ts[-1]}']['info/is_completed'][()])
    rec['gripper_close_runs']=[]
    pcl=None
    for t in ts:
        c=bool(g[f'timestep_{t}']['obs/is_gripper_close'][()])
        if c!=pcl: rec['gripper_close_runs'].append([t,c]); pcl=c
    out.append(rec)
json.dump(out,open(E+'/raw_extract.json','w'),indent=1)
for r in out:
    print('==',r['tier'],r['episode'],r['seed'],r['n_steps'],'demo_end',r['demo_last_step'],'completed',r['completed_last'])
    print('  goal:',r['task_goal'])
    for sg in r['segments']: print('   ',sg['start'],sg['end'],'demo' if sg['demo'] else '',sg['simple'],'|',sg['grounded'], '|online:',sg['grounded_online'])
    print('  choices', [(c['start'],c['end'],c['choice']) for c in r['choice_runs']])
    print('  grip', r['gripper_close_runs'])
