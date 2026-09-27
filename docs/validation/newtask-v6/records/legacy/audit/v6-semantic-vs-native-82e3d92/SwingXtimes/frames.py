import json,cv2,re,os,math
D='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/SwingXtimes'
R=json.load(open(D+'/raw_extract.json'))
os.makedirs(D+'/frames',exist_ok=True)
def grab(mp4,i):
    c=cv2.VideoCapture(mp4); c.set(cv2.CAP_PROP_POS_FRAMES,i); ok,fr=c.read(); return fr if ok else None
sel={('xhard1',0),('xhard2',0),('xhard3',0),('xhard4',0),('xhard4',6),('easy',0),('medium',2),('hard',3)}
made=[]
for r in R:
    if (r['difficulty'],r['episode']) not in sel: continue
    mp4=[m for m in r['mp4'] if 'success_NO_OBJECT' not in os.path.basename(m)][0]
    segs=r['segments']
    picks=[(0,'frame0 '+r['task_goal'][0][:90])]
    vis=r['swing_visual']
    if vis: picks+= [(vis[0]['end_frame'],vis[0]['seg']),(vis[1]['end_frame'],vis[1]['seg']),(vis[-1]['end_frame'],vis[-1]['seg'])]
    for s in segs:
        if '11th' in s['simple']: picks.append((s['frame']+5,s['simple']))
    picks.append((r['n_frames']-1,'last frame'))
    for fi,lab in picks:
        fr=grab(mp4,fi)
        if fr is None: continue
        cv2.putText(fr,f"{r['difficulty']} ep{r['episode']} f{fi}: {lab}"[:120],(5,fr.shape[0]-10),cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,0,255),2)
        fn=f"{D}/frames/{r['difficulty']}_ep{r['episode']}_f{fi:04d}.png"; cv2.imwrite(fn,fr); made.append(fn)
print(len(made)); print('\n'.join(made))
