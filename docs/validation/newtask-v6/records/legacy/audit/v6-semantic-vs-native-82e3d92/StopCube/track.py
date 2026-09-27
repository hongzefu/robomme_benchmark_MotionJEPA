# Track cube in front_rgb by median-background subtraction (two selectors; keep the one tracking more frames).
import h5py,cv2,numpy as np,json,re
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'; E=R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/StopCube'
recs=json.load(open(E+'/_raw_extract.json'))
def run(fr,bg,satf):
    track=[]; prev=None
    for t in range(len(fr)):
        hsv=cv2.cvtColor(fr[t].astype(np.uint8),cv2.COLOR_RGB2HSV)
        d=np.abs(fr[t]-bg).max(-1)>35
        d[:35,:]=False  # robot base band at top of image
        num,lab,st,cen=cv2.connectedComponentsWithStats(d.astype(np.uint8))
        best=None
        for i in range(1,num):
            a=st[i,4]
            if a<12 or a>400: continue
            c=cen[i]
            if satf:
                if hsv[...,1][lab==i].mean()<70: continue  # gray robot parts
                sc=-a
            else:
                sc=0 if prev is None else np.hypot(*(c-prev))
            if best is None or sc<best[0]: best=(sc,c,a)
        if best is None or (not satf and prev is not None and best[0]>25): track.append(None)
        else:
            prev=best[1]; track.append([float(best[1][0]),float(best[1][1]),int(best[2])])
    return track
res=[]
for r in recs:
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]; n=r['n_steps']
    fr=np.stack([g[f'timestep_{t}/obs/front_rgb'][()] for t in range(n)]).astype(np.int16)
    bg=np.median(fr,axis=0)
    press=[s for s in r['segments'] if s['simple'].startswith('press')][0]
    ty,tx=map(int,re.findall(r'<(\d+), (\d+)>',press['grounded'])[0])
    cands=[(run(fr,bg,True),'saturation'),(run(fr,bg,False),'nearest')]
    track,meth=max(cands,key=lambda c:sum(x is not None for x in c[0]))
    res.append(dict(tier=r['tier'],episode=r['episode'],target_px_rc=[ty,tx],method=meth,track=track))
    print(r['tier'],r['episode'],meth,'tracked',sum(x is not None for x in track),'/',n)
json.dump(res,open(E+'/_tracks.json','w'))
