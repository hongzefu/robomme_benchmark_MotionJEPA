"""Annotated key frames: path overlay on demo frame + exec contact frames with expected node circled."""
import h5py,numpy as np,json,cv2
B='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/PatternLock'
R=json.load(open(B+'/records_raw.json')); V={(v['kind'],v['tier'],v['episode']):v for v in json.load(open(B+'/visual_highlight_check.json'))}
S=2
for r in R:
    uv=np.array(V[(r['kind'],r['tier'],r['episode'])]['uv'])*S
    f=h5py.File(r['h5'],'r'); ep=f[next(iter(f))]
    def fr(i):
        im=cv2.cvtColor(ep[f'timestep_{i}/obs/front_rgb'][()],cv2.COLOR_RGB2BGR)
        return cv2.resize(im,(256*S,256*S),interpolation=cv2.INTER_NEAREST)
    # panel 1: path overlay on the last demo contact frame
    last=r['demo_node_steps'][-1]
    p=fr(last)
    for k,(u,v) in enumerate(uv): cv2.putText(p,str(k),(int(u)+4,int(v)-4),cv2.FONT_HERSHEY_SIMPLEX,0.35,(255,255,0),1)
    for j,(a,b) in enumerate(zip(r['demo_nodes'],r['demo_nodes'][1:])):
        cv2.arrowedLine(p,tuple(uv[a].astype(int)),tuple(uv[b].astype(int)),(0,255,0),1,tipLength=0.25)
    cv2.circle(p,tuple(uv[r['demo_nodes'][0]].astype(int)),7,(255,0,255),2)
    cv2.putText(p,f"{r['tier']} ep{r['episode']} N={r['n_nodes']} demo f{last} start=magenta",(4,14),cv2.FONT_HERSHEY_SIMPLEX,0.4,(255,255,255),1)
    # exec contact thumbnails
    thumbs=[]
    labs=['(start)']+[x.replace('move ','') for x in r['exec_seg_labels'] if x!='All tasks completed']
    for j,(k,s) in enumerate(zip(r['exec_nodes'],r['exec_node_steps'])):
        fi=min(s+4,r['frames']-1); t=fr(fi); cv2.circle(t,tuple(uv[k].astype(int)),10,(0,255,255),2)
        t=cv2.resize(t,(192,192),interpolation=cv2.INTER_AREA)
        cv2.putText(t,f"f{fi} n{k}",(3,12),cv2.FONT_HERSHEY_SIMPLEX,0.38,(255,255,255),1)
        cv2.putText(t,labs[j] if j<len(labs) else '?',(3,186),cv2.FONT_HERSHEY_SIMPLEX,0.38,(255,255,255),1)
        thumbs.append(t)
    cols=8; rows=(len(thumbs)+cols-1)//cols
    grid=np.zeros((rows*192,cols*192,3),np.uint8)
    for j,t in enumerate(thumbs): grid[(j//cols)*192:(j//cols+1)*192,(j%cols)*192:(j%cols+1)*192]=t
    W=max(512,grid.shape[1]); canvas=np.zeros((512+grid.shape[0],W,3),np.uint8); canvas[:512,:512]=p; canvas[512:,:grid.shape[1]]=grid
    cv2.imwrite(f"{B}/frames/{r['kind']}_{r['tier']}_ep{r['episode']}_path_and_exec_contacts.png",canvas)
print('ok')
