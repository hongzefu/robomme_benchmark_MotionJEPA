import h5py, json, numpy as np, cv2, re
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
track={(t['tier'],t['seed']):t for t in json.load(open(E+'/track_check.json'))}
for r in json.load(open(E+'/raw_extract.json')):
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    items=[(5,'reveal t5'),(50,'covered t50'),(r['demo_last_step'],'demo end')]
    for sg in r['segments']:
        if sg['simple'].startswith('pick up'):
            c=re.search(r'hides the (\w+) cube',sg['simple']).group(1)
            items.append((sg['start'],f'pick {c} start')); items.append((sg['end'],f'pick {c} lifted'))
    tiles=[]
    tr=track.get((r['tier'],r['seed']))
    for t,lab in items:
        im=cv2.cvtColor(g[f'timestep_{t}']['obs/front_rgb'][()],cv2.COLOR_RGB2BGR)
        im=cv2.resize(im,(320,320),interpolation=cv2.INTER_NEAREST); s=320/256
        if tr and 'lifted' in lab:
            c=lab.split()[1]; p=tr['picks'][c]
            ex=p['expected_px']; cv2.circle(im,(int(ex[0]*s),int(ex[1]*s)),12,(0,255,255),2)
        cv2.rectangle(im,(0,0),(320,18),(0,0,0),-1)
        cv2.putText(im,f't{t} {lab}',(3,13),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
        tiles.append(im)
    while len(tiles)%3: tiles.append(np.zeros_like(tiles[0]))
    sheet=np.vstack([np.hstack(tiles[i:i+3]) for i in range(0,len(tiles),3)])
    head=np.zeros((40,sheet.shape[1],3),np.uint8)
    goal=r['task_goal'][0]
    cv2.putText(head,f"{r['tier']} ep{r['episode']} seed{r['seed']}",(3,14),cv2.FONT_HERSHEY_SIMPLEX,0.45,(0,255,255),1)
    cv2.putText(head,goal[:150],(3,32),cv2.FONT_HERSHEY_SIMPLEX,0.33,(255,255,255),1)
    out=f"{E}/sheets/{r['tier']}_ep{r['episode']}_seed{r['seed']}.png"
    cv2.imwrite(out,np.vstack([head,sheet]))
    print(out)
