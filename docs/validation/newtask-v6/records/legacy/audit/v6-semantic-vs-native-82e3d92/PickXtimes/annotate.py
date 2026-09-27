import h5py,json,numpy as np,cv2,re
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/PickXtimes'
R=json.load(open(E+'/records.json'))
S=3
def up(img): return cv2.resize(img[:,:,::-1],(256*S,256*S),interpolation=cv2.INTER_NEAREST).copy()
def put(im,txt,y,col=(255,255,255)):
    cv2.putText(im,txt,(5,y),cv2.FONT_HERSHEY_SIMPLEX,0.45,(0,0,0),3); cv2.putText(im,txt,(5,y),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
BGR={'red':(0,0,255),'green':(0,255,0),'blue':(255,0,0),'yellow':(0,255,255),'cyan':(255,255,0),'magenta':(255,0,255)}
hue_log=[]
for r in R:
    f=h5py.File(r['h5'],'r'); ep=f[list(f.keys())[0]]
    T=r['n_steps']; picks=[s for s in r['segments'] if s['simple'].startswith('pick')]; places=[s for s in r['segments'] if s['simple'].startswith('place')]
    btn=[s for s in r['segments'] if s['simple'].startswith('press')][0]
    tiles=[]
    # tile 1: frame0 census
    im=up(ep['timestep_0/obs/front_rgb'][()])
    for k,bl in r['frame0_blobs'].items():
        for cx,cy,a in bl: cv2.circle(im,(int(cx*S),int(cy*S)),22,BGR[k],2); put(im,k,0) if False else cv2.putText(im,k,(int(cx*S)+24,int(cy*S)),cv2.FONT_HERSHEY_SIMPLEX,0.5,BGR[k],2)
    put(im,f"t0 {r['kind']} {r['difficulty']} ep{r['episode']} seed{r['seed']}",15); put(im,f"goal: {r['goal_color']} x{r['goal_N']}",32)
    put(im,'census: '+','.join(f"{k}:{len(v)}" for k,v in r['frame0_blobs'].items() if v),49)
    tiles.append(im)
    # tile 2: first pick grounded point
    p=picks[0]; rc=tuple(int(x) for x in re.search(r'<(\d+), (\d+)>',p['grounded']).groups())
    im=up(ep[f"timestep_{p['start']}/obs/front_rgb"][()]); cv2.drawMarker(im,(rc[1]*S,rc[0]*S),(255,255,255),cv2.MARKER_CROSS,30,2)
    put(im,f"t{p['start']} {p['simple']}",15); put(im,f"grounded <r,c>={rc}",32); tiles.append(im)
    # tile 3: last place end (cube on disk) with disk marker
    pl=places[-1]; rc2=tuple(int(x) for x in re.search(r'<(\d+), (\d+)>',pl['grounded']).groups())
    im=up(ep[f"timestep_{btn['start']}/obs/front_rgb"][()]); cv2.circle(im,(rc2[1]*S,rc2[0]*S),30,(255,255,255),2)
    put(im,f"t{btn['start']} after place #{len(places)} -> {btn['simple']}",15); put(im,f"grounded: {btn['grounded']}",32); tiles.append(im)
    # tile 4: final
    im=up(ep[f"timestep_{T-1}/obs/front_rgb"][()]); put(im,f"t{T-1} final ({r['segments'][-1]['simple']}) completed@{r['completed_first_step']}",15)
    put(im,f"picks={len(picks)} places={len(places)} grip_edges={len(r['gripper_close_rising_edges'])}",32); tiles.append(im)
    out=np.concatenate(tiles,axis=1)
    fn=f"{E}/frames/{r['kind']}_{r['difficulty']}_ep{r['episode']}_t0-t{picks[0]['start']}-t{btn['start']}-t{T-1}.png"
    cv2.imwrite(fn,out)
    # disk ring hue vs magenta cube hue (frame0)
    img0=ep['timestep_0/obs/front_rgb'][()]; hsv=cv2.cvtColor(img0,cv2.COLOR_RGB2HSV)
    rr,cc=rc2; yy,xx=np.ogrid[:256,:256]; d=np.hypot(yy-rr,xx-cc); ring=(d<=9)&(hsv[...,1]>80)
    mag=r['frame0_blobs'].get('magenta',[])
    hue_log.append(dict(ep=f"{r['kind']}_{r['difficulty']}_ep{r['episode']}",disk_ring_h=float(np.median(hsv[...,0][ring])) if ring.any() else None,disk_ring_s=float(np.median(hsv[...,1][ring])) if ring.any() else None,magenta_blob=mag))
    f.close()
json.dump(hue_log,open(E+'/disk_vs_magenta_hue.json','w'),indent=1)
print(hue_log[:12])
