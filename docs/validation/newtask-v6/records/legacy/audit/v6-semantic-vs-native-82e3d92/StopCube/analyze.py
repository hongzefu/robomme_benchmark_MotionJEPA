import json,numpy as np,cv2
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/StopCube'
tr=json.load(open(E+'/_tracks.json')); recs=json.load(open(E+'/_raw_extract.json'))
out=[]
for T,r in zip(tr,recs):
    n=len(T['track']); ok=[i for i,x in enumerate(T['track']) if x is not None]
    P=np.array([T['track'][i][:2] for i in ok])  # (x,y)
    ty,tx=T['target_px_rc']; tgt=np.array([tx,ty],float)
    # principal axis
    c=P-P.mean(0); u=np.linalg.svd(c,full_matrices=False)[2][0]
    s=(P-tgt)@u
    # stop: first index after which cube moves < 0.3px/frame for rest
    sp=np.r_[np.hypot(*np.diff(P,axis=0).T),0]
    stop=None
    for k in range(len(ok)):
        if np.all(sp[k:-1]<0.3) and len(ok)-k>5: stop=ok[k]; break
    # crossings before stop
    cross=[]
    for k in range(1,len(ok)):
        if stop is not None and ok[k]>stop: break
        if s[k-1]*s[k]<0 or s[k]==0: cross.append(ok[k])
    fin=P[-1]; off=float(np.hypot(*(fin-tgt)))
    # distance at stop along route & perp
    rec=dict(tier=T['tier'],episode=T['episode'],n=n,tracked=len(ok),target_px_xy=tgt.tolist(),stop_frame_est=stop,
             crossings_before_stop=cross,n_crossings=len(cross),final_cube_px_xy=fin.tolist(),final_offset_px=round(off,2),
             amp_px=[float(s.min()),float(s.max())])
    out.append(rec); print(rec)
json.dump(out,open(E+'/_analysis.json','w'),indent=1)
