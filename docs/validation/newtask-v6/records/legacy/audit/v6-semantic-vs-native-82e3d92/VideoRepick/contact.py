import cv2, json, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoRepick'
recs=json.load(open(E+'/records_raw.json')); ids=json.load(open(E+'/identity_check.json'))
def findY0(im):
    m=im[:,0:256].mean(axis=(1,2))
    for y in range(40,im.shape[0]-256):
        if (m[y:y+200]>45).all(): return y
index=[]
for r in recs:
    m=r['mp4'][0]
    if 'NO_OBJECT' in m: continue
    diff=r.get('difficulty') or r['setup']['difficulty']
    idr=[x for x in ids if x['kind']==r['kind'] and x['episode']==r['episode'] and x['difficulty']==diff][0]
    keys=[]
    for p in idr['picks']:
        keys.append((p['start'],('DEMO ' if p['demo'] else 'EXEC ')+'start '+p['seg'][:40]))
        keys.append((p['lift_frame'],('DEMO ' if p['demo'] else 'EXEC ')+'lift  '+p['seg'][:40]))
    statics=[s for s in r['segments'] if s['ss']=='static']
    if statics: keys.append((statics[-1]['end'],'DEMO end of swap phase'))
    btn=[s for s in r['segments'] if s['ss'].startswith('press')]
    if btn: keys.append((btn[0]['end'],'EXEC '+btn[0]['ss'][:40]))
    keys.append((r['n_steps']-1,'final frame'))
    c=cv2.VideoCapture(m); tiles=[]
    Y0=None
    for f,lab in keys:
        c.set(cv2.CAP_PROP_POS_FRAMES,f); ok,im=c.read()
        if Y0 is None: Y0=findY0(im)
        t=np.concatenate([im[Y0:Y0+256,0:256],im[Y0:Y0+256,512:768],im[Y0:Y0+256,768:1024]],axis=1).copy()
        cv2.rectangle(t,(0,0),(768,22),(0,0,0),-1)
        cv2.putText(t,f"f{f} {lab}",(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
        tiles.append(t)
    cols=2; rows=(len(tiles)+cols-1)//cols
    while len(tiles)<rows*cols: tiles.append(np.zeros_like(tiles[0]))
    grid=np.concatenate([np.concatenate(tiles[i*cols:(i+1)*cols],axis=1) for i in range(rows)],axis=0)
    name=f"contact_{r['kind']}_{diff}_ep{r['episode']}.jpg"
    cv2.imwrite(E+'/frames/'+name,grid,[cv2.IMWRITE_JPEG_QUALITY,85])
    index.append(dict(kind=r['kind'],difficulty=diff,episode=r['episode'],image='frames/'+name,frames=[k[0] for k in keys]))
json.dump(index,open(E+'/contact_index.json','w'),indent=1)
print(len(index))
