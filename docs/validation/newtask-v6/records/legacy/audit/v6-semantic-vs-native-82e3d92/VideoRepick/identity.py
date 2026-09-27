import cv2, json, numpy as np, sys
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoRepick'
recs=json.load(open(E+'/records_raw.json'))
Y0=224
def findY0(im):
    m=im[:,0:256].mean(axis=(1,2))
    for y in range(40,im.shape[0]-256):
        if (m[y:y+200]>45).all(): return y
    return None
def panel(im,i): return im[Y0:Y0+256, 256*i:256*(i+1)].astype(np.int32)
def tmask_centroid(tp):
    mask=np.linalg.norm(tp,axis=2)>60
    if mask.sum()<5: return None,0
    ys,xs=np.nonzero(mask); return [float(ys.mean()),float(xs.mean())],int(mask.sum())
class V:
    def __init__(s,m): s.c=cv2.VideoCapture(m); s.cache={}
    def get(s,f):
        if f not in s.cache:
            s.c.set(cv2.CAP_PROP_POS_FRAMES,f); ok,im=s.c.read(); assert ok,f; s.cache[f]=im
        return s.cache[f]
def comps(seg, ref, tol=22):
    m=(np.linalg.norm(seg-ref[None,None,:],axis=2)<tol).astype(np.uint8)
    n,lab,st,cen=cv2.connectedComponentsWithStats(m,8)
    return [(int(st[i,4]),cen[i][::-1].tolist()) for i in range(1,n) if st[i,4]>=5]  # (area,(row,col))
def palette(seg):
    q=(seg//12)
    keys,cnt=np.unique(q.reshape(-1,3),axis=0,return_counts=True)
    cols=[]
    for k,c in zip(keys,cnt):
        if c<15 or k.sum()<3: continue
        ref=np.median(seg[(q==k).all(2)],axis=0)
        if any(np.linalg.norm(ref-x)<22 for x in cols): continue
        cols.append(ref)
    return cols
def biggest(seg,ref):
    cs=comps(seg,ref); 
    return max(cs) if cs else (0,None)
results=[]
for r in recs:
    m=r['mp4'][0]; 
    if 'NO_OBJECT' in m: continue
    v=V(m)
    segs=[s for s in r['segments'] if s['ss'].startswith('pick up')]
    grips=r['gripper_closed_intervals']
    f0=v.get(0); Y0=findY0(f0); globals()['Y0']=Y0; seg0=panel(f0,2)
    # cube candidates at frame0
    cands=[]
    for ref in palette(seg0):
        a,c=biggest(seg0,ref)
        if 12<=a<=400 and c[0]>45: cands.append((ref,a,c))
    rec={'Y0':Y0,'kind':r['kind'],'difficulty':r.get('difficulty') or r['setup']['difficulty'],'episode':r['episode'],'n_candidates_frame0':len(cands),'picks':[]}
    Tref=None
    for s in segs:
        st=s['start']; en=s['end']
        g=[gi for gi in grips if st<=gi[0]<=en]
        # also allow closing after segment end (pick completes when lifted)
        if not g: g=[gi for gi in grips if gi[0]>st][:1]
        fs=v.get(st); tp=panel(fs,3); seg=panel(fs,2)
        mask=np.linalg.norm(tp,axis=2)>60
        tcol=np.median(seg[mask],axis=0) if mask.sum()>5 else None
        if Tref is None and tcol is not None: Tref=tcol
        same=None if tcol is None else bool(np.linalg.norm(tcol-Tref)<22)
        lift=min(g[0][0]+15, g[0][1]) if g else en
        fl=v.get(lift); segl=panel(fl,2)
        # grounded point
        import re
        mm=re.search(r'<(\d+), (\d+)>',s['gs']); gp=[int(mm.group(1)),int(mm.group(2))] if mm else None
        c0,a0=tmask_centroid(tp); c1,a1=tmask_centroid(panel(fl,3))
        tdisp=None if (c0 is None or c1 is None) else float(np.hypot(c1[0]-c0[0],c1[1]-c0[1]))
        gp_on_T=None
        if gp and c0: gp_on_T=float(np.hypot(gp[0]-c0[0],gp[1]-c0[1]))
        others=[]
        for ref,a,c in cands:
            if np.linalg.norm(ref-Tref)<22: continue
            b0=biggest(seg,ref); b1=biggest(segl,ref)
            if b0[1] is None or b1[1] is None: others.append(None); continue
            others.append(round(float(np.hypot(b1[1][0]-b0[1][0],b1[1][1]-b0[1][1])),2))
        rec['picks'].append(dict(seg=s['ss'],demo=s['demo'],start=st,end=en,lift_frame=lift,target_panel_color=None if tcol is None else tcol.round().tolist(),
            target_same_as_demo=same,target_centroid_start=c0,target_area_start=a0,target_centroid_lift=c1,target_disp_px=tdisp,grounded_point=gp,grounded_to_target_px=gp_on_T,
            other_cube_disp_px=others, max_other_disp=max([o for o in others if o is not None],default=None)))
    rec['target_seg_color']=None if Tref is None else Tref.round().tolist()
    rec['exec_pick_count']=sum(1 for p in rec['picks'] if not p['demo']); rec['demo_pick_count']=sum(1 for p in rec['picks'] if p['demo'])
    results.append(rec)
    print(rec['kind'],rec['difficulty'],rec['episode'],'cands',len(cands),'T',rec['target_seg_color'],'demo',rec['demo_pick_count'],'exec',rec['exec_pick_count'])
    for p in rec['picks']: print('   ',p['start'],p['lift_frame'],'D' if p['demo'] else 'E','same',p['target_same_as_demo'],'Tdisp',None if p['target_disp_px'] is None else round(p['target_disp_px'],1),'gp->T',None if p['grounded_to_target_px'] is None else round(p['grounded_to_target_px'],1),'maxOther',p['max_other_disp'])
json.dump(results,open(E+'/identity_check.json','w'),indent=1)
