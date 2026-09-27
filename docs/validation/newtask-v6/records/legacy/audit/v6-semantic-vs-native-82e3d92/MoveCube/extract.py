import h5py,json,glob,os,re,numpy as np
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
idx=json.load(open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['MoveCube']
items=[dict(kind='new',difficulty=d['difficulty'],episode=d['episode'],seed=d['seed'],h5=d['h5'],mp4=d['mp4'][0]) for d in idx]
for d in sorted(glob.glob(R+'/artifacts/newtask-v6/v1/base/B/MoveCube_episode_*')):
    h=glob.glob(d+'/hdf5_files/*.h5')[0]; m=glob.glob(d+'/videos/*.mp4')
    items.append(dict(kind='native',episode=int(d.split('_')[-1]),h5=h,mp4=m))
def s(x):
    x=x[()]
    if isinstance(x,bytes): return x.decode()
    if isinstance(x,np.ndarray): return [y.decode() if isinstance(y,bytes) else str(y) for y in x.tolist()]
    return x if not isinstance(x,(np.integer,np.bool_)) else x.item()
recs=[]
for it in items:
    f=h5py.File(it['h5'],'r'); ep=f[list(f.keys())[0]]
    st=ep['setup']; r=dict(it)
    r['setup']={k:s(st[k]) for k in ['difficulty','seed','task_goal','available_multi_choices']}
    ts=sorted([k for k in ep if k.startswith('timestep_')],key=lambda k:int(k.split('_')[1]))
    r['n_steps']=len(ts)
    segs=[];prev=None;choices=[]
    grip=[]
    for i,k in enumerate(ts):
        g=ep[k]; info=g['info']
        row=(s(info['simple_subgoal']),s(info['grounded_subgoal']),bool(info['is_video_demo'][()]),s(info['simple_subgoal_online']),s(info['grounded_subgoal_online']))
        bd=bool(info['is_subgoal_boundary'][()])
        ca=s(g['action/choice_action'])
        if ca not in ('',None,b'') and (not choices or choices[-1]['v']!=ca): choices.append(dict(step=i,v=ca))
        grip.append(bool(g['obs/is_gripper_close'][()]))
        if row!=prev or bd:
            segs.append(dict(step=i,boundary=bd,simple=row[0],grounded=row[1],demo=row[2],simple_online=row[3],grounded_online=row[4],completed=bool(info['is_completed'][()])))
            prev=row
    r['segments']=segs; r['choice_actions']=choices
    r['n_demo']=sum(bool(ep[k]['info/is_video_demo'][()]) for k in ts)
    r['last_completed']=bool(ep[ts[-1]]['info/is_completed'][()])
    r['grip_close_frac_exec']=float(np.mean([grip[i] for i in range(len(ts)) if not ep[ts[i]]['info/is_video_demo'][()]]))
    recs.append(r)
json.dump(recs,open(E+'/raw_extract.json','w'),indent=1,ensure_ascii=False,default=str)
for r in recs:
    print('=====',r['kind'],r.get('difficulty'),r['episode'],r['setup']['difficulty'],r['setup']['seed'],'steps',r['n_steps'],'demo',r['n_demo'],'done',r['last_completed'])
    print(' goal',r['setup']['task_goal']); print(' choices-setup',str(r['setup']['available_multi_choices'])[:300])
    for sg in r['segments']: print('  ',sg['step'],'B' if sg['boundary'] else '-','D' if sg['demo'] else 'E',repr(sg['simple'])[:60],'|',repr(sg['grounded'])[:90],'|on:',repr(sg['simple_online'])[:50])
    print(' choice_actions',r['choice_actions'][:10])
