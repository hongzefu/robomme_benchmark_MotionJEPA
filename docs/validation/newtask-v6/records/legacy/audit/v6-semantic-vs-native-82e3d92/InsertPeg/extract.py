import h5py, json, sys, glob, os, numpy as np
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
idx=json.load(open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['InsertPeg']
files=[(d['difficulty'],d['episode'],d['h5'],d['mp4'][0]) for d in idx]
for ep in sorted(glob.glob(R+'/artifacts/newtask-v6/v1/base/B/InsertPeg_episode_*')):
    h=glob.glob(ep+'/hdf5_files/*.h5')[0]; m=glob.glob(ep+'/videos/*.mp4')[0]
    diff=os.path.basename(m).split('_')[3]
    files.append((diff,int(ep.split('_')[-1]),h,m))
def s(x):
    x=x[()]
    return x.decode() if isinstance(x,bytes) else (x.item() if hasattr(x,'item') else x)
out=[]
for diff,epn,h,m in files:
    f=h5py.File(h,'r'); g=f[list(f.keys())[0]]
    su=g['setup']
    ts=sorted([k for k in g if k.startswith('timestep_')],key=lambda k:int(k.split('_')[1]))
    rec=dict(difficulty=diff,episode=epn,h5=h,mp4=m,seed=int(s(su['seed'])),setup_difficulty=s(su['difficulty']),
             task_goal=[x.decode() if isinstance(x,bytes) else str(x) for x in su['task_goal'][()]],
             available_multi_choices=str(s(su['available_multi_choices'])),n_steps=len(ts))
    segs=[]; prev=None; choices=[]; demo_end=None
    grip=[]
    for i,k in enumerate(ts):
        info=g[k]['info']
        ss=s(info['simple_subgoal']); gs=s(info['grounded_subgoal']); dm=bool(s(info['is_video_demo'])); b=bool(s(info['is_subgoal_boundary']))
        ca=s(g[k]['action']['choice_action'])
        if ca not in (None,'','None') and (not choices or choices[-1][1]!=str(ca)): choices.append((i,str(ca)))
        key=(ss,gs,dm)
        if key!=prev: segs.append(dict(start=i,simple=ss,grounded=gs,demo=dm)); prev=key
        if b: segs[-1].setdefault('boundaries',[]).append(i)
        grip.append(bool(s(g[k]['obs']['is_gripper_close'])))
        if dm: demo_end=i
    for a,bb in zip(segs,segs[1:]+[None]): a['end']=(bb['start']-1) if bb else len(ts)-1
    rec['segments']=segs; rec['choices']=choices[:40]; rec['last_demo_step']=demo_end
    rec['is_completed_last']=bool(s(g[ts[-1]]['info']['is_completed']))
    # gripper close intervals
    iv=[];st=None
    for i,c in enumerate(grip):
        if c and st is None: st=i
        if not c and st is not None: iv.append([st,i-1]); st=None
    if st is not None: iv.append([st,len(grip)-1])
    rec['gripper_closed_intervals']=iv
    out.append(rec)
json.dump(out,open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/InsertPeg/extract_raw.json','w'),indent=1)
for r in out:
    print('=====',r['difficulty'],r['episode'],r['seed'],r['setup_difficulty'],r['n_steps'],'lastdemo',r['last_demo_step'],'completed',r['is_completed_last'])
    print(' goal',r['task_goal']); print(' choices-avail',r['available_multi_choices'][:300])
    for sg in r['segments']: print('  ',sg['start'],sg['end'],sg['demo'],repr(sg['simple']),'|',repr(sg['grounded']),sg.get('boundaries'))
    print('  choice_actions',r['choices'][:12]); print('  grip',r['gripper_closed_intervals'])
