"""Read-only extraction of SwingXtimes HDF5 facts (h5py/numpy/cv2/json only)."""
import h5py, json, re, glob, os, numpy as np, cv2
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
OUT=os.path.join(ROOT,'artifacts/audit/v6-semantic-vs-native-82e3d92/SwingXtimes')
idx=json.load(open(os.path.join(ROOT,'artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json')))['SwingXtimes']
eps=[dict(tier=e['difficulty'],episode=e['episode'],seed=e['seed'],h5=e['h5'],mp4=e['mp4']) for e in idx]
for d in sorted(glob.glob(ROOT+'/artifacts/newtask-v6/v1/base/B/SwingXtimes_episode_*')):
    h=glob.glob(d+'/hdf5_files/*.h5')[0]; mp=sorted(glob.glob(d+'/videos/*.mp4'))
    eps.append(dict(tier=None,episode=int(d.rsplit('_',1)[1]),seed=None,h5=h,mp4=mp))
def s(x):
    x=x[()] if hasattr(x,'shape') else x
    return x.decode() if isinstance(x,bytes) else (str(x) if not isinstance(x,np.ndarray) else [v.decode() if isinstance(v,bytes) else v for v in x.tolist()])
# HSV masks for pure-colored cubes
COL={'red':((0,0),(170,180)),'green':((50,70),),'blue':((110,130),),'yellow':((25,35),),'cyan':((85,95),),'magenta':((145,155),)}
def blobs(rgb):
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV); out={}
    for c,rngs in COL.items():
        m=np.zeros(rgb.shape[:2],np.uint8)
        for r in rngs:
            lo,hi=(r if len(r)==2 else (r[0],r[0]))
            m|=cv2.inRange(hsv,(lo,150,70),(hi,255,255))
        n,lab,st,cen=cv2.connectedComponentsWithStats(m)
        out[c]=[dict(area=int(st[i,4]),cx=float(cen[i,0]),cy=float(cen[i,1])) for i in range(1,n) if st[i,4]>=12]
    return out
recs=[]
for e in eps:
    f=h5py.File(e['h5'],'r'); g=f[list(f.keys())[0]]; st=g['setup']
    ts=sorted([k for k in g.keys() if k.startswith('timestep_')],key=lambda k:int(k.split('_')[1]))
    rec=dict(e); rec['difficulty']=s(st['difficulty']); rec['seed_h5']=int(st['seed'][()])
    rec['task_goal']=s(st['task_goal']); rec['available_multi_choices']=s(st['available_multi_choices'])
    rec['n_frames']=len(ts)
    segs=[]; prev=None; bounds=[]; choices=[]; demo=0; comp=[]
    eefz=[]; grip=[]
    for i,k in enumerate(ts):
        inf=g[k]['info']; ss=s(inf['simple_subgoal']); gs=s(inf['grounded_subgoal'])
        sso=s(inf['simple_subgoal_online']); gso=s(inf['grounded_subgoal_online'])
        if bool(inf['is_subgoal_boundary'][()]): bounds.append(i)
        if bool(inf['is_video_demo'][()]): demo+=1
        if bool(inf['is_completed'][()]): comp.append(i)
        ca=s(g[k]['action']['choice_action'])
        if ca and ca not in ('None','',None) and (not choices or choices[-1][1]!=ca): choices.append((i,ca))
        if ss!=prev: segs.append(dict(frame=i,simple=ss,grounded=gs,simple_online=sso,grounded_online=gso)); prev=ss
        eefz.append(float(g[k]['obs']['eef_state'][2])); grip.append(bool(g[k]['obs']['is_gripper_close'][()]))
    rec['segments']=segs; rec['boundaries']=bounds; rec['n_demo']=demo; rec['completed_frames']=comp[:3]+(['...',comp[-1]] if len(comp)>3 else [])
    rec['choice_changes']=choices[:60]
    names=[x['simple'] for x in segs]
    rec['right_count']=sum('right-side' in n for n in names); rec['left_count']=sum('left-side' in n for n in names)
    m=re.search(r'motion (\w+) times',rec['task_goal'][0]); rec['goal_word']=m.group(1) if m else None
    col=re.search(r'pick up the (\w+) cube',rec['task_goal'][0]).group(1); rec['goal_color']=col
    # visual: frame0 blobs, and target-cube centroid at each swing-segment end
    rgb0=g[ts[0]]['obs']['front_rgb'][()]
    b0=blobs(rgb0); rec['frame0_blobs']={c:v for c,v in b0.items() if v}
    rec['frame_last_blobs']={c:v for c,v in blobs(g[ts[-1]]['obs']['front_rgb'][()]).items() if v}
    checks=[]
    for j,sg in enumerate(segs):
        mm=re.search(r'<(\d+), (\d+)>',sg['grounded'] or '')
        if not mm or 'target' not in sg['simple']: continue
        end=(segs[j+1]['frame']-1) if j+1<len(segs) else len(ts)-1
        rgb=g[ts[end]]['obs']['front_rgb'][()]
        bl=blobs(rgb)[col]
        tx,ty=int(mm.group(1)),int(mm.group(2))
        # grounded coords are <row?, col?>: record both
        best=max(bl,key=lambda b:b['area']) if bl else None
        checks.append(dict(seg=sg['simple'],end_frame=end,grounded=[tx,ty],cube_blob=best,eef_z=eefz[end],grip=grip[end]))
    rec['swing_visual']=checks
    rec['eef_z_last']=eefz[-1]; rec['grip_last']=grip[-1]
    recs.append(rec); f.close()
json.dump(recs,open(os.path.join(OUT,'raw_extract.json'),'w'),indent=1,default=str)
for r in recs:
    print(r['tier'],r['difficulty'],r['episode'],r['n_frames'],r['goal_color'],r['goal_word'],'R',r['right_count'],'L',r['left_count'],'demo',r['n_demo'],{c:len(v) for c,v in r['frame0_blobs'].items()})
