import h5py, json, os, numpy as np, cv2
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/InsertPeg'
raw=json.load(open(E+'/extract_raw.json'))
AGENT_X=-0.615; L=0.05
def spec_for(h5):
    ep=os.path.dirname(os.path.dirname(h5)); p=ep+'/rng_trace.json'
    if not os.path.exists(p): return None
    calls={c['path']:c['drawn'] for c in json.load(open(p))['calls']}
    inits=sorted({int(k.split('.')[1]) for k in calls if k.startswith('initializations.')})
    out={'head_rgb':calls['objects.head_rgb'],'random_peg_idx':calls['objects.sampling_trace.random_peg_idx'],'inits':{}}
    for i in inits:
        pre=f'initializations.{i}.'
        pegs=[calls[pre+f'pegs.{k}'] for k in range(8) if pre+f'pegs.{k}' in calls]
        out['inits'][i]=dict(box_xy=calls[pre+'box_jitter'],box_yaw=calls[pre+'box_yaw'],pegs=pegs,obj_sample=calls[pre+'obj_sample'],dir_sample=calls[pre+'dir_sample'],
                             min_pair_gap=calls.get(pre+'min_pair_gap_m'),min_box_gap=calls.get(pre+'min_box_gap_m'))
    return out
def S(x):
    x=x[()]; return x.decode() if isinstance(x,bytes) else x
