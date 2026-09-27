import h5py,json,cv2,numpy as np,os,re
OUT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmask'
recs=json.load(open(f'{OUT}/raw_extract.json'))
def grab(g,t,cam='front_rgb'):
    return g[f'timestep_{t}']['obs'][cam][()]
for e in recs:
    f=h5py.File(e['h5'],'r'); g=f[[k for k in f if k.startswith('episode_')][0]]
    ts=[0,10,20,33,50,65]
    labs=['t0','t10','t20','t33','t50','t65']
    for sg in e['segments']:
        if sg['simple'].startswith('pick'):
            ts+= [sg['start'], sg['end']]; labs+=[f"pk-s{sg['start']}",f"pk-e{sg['end']}"]
        elif sg['simple'].startswith('put'):
            ts+=[sg['end']]; labs+=[f"pd-e{sg['end']}"]
    ts.append(e['n_steps']-1); labs.append('last')
    tiles=[]
    for t,l in zip(ts,labs):
        im=cv2.cvtColor(grab(g,t),cv2.COLOR_RGB2BGR); im=cv2.resize(im,(384,384),interpolation=cv2.INTER_NEAREST)
        cv2.putText(im,f'{l} t={t}',(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
        # mark grounded point on pick start
        for sg in e['segments']:
            if sg['start']==t and '<' in sg['grounded']:
                y,x=map(int,re.search(r'<(\d+), (\d+)>',sg['grounded']).groups()); cv2.circle(im,(int(x*1.5),int(y*1.5)),8,(255,255,255),2)
        tiles.append(im)
    while len(tiles)%6: tiles.append(np.zeros_like(tiles[0]))
    rows=[np.hstack(tiles[i:i+6]) for i in range(0,len(tiles),6)]
    sheet=np.vstack(rows)
    hdr=np.zeros((40,sheet.shape[1],3),np.uint8); cv2.putText(hdr,f"{e['tier']} ep{e['episode']} seed{e['seed']}: {e['setup']['task_goal'][0]}",(4,26),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1)
    p=f"{OUT}/frames/sheet_{e['tier']}_ep{e['episode']}_seed{e['seed']}.png"; cv2.imwrite(p,np.vstack([hdr,sheet])); print(p)
