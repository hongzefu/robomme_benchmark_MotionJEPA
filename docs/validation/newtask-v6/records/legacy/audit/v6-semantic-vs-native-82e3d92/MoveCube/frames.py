import h5py,json,numpy as np,cv2,os
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
raw=json.load(open(E+'/raw_extract.json')); proj=json.load(open(E+'/xhard4_spec_projection.json'))
os.makedirs(E+'/frames',exist_ok=True)
for r in raw:
    f=h5py.File(r['h5'],'r'); ep=f[list(f)[0]]
    tag=('xhard4' if r['kind']=='new' else r['setup']['difficulty'])+f"_ep{r['episode']}"
    n=r['n_steps']; bsteps=[s['step'] for s in r['segments'] if s['boundary']]
    keys=sorted(set([0]+bsteps+[n-1]+[s['step'] for s in r['segments']]))
    tiles=[]
    for k in keys:
        img=ep[f'timestep_{k}/obs/front_rgb'][()].copy()
        big=cv2.resize(img,(512,512),interpolation=cv2.INTER_NEAREST)
        big=cv2.cvtColor(big,cv2.COLOR_RGB2BGR)
        seg=[s for s in r['segments'] if s['step']<=k][-1]
        g=seg['grounded']
        import re
        for m in re.findall(r'<(\d+), (\d+)>',g or ''):
            rr,cc=int(m[0]),int(m[1]); cv2.circle(big,(cc*2,rr*2),10,(0,255,0),2)
        if r['kind']=='new':
            sp=proj[str(r['episode'])]['demo' if seg['demo'] else 'execution']
            for key,col in (('cube_px',(255,0,255)),('goal_px',(255,255,0)),('peg_grasp_px',(0,165,255))):
                u,v=sp[key]; cv2.drawMarker(big,(int(u*2),int(v*2)),col,cv2.MARKER_CROSS,16,2)
        txt=f"{tag} t={k} {'DEMO' if seg['demo'] else 'EXEC'} {seg['simple'][:40]}"
        cv2.rectangle(big,(0,0),(512,22),(0,0,0),-1); cv2.putText(big,txt,(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
        cv2.imwrite(f"{E}/frames/{tag}_t{k:04d}.png",big); tiles.append(cv2.resize(big,(256,256)))
    while len(tiles)%6: tiles.append(np.zeros_like(tiles[0]))
    rows=[np.hstack(tiles[i:i+6]) for i in range(0,len(tiles),6)]
    cv2.imwrite(f"{E}/{tag}_keyframes.png",np.vstack(rows))
    print(tag,keys)