records=[]
for r in raw:
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    K=g['setup/front_camera_intrinsic'][()]
    def T(t): return g[f'timestep_{t}']
    Ex=T(0)['obs/front_camera_extrinsic'][()]
    def proj(p):
        pc=Ex@np.r_[p,1]; uv=K@pc; return (float(uv[0]/uv[2]),float(uv[1]/uv[2]))
    segs=r['segments']; demo=[s for s in segs if s['demo']]; ex=[s for s in segs if not s['demo']]
    gi=r['gripper_closed_intervals']
    demo_close=gi[0][0]; exec_close=gi[1][0]
    wp=lambda t: np.asarray(T(t)['action/waypoint_action'][()],float)
    eef=lambda t: np.asarray(T(t)['obs/eef_state'][()],float)
    last_demo=r['last_demo_step']; last=r['n_steps']-1
    exec_start=ex[0]['start']
    rec=dict(difficulty=r['difficulty'],episode=r['episode'],seed=r['seed'],h5=r['h5'],mp4=r['mp4'],n_steps=r['n_steps'],
             task_goal=r['task_goal'],segments=[{k:s[k] for k in ('start','end','demo','simple','grounded')} for s in segs],
             gripper_closed_intervals=gi,demo_close_step=demo_close,exec_close_step=exec_close,last_demo_step=last_demo,exec_start_step=exec_start,
             grasp_wp_demo=wp(demo_close)[:3].round(4).tolist(),grasp_wp_exec=wp(exec_close)[:3].round(4).tolist(),
             final_eef_demo=eef(last_demo)[:3].round(4).tolist(),final_eef_exec=eef(last)[:3].round(4).tolist(),
             eef_reset_exec_start=eef(exec_start)[:3].round(4).tolist(),eef_step0=eef(0)[:3].round(4).tolist())
    rec['grasp_demo_vs_exec_dist_m']=float(np.linalg.norm(wp(demo_close)[:2]-wp(exec_close)[:2]))
    rec['final_demo_vs_exec_dist_m']=float(np.linalg.norm(eef(last_demo)[:3]-eef(last)[:3]))
    # frame diff step0 vs exec_start (pegs reset?) excluding robot: compare lower half table region
    f0=T(0)['obs/front_rgb'][()].astype(int); fe=T(exec_start)['obs/front_rgb'][()].astype(int)
    rec['frame0_vs_exec_start_meanabs']=float(np.abs(f0-fe).mean()); rec['frame0_vs_exec_start_frac_px_gt30']=float((np.abs(f0-fe).max(-1)>30).mean())
    sp=spec_for(r['h5'])
    ann=[]
    if sp:
        used=max(sp['inits']); it=sp['inits'][used]
        rec['spec']=dict(head_rgb=sp['head_rgb'],tail_rgb=[1-c for c in sp['head_rgb']],init_index_used=used,n_inits=len(sp['inits']),**it)
        obj_flag=-1 if it['obj_sample']==0 else 1; direction=-1 if it['dir_sample']==0 else 1
        pegs=[]
        for k,(xy,yaw) in enumerate(it['pegs']):
            root=np.array(xy); u=np.array([np.cos(yaw),np.sin(yaw)])
            head=root; tail=root-L*u
            pegs.append(dict(k=k,head=head.round(4).tolist(),tail=tail.round(4).tolist(),yaw_deg=round(float(np.degrees(yaw)),1),
                             head_uv=proj(np.r_[head,0.01]),tail_uv=proj(np.r_[tail,0.01])))
        rec['pegs']=pegs
        gd=wp(demo_close)[:2]; ge=wp(exec_close)[:2]
        cand=[(float(np.linalg.norm(np.array(p[e])-gd)),p['k'],e) for p in pegs for e in ('head','tail')]
        cand.sort(); rec['demo_grasp_nearest']=cand[:2]
        cand2=sorted([(float(np.linalg.norm(np.array(p[e])-ge)),p['k'],e) for p in pegs for e in ('head','tail')]); rec['exec_grasp_nearest']=cand2[:2]
        exp_end='head' if obj_flag==-1 else 'tail'
        rec['expected']=dict(target_peg=0,grasp_end=exp_end,insert_way='left' if direction==-1 else 'right',obj_flag=obj_flag,direction=direction)
        p0=pegs[0]; hx=abs(p0['head'][0]-AGENT_X); tx=abs(p0['tail'][0]-AGENT_X)
        near_x='head' if hx<=tx else 'tail'
        hd=np.hypot(p0['head'][0]-AGENT_X,p0['head'][1]); td=np.hypot(p0['tail'][0]-AGENT_X,p0['tail'][1])
        rec['near_far_xaxis']='near' if exp_end==near_x else 'far'
        rec['near_far_euclid']='near' if ((hd<=td)==(exp_end=='head')) else 'far'
        box=np.array(it['box_xy'])
        rec['exec_side_indicator_y']=float(eef(last)[1]-box[1]); rec['demo_side_indicator_y']=float(eef(last_demo)[1]-box[1])
        rec['side_ok_exec']=bool(rec['exec_side_indicator_y']*direction<0); rec['side_ok_demo']=bool(rec['demo_side_indicator_y']*direction<0)
        rec['box_uv']=proj(np.r_[box,0.04])
        # pixel colors at head/tail projections step0
        img=T(0)['obs/front_rgb'][()]
        for p in pegs:
            for e in ('head','tail'):
                u,v=p[e+'_uv']; u=int(round(u)); v=int(round(v))
                if 0<=u<256 and 0<=v<256:
                    p[e+'_px_rgb_step0']=img[max(0,v-1):v+2,max(0,u-1):u+2].reshape(-1,3).mean(0).round(1).tolist()
        # pairwise root distances & peg-end to box
        ann=[(p['head_uv'],f"P{p['k']}H",(0,0,255)) for p in pegs]+[(p['tail_uv'],f"P{p['k']}T",(255,0,0)) for p in pegs]+[(rec['box_uv'],'BOX',(0,255,0))]
    records.append(rec)
    # frames
    steps=[('s0',0),('demo_close',demo_close),('demo_end',last_demo),('exec_start',exec_start),('exec_close',exec_close),('exec_end',last)]
    tiles=[]
    for name,t in steps:
        im=cv2.cvtColor(T(t)['obs/front_rgb'][()],cv2.COLOR_RGB2BGR)
        im=cv2.resize(im,(512,512),interpolation=cv2.INTER_NEAREST)
        if name in ('s0','exec_start'):
            for (u,v),lab,col in ann:
                cv2.circle(im,(int(u*2),int(v*2)),6,col,1); cv2.putText(im,lab,(int(u*2)+6,int(v*2)-4),cv2.FONT_HERSHEY_SIMPLEX,0.4,col,1)
        seg=[s for s in segs if s['start']<=t<=s['end']][0]
        cv2.putText(im,f"{name} t={t}",(5,15),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
        cv2.putText(im,seg['simple'][:60],(5,500),cv2.FONT_HERSHEY_SIMPLEX,0.4,(255,255,0),1)
        w=cv2.cvtColor(T(t)['obs/wrist_rgb'][()],cv2.COLOR_RGB2BGR); w=cv2.resize(w,(512,512),interpolation=cv2.INTER_NEAREST)
        tiles.append(np.vstack([im,w]))
        cv2.imwrite(f"{E}/frames/{r['difficulty']}_ep{r['episode']}_{name}_t{t}.png",im)
    cv2.imwrite(f"{E}/frames/{r['difficulty']}_ep{r['episode']}_montage.png",np.hstack(tiles))
json.dump(records,open(E+'/records.json','w'),indent=1)
for x in records:
    print('====',x['difficulty'],x['episode'],x['seed'])
    print(' grasp demo/exec',x['grasp_wp_demo'],x['grasp_wp_exec'],'d=%.4f'%x['grasp_demo_vs_exec_dist_m'],' final d=%.4f'%x['final_demo_vs_exec_dist_m'])
    print(' reset eef',x['eef_reset_exec_start'],x['eef_step0'],' frame0vsexecstart',round(x['frame0_vs_exec_start_meanabs'],2),round(x['frame0_vs_exec_start_frac_px_gt30'],4))
    if 'spec' in x:
        print(' n_inits',x['spec']['n_inits'],'used',x['spec']['init_index_used'],'npegs',len(x['pegs']),'yaws',[p['yaw_deg'] for p in x['pegs']],'gaps',round(x['spec']['min_pair_gap'],3),round(x['spec']['min_box_gap'],3))
        print(' expected',x['expected'],'demo nearest',x['demo_grasp_nearest'][0],'exec nearest',x['exec_grasp_nearest'][0])
        print(' near/far x',x['near_far_xaxis'],'euclid',x['near_far_euclid'],'text',x['segments'][0]['simple'])
        print(' side demo/exec',round(x['demo_side_indicator_y'],3),round(x['exec_side_indicator_y'],3),x['side_ok_demo'],x['side_ok_exec'])
        print(' head_rgb',[round(c*255) for c in x['spec']['head_rgb']],'px',[(p['k'],p.get('head_px_rgb_step0'),p.get('tail_px_rgb_step0')) for p in x['pegs']])
