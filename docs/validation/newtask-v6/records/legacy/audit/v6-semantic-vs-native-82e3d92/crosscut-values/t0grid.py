"""每任务七档各取首局t0（或指定帧）拼图"""
import h5py,json,sys,cv2,numpy as np
E=sys.argv[1]; task=sys.argv[2]; t=int(sys.argv[3]) if len(sys.argv)>3 else 0
r=json.load(open(E+'/scan_raw.json'))
order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
xs=[]
for d in order:
    c=sorted([x for x in r if x['task']==task and x['setup']['difficulty']==d],key=lambda x:x['episode'])
    if c: xs.append(c[0])
ims=[]
for x in xs:
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]; tt=min(t,x['n_steps']-1)
        im=g[f'timestep_{tt}']['obs']['front_rgb'][()][:,:,::-1].copy()
    im=cv2.resize(im,(384,384),interpolation=cv2.INTER_NEAREST)
    cv2.putText(im,f"{x['setup']['difficulty']} ep{x['episode']} t{tt}",(4,14),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
    ims.append(im)
while len(ims)%4: ims.append(np.zeros_like(ims[0]))
rows=[np.hstack(ims[i:i+4]) for i in range(0,len(ims),4)]
out=f'{E}/frames/grid-{task}-t{t}.png'; cv2.imwrite(out,np.vstack(rows)); print(out)
