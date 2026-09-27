"""Read-only extractor: new-tier (12) + native (9) ButtonUnmaskSwap HDF5 -> records_raw.json"""
import h5py, json, glob, os, sys, re
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts'
OUT=os.path.dirname(os.path.abspath(__file__))
idx=json.load(open(f'{ROOT}/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['ButtonUnmaskSwap'] if 'ButtonUnmaskSwap' in json.load(open(f'{ROOT}/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json')) else None
items=[dict(tier=e['difficulty'],episode=e['episode'],seed=e['seed'],h5=e['h5'],mp4=e['mp4'][0]) for e in idx]
for d in sorted(glob.glob(f'{ROOT}/newtask-v6/v1/base/B/ButtonUnmaskSwap_episode_*')):
    h5=glob.glob(d+'/hdf5_files/*.h5')[0]; mp4=glob.glob(d+'/videos/*.mp4')[0]
    ep=int(d.rsplit('_',1)[1]); m=re.search(r'_(easy|medium|hard)_',os.path.basename(mp4))
    items.append(dict(tier=m.group(1),episode=ep,seed=None,h5=h5,mp4=mp4,native=True))
def s(x):
    x=x[()]; return x.decode() if isinstance(x,bytes) else x
recs=[]
for it in items:
    f=h5py.File(it['h5'],'r'); ep=f[list(f.keys())[0]]
    names=sorted([k for k in ep if k.startswith('timestep_')],key=lambda k:int(k.split('_')[1]))
    r=dict(it); r['task_goal']=[g.decode() for g in ep['setup/task_goal'][()]]
    r['difficulty_attr']=s(ep['setup/difficulty']); r['seed_attr']=int(ep['setup/seed'][()])
    r['choices']=json.loads(s(ep['setup/available_multi_choices']))
    r['n_steps']=len(names)
    segs=[]; prev=None; demo_steps=0
    for n in names:
        t=ep[n]; ts=int(n.split('_')[1])
        sg=s(t['info/simple_subgoal']); b=bool(t['info/is_subgoal_boundary'][()])
        if bool(t['info/is_video_demo'][()]): demo_steps+=1
        if sg!=prev or b:
            ca=s(t['action/choice_action']) if 'action/choice_action' in t else None
            segs.append(dict(t=ts,subgoal=sg,boundary=b,choice=ca,grounded=s(t['info/grounded_subgoal']),
                              grounded_online=s(t['info/grounded_subgoal_online']),online=s(t['info/simple_subgoal_online'])))
            prev=sg
    r['segments']=segs; r['video_demo_steps']=demo_steps
    r['last_completed']=bool(ep[names[-1]]['info/is_completed'][()])
    r['gripper_close']=[int(ep[n]['obs/is_gripper_close'][()]) for n in names]
    recs.append(r); f.close()
    print(r['tier'],r['episode'],r['seed_attr'],r['n_steps'],r['task_goal'][0])
    for sgm in segs: print('   ',sgm['t'],sgm['boundary'],sgm['subgoal'],'|',sgm['choice'],'|',sgm['grounded'])
for r in recs: del r['gripper_close']
json.dump(recs,open(f'{OUT}/records_raw.json','w'),indent=1)
