import h5py,cv2,json,numpy as np
OUT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceButton'
R=json.load(open(OUT+'/raw_extract.json'))
def cents(im):
    im=im.astype(int); r,g,b=im[...,0],im[...,1],im[...,2]
    m={'red':(r>140)&(g<60)&(b<60),'green':(g>130)&(r<90)&(b<90),'blue':(b>110)&(r<50)&(g<60)}
    out={}
    for k,v in m.items():
        ys,xs=np.nonzero(v)
        out[k]=[int(xs.mean()),int(ys.mean()),int(v.sum())] if v.sum()>=15 else None
    return out
res=[]
for r in R:
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    segs=[]
    for s in r['segments']:
        if segs and segs[-1]['simple']==s['simple'] and segs[-1]['demo']==s['demo']: segs[-1]['end']=s['end']; continue
        segs.append(dict(simple=s['simple'],grounded=s['grounded'],demo=s['demo'],start=s['start'],end=s['end']))
    ev=[]
    for i,s in enumerate(segs):
        a=cents(g[f"timestep_{s['start']}/obs/front_rgb"][()]); b=cents(g[f"timestep_{s['end']}/obs/front_rgb"][()])
        moved={}
        for c in ('red','green','blue'):
            if a[c] and b[c]:
                d=float(np.hypot(a[c][0]-b[c][0],a[c][1]-b[c][1]))
                if d>4: moved[c]=[a[c][:2],b[c][:2],round(d,1)]
        ev.append(dict(i=i,start=s['start'],end=s['end'],demo=s['demo'],simple=s['simple'],grounded=s['grounded'],cents_end=b,moved=moved))
    res.append(dict(difficulty=r['difficulty'],episode=r['episode'],events=ev))
json.dump(res,open(OUT+'/cube_tracks.json','w'),indent=1)
for x in res:
    print('==',x['difficulty'],x['episode'])
    for e in x['events']:
        print(f"  {e['start']:5d}-{e['end']:5d} d={int(e['demo'])} {e['grounded'][:45]:45s} moved={e['moved']}")
