import h5py, json, glob, os, sys, numpy as np
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
idx=json.load(open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['StopCube']
eps=[(e['difficulty'],e['episode'],e['h5'],e['mp4'][0]) for e in idx]
for d in sorted(glob.glob(R+'/artifacts/newtask-v6/v1/base/B/StopCube_episode_*')):
    h=glob.glob(d+'/hdf5_files/*.h5')[0]; m=glob.glob(d+'/videos/*.mp4')
    tier=os.path.basename(m[0]).split('_')[3]
    eps.append((tier,int(d.split('_')[-1]),h,m[0]))
def s(v):
    v=v[()] if hasattr(v,'shape') else v
    return v.decode() if isinstance(v,bytes) else (str(v) if not isinstance(v,np.ndarray) else [x.decode() if isinstance(x,bytes) else x for x in v.tolist()])
out=[]
for tier,ep,h,m in eps:
    f=h5py.File(h,'r'); g=f[list(f.keys())[0]]
    n=len([k for k in g if k.startswith('timestep_')])
    setup=g['setup']
    rec=dict(tier=tier,episode=ep,h5=h,mp4=m,seed=int(setup['seed'][()]),difficulty=s(setup['difficulty']),
             task_goal=s(setup['task_goal']),choices=json.loads(s(setup['available_multi_choices'])),n_steps=n)
    segs=[]; prev=None; demo=0; bounds=[]
    for t in range(n):
        inf=g[f'timestep_{t}/info']
        ss=s(inf['simple_subgoal']); gs=s(inf['grounded_subgoal']); ca=s(g[f'timestep_{t}/action/choice_action'])
        if inf['is_video_demo'][()]: demo+=1
        if inf['is_subgoal_boundary'][()]: bounds.append(t)
        key=(ss,gs,ca)
        if key!=prev:
            segs.append(dict(start=t,simple=ss,grounded=gs,choice=ca)); prev=key
    rec['video_demo_steps']=demo; rec['boundaries']=bounds; rec['segments']=segs
    rec['is_completed_last']=bool(g[f'timestep_{n-1}/info/is_completed'][()])
    rec['front_extrinsic']=g['timestep_0/obs/front_camera_extrinsic'][()].tolist()
    out.append(rec)
json.dump(out,open(R+'/'+sys.argv[1],'w'),indent=1)
for r in out:
    print(r['tier'],r['episode'],r['seed'],r['n_steps'],'demo',r['video_demo_steps'],'completed',r['is_completed_last'])
    print('  goal:',r['task_goal'][0])
    print('  bounds:',r['boundaries'])
    for sg in r['segments']: print('   ',sg['start'],'|',sg['simple'],'|',sg['grounded'],'|',sg['choice'][:120])
