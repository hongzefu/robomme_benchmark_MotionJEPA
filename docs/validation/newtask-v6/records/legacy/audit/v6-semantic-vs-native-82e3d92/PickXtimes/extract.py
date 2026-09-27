"""Read-only extractor for PickXtimes audit (h5py/numpy/cv2/json only)."""
import h5py, json, glob, os, re, sys, numpy as np, cv2
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/PickXtimes'
idx=json.load(open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['PickXtimes']
eps=[dict(kind='new',**e) for e in idx]
for d in sorted(glob.glob(R+'/artifacts/newtask-v6/v1/base/B/PickXtimes_episode_*')):
    h=glob.glob(d+'/hdf5_files/*.h5')[0]; m=sorted(glob.glob(d+'/videos/*.mp4'))
    tier=re.search(r'_(easy|medium|hard)_',os.path.basename(m[0])).group(1)
    eps.append(dict(kind='native',difficulty=tier,episode=int(d.split('_')[-1]),h5=h,mp4=m))
NUM={w:i for i,w in enumerate('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split())}
ORD='first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth'.split()
# OpenCV hue centres
HUES={'red':0,'yellow':30,'green':60,'cyan':90,'blue':120,'magenta':150}
def classify(rgb):
    hsv=cv2.cvtColor(rgb[None,None,:].astype(np.uint8),cv2.COLOR_RGB2HSV)[0,0]
    h,s,v=int(hsv[0]),int(hsv[1]),int(hsv[2])
    if s<150 or v<60: return 'none'
    best=min(HUES,key=lambda k:min(abs(h-HUES[k]),180-abs(h-HUES[k])))
    return best
def cube_masks(img):
    hsv=cv2.cvtColor(img,cv2.COLOR_RGB2HSV)
    H,S,V=hsv[...,0].astype(int),hsv[...,1],hsv[...,2]
    out={}
    for k,c in HUES.items():
        dh=np.minimum(abs(H-c),180-abs(H-c))
        m=((dh<=8)&(S>=170)&(V>=60)).astype(np.uint8)
        n,lab,st,cen=cv2.connectedComponentsWithStats(m)
        blobs=[dict(area=int(st[i,4]),cx=float(cen[i,0]),cy=float(cen[i,1])) for i in range(1,n) if st[i,4]>=12]
        out[k]=blobs
    return out
def patch_color(img,r,c,rad=2):
    r0,r1=max(0,r-rad),min(256,r+rad+1); c0,c1=max(0,c-rad),min(256,c+rad+1)
    votes={}
    for px in img[r0:r1,c0:c1].reshape(-1,3):
        k=classify(px); votes[k]=votes.get(k,0)+1
    return votes
def parse_rc(s):
    m=re.search(r'<(\d+), (\d+)>',s); return (int(m.group(1)),int(m.group(2))) if m else None
recs=[]
for e in eps:
    f=h5py.File(e['h5'],'r'); ep=f[list(f.keys())[0]]; s=ep['setup']
    dec=lambda x: x.decode() if isinstance(x,bytes) else x
    goals=[dec(x) for x in s['task_goal'][()]]
    rec=dict(kind=e['kind'],difficulty=dec(s['difficulty'][()]),index_difficulty=e['difficulty'],episode=e['episode'],seed=int(s['seed'][()]),h5=e['h5'],mp4=e['mp4'],task_goal=goals,
             choices=json.loads(dec(s['available_multi_choices'][()])))
    ts=sorted([int(k.split('_')[1]) for k in ep if k.startswith('timestep_')])
    assert ts==list(range(len(ts)))
    T=len(ts); rec['n_steps']=T
    ss=[dec(ep[f'timestep_{t}/info/simple_subgoal'][()]) for t in ts]
    gs=[dec(ep[f'timestep_{t}/info/grounded_subgoal'][()]) for t in ts]
    ca=[dec(ep[f'timestep_{t}/action/choice_action'][()]) for t in ts]
    bd=np.array([bool(ep[f'timestep_{t}/info/is_subgoal_boundary'][()]) for t in ts])
    vd=np.array([bool(ep[f'timestep_{t}/info/is_video_demo'][()]) for t in ts])
    comp=np.array([bool(ep[f'timestep_{t}/info/is_completed'][()]) for t in ts])
    gc=np.array([bool(ep[f'timestep_{t}/obs/is_gripper_close'][()]) for t in ts])
    eef=np.array([ep[f'timestep_{t}/obs/eef_state'][()] for t in ts])
    rec['n_video_demo_steps']=int(vd.sum()); rec['n_boundary']=int(bd.sum()); rec['completed_first_step']=int(np.argmax(comp)) if comp.any() else None
    # segments by simple_subgoal
    segs=[]; start=0
    for t in range(1,T+1):
        if t==T or ss[t]!=ss[start] or (bd[t] if t<T else False):
            segs.append(dict(start=start,end=t-1,simple=ss[start],grounded=gs[start],grounded_last=gs[t-1],choice_first=ca[start],choice_letters=sorted(set(json.loads(c)['choice'] if c.startswith('{') else c for c in ca[start:t]))))
            start=t
    rec['segments']=segs
    # gripper close rising edges
    edges=[int(t) for t in range(1,T) if gc[t] and not gc[t-1]]
    rec['gripper_close_rising_edges']=edges
    # goal parsing
    g=goals[0]
    m=re.search(r'pick up the (\w+) cube and place it on the target(?:, repeating this action (\w+) times)?',g)
    gcol=m.group(1); gN=NUM[m.group(2)] if m.group(2) else 1
    rec['goal_color']=gcol; rec['goal_N']=gN
    picks=[sg for sg in segs if sg['simple'].startswith('pick up')]
    places=[sg for sg in segs if sg['simple'].startswith('place')]
    buttons=[sg for sg in segs if sg['simple'].startswith('press')]
    rec['n_pick_segments']=len(picks); rec['n_place_segments']=len(places); rec['n_button_segments']=len(buttons)
    rec['pick_ordinals']=[re.search(r'for the (\w+) time',p['simple']).group(1) for p in picks]
    rec['ordinals_ok']=rec['pick_ordinals']==ORD[:len(picks)]
    rec['subgoal_colors']=sorted(set(re.search(r'the (\w+) cube',x['simple']).group(1) for x in picks+places))
    # frame0 blob census
    img0=ep['timestep_0/obs/front_rgb'][()]
    imgL=ep[f'timestep_{T-1}/obs/front_rgb'][()]
    b0=cube_masks(img0); bL=cube_masks(imgL)
    rec['frame0_blobs']={k:[(round(b['cx'],1),round(b['cy'],1),b['area']) for b in v] for k,v in b0.items()}
    rec['last_blobs']={k:[(round(b['cx'],1),round(b['cy'],1),b['area']) for b in v] for k,v in bL.items()}
    # pick coordinate colour check and distance to disk
    checks=[]
    for p in picks:
        rc=parse_rc(p['grounded']); img=ep[f"timestep_{p['start']}/obs/front_rgb"][()]
        checks.append(dict(seg_start=p['start'],rc=rc,votes=patch_color(img,*rc)))
    rec['pick_point_colour']=checks
    place_rc=[parse_rc(p['grounded']) for p in places]
    rec['place_points']=place_rc
    # after each place: next pick point (cube location) distance to disk
    d=[]
    for i,p in enumerate(places):
        nxt=[q for q in picks if q['start']>p['end']]
        if nxt:
            a=parse_rc(nxt[0]['grounded']); b=place_rc[i]
            d.append(dict(place_seg=p['start'],next_pick_rc=a,disk_rc=b,px_dist=round(float(np.hypot(a[0]-b[0],a[1]-b[1])),2)))
    rec['cube_on_disk_after_place']=d
    # final frame: target-colour blob near disk
    disk=place_rc[-1] if place_rc else None
    fb=[bb for bb in bL.get(gcol,[])]
    rec['final_target_blob_to_disk_px']=[round(float(np.hypot(bb['cy']-disk[0],bb['cx']-disk[1])),2) for bb in fb] if disk else None
    # displacement of non-target colour blobs frame0 -> last
    disp={}
    for k in HUES:
        if k==gcol: continue
        for b in b0[k]:
            cand=[np.hypot(b['cx']-c['cx'],b['cy']-c['cy']) for c in bL[k]]
            disp.setdefault(k,[]).append(round(float(min(cand)),2) if cand else None)
    rec['nontarget_blob_disp_px']=disp
    # mp4 frames
    mp=[]
    for mf in e['mp4']:
        cap=cv2.VideoCapture(mf); n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); w=int(cap.get(3)); h=int(cap.get(4)); cap.release()
        fn=os.path.basename(mf)
        mp.append(dict(file=fn,frames=n,w=w,h=h,goal_in_name=fn.split('__ALT__')[0]))
    rec['mp4_info']=mp
    rec['eef_final']=eef[-1].tolist()
    recs.append(rec)
    f.close()
json.dump(recs,open(E+'/records.json','w'),indent=1,ensure_ascii=False)
for r in recs:
    print(r['kind'],r['difficulty'],r['episode'],r['seed'],'N',r['goal_N'],r['goal_color'],'picks',r['n_pick_segments'],'places',r['n_place_segments'],'btn',r['n_button_segments'],'ord',r['ordinals_ok'],'cols',r['subgoal_colors'],'T',r['n_steps'],'demo',r['n_video_demo_steps'],'edges',len(r['gripper_close_rising_edges']),'mp4',[(m['frames']) for m in r['mp4_info']])
