import h5py,cv2,json,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/StopCube'
recs=json.load(open(E+'/_raw_extract.json')); tr=json.load(open(E+'/_tracks.json'))
on=json.load(open(E+'/_online_segments.json'))
ORD=["first","second","third","fourth","fifth","sixth","seventh","eighth","ninth","tenth","eleventh","twelfth","thirteenth","fourteenth","fifteenth"]
records=[]
for r,T in zip(recs,tr):
    tag=f"{r['tier']}_ep{r['episode']}"
    n=r['n_steps']; P=np.array([x[:2] for x in T['track']]); ty,tx=T['target_px_rc']; tgt=np.array([tx,ty],float)
    u=np.linalg.svd(P-P.mean(0),full_matrices=False)[2][0]; s=(P-tgt)@u
    sp=np.r_[np.hypot(*np.diff(P,axis=0).T),0]
    stop=next(k for k in range(n) if np.all(sp[k:-1]<0.3))
    cross=[k for k in range(1,stop+1) if s[k-1]*s[k]<0 or s[k]==0]
    period=float(np.median(np.diff(cross))) if len(cross)>1 else None
    press_on=[x[0] for x in on[tag] if x[1].startswith('press')][0]
    mi_est=min((60,80,120),key=lambda m:abs(m-period)) if period else None
    goal_word=r['task_goal'][0].split('for the ')[1].split(' time')[0]
    N=ORD.index(goal_word)+1
    if mi_est is None: mi_est=min((60,80,120),key=lambda m:abs(m-(press_on+30)/(N-0.5)))
    lead=[c for c in cross if c < stop - mi_est/4]
    pass_at_stop=len(lead)+1
    win=[mi_est*(N-1), mi_est*N]
    # expected press-subgoal onset under code: steps_press - 30 = mi*(N-0.5)-30
    exp_press=mi_est*(N-0.5)-30
    fin=P[-1]; off=float(np.hypot(*(fin-tgt)))
    rec=dict(tier=r['tier'],episode=r['episode'],seed=r['seed'],h5=r['h5'],mp4=r['mp4'],task_goal=r['task_goal'],
        ordinal_in_goal=goal_word,N_from_goal=N,choices=[c['action'] for c in r['choices']],n_steps=n,
        planner_segments=[dict(start=x['start'],simple=x['simple'],grounded=x['grounded'],choice=x['choice']) for x in r['segments']],
        boundaries=r['boundaries'],online_segments=on[tag],
        target_px_xy=tgt.tolist(),cube_track_method=T['method'],
        target_crossing_frames=cross,crossing_period_frames=period,move_interval_inferred=mi_est,
        online_press_onset=press_on,expected_press_onset=exp_press,
        cube_stop_frame=int(stop),pass_index_at_stop_visual=pass_at_stop,stop_window_code=win,
        stop_in_window=bool(win[0]<=stop<=win[1]),final_cube_px_xy=fin.round(2).tolist(),final_offset_px=round(off,2),
        visual_matches_language=bool(pass_at_stop==N))
    records.append(rec)
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    def frame(t,label):
        im=cv2.resize(g[f'timestep_{t}/obs/front_rgb'][()],(384,384),interpolation=cv2.INTER_NEAREST).copy()
        k=1.5; cv2.circle(im,(int(tgt[0]*k),int(tgt[1]*k)),14,(0,255,0),1)
        cv2.drawMarker(im,(int(P[t,0]*k),int(P[t,1]*k)),(255,255,0),cv2.MARKER_CROSS,14,2)
        cv2.putText(im,label,(4,20),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,0),1); cv2.putText(im,f"f={t}",(4,40),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,0),1)
        return im
    keys=[(c,f"pass {i+1} crossing") for i,c in enumerate(lead)]
    if len(keys)>4: keys=keys[:2]+keys[-2:]
    keys+= [(stop,f"STOP = pass {pass_at_stop} (goal: {goal_word})"),(n-1,"last frame")]
    strip=np.concatenate([frame(t,l) for t,l in keys],1)
    # timeline
    W=max(900,n+100); H=220; tl=np.full((H,W,3),255,np.uint8); y0=110; sc=0.9
    cv2.line(tl,(50,y0),(50+n,y0),(0,160,0),1)
    x0=50+win[0]; x1=50+min(win[1],n)
    cv2.rectangle(tl,(x0,10),(x1,H-30),(220,220,255),-1)
    for t in range(n-1): cv2.line(tl,(50+t,int(y0-s[t]*sc)),(50+t+1,int(y0-s[t+1]*sc)),(0,0,0),1)
    for c in cross: cv2.circle(tl,(50+c,y0),3,(0,128,0),-1)
    cv2.line(tl,(50+stop,10),(50+stop,H-30),(0,0,255),1); cv2.line(tl,(50+press_on,10),(50+press_on,H-30),(255,0,0),1)
    cv2.putText(tl,f"{tag}: cube along-route offset from target (px) vs frame; green dots=target crossings; blue=press subgoal onset {press_on}; red=cube stop {stop}; shaded=code stop window {win}",(5,H-10),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,0,0),1)
    tl=cv2.cvtColor(tl,cv2.COLOR_BGR2RGB)
    if tl.shape[1]<strip.shape[1]: tl=np.pad(tl,((0,0),(0,strip.shape[1]-tl.shape[1]),(0,0)),constant_values=255)
    else: strip=np.pad(strip,((0,0),(0,tl.shape[1]-strip.shape[1]),(0,0)),constant_values=255)
    cv2.imwrite(f"{E}/frames/{tag}_passes_stop{stop:04d}.png",cv2.cvtColor(np.concatenate([strip,tl],0),cv2.COLOR_RGB2BGR))
    print(tag,'N',N,'visual pass',pass_at_stop,'mi',mi_est,'stop',stop,'win',win,'press_on',press_on,'exp',exp_press,'off',round(off,1))
json.dump(records,open(E+'/records.json','w'),indent=1)
