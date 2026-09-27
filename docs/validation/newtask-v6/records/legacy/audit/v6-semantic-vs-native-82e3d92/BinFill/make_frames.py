"""Annotated key frames: per episode, t0 front frame with every pick target (grounded <row,col>) labelled by ordinal+colour,
bin/button points, plus the frame at each pick-segment start (target marked) and the last frame. Nearest-neighbour upscale."""
import json,h5py,numpy as np,cv2,re
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill'
R=json.load(open(ROOT+'/records.json'))
def up(im,s=3): return cv2.resize(im,None,fx=s,fy=s,interpolation=cv2.INTER_NEAREST)
for r in R:
    f=h5py.File(r['h5'],'r'); e=f[list(f.keys())[0]]
    fr=lambda t: e[f'timestep_{t}/obs/front_rgb'][()][:,:,::-1].copy()
    base=up(fr(0))
    tiles=[]
    for g in r['grounded_checks']:
        m=re.search(r'<(\d+), (\d+)>',g['text']); a,b=int(m.group(1)),int(m.group(2))
        lab=g['text'].split(' at ')[0].replace('pick up the ','').replace(' cube','')
        cv2.circle(base,(b*3,a*3),9,(255,255,255),2); cv2.putText(base,lab[:14],(b*3+10,a*3),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
        if g['expected']:
            t=up(fr(g['t'])); cv2.circle(t,(b*3,a*3),10,(255,255,255),2)
            cv2.putText(t,f"t{g['t']} {lab} ptcol={g['color_at_point']}",(5,20),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)
            tiles.append(cv2.resize(t,(384,384),interpolation=cv2.INTER_NEAREST))
    cv2.putText(base,f"{r['difficulty']} ep{r['episode']} t0: {r['task_goal'][0][:60]}",(5,20),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),2)
    last=up(fr(r['n_steps']-1)); cv2.putText(last,f"last t{r['n_steps']-1}",(5,20),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)
    top=np.concatenate([base,last],1)
    while len(tiles)%4: tiles.append(np.zeros((384,384,3),np.uint8))
    rows=[np.concatenate(tiles[i:i+4],1) for i in range(0,len(tiles),4)]
    grid=np.concatenate(rows,0) if rows else None
    if grid is not None:
        grid=cv2.resize(grid,(top.shape[1],int(grid.shape[0]*top.shape[1]/grid.shape[1])),interpolation=cv2.INTER_NEAREST)
        top=np.concatenate([top,grid],0)
    cv2.imwrite(f"{ROOT}/frames/{r['kind']}_{r['difficulty']}_ep{r['episode']}_picks_t0_last.png",top)
print('ok')
