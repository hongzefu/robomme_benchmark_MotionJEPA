"""Read-only: within the 'press the second button' segment, measure the trailing idle (eef static) span."""
import h5py, json, os, numpy as np
OUT=os.path.dirname(os.path.abspath(__file__))
recs=json.load(open(f'{OUT}/records_raw.json')); specs={(s['tier'],s['episode']):s for s in json.load(open(f'{OUT}/specs_newtier.json'))}
res=[]
for r in recs:
    f=h5py.File(r['h5'],'r'); ep=f[list(f.keys())[0]]
    s=r['segments']; i=[k for k,x in enumerate(s) if x['subgoal']=='press the second button'][0]
    t0,t1=s[i]['t'],s[i+1]['t']
    p=np.array([ep[f'timestep_{t}/obs/eef_state'][()][:3] for t in range(t0,t1+1)])
    v=np.linalg.norm(np.diff(p,axis=0),axis=1)
    # trailing static run: steps with displacement < 1e-4 m
    k=len(v)
    while k>0 and v[k-1]<1e-4: k-=1
    idle_start=t0+k
    # also longest static run anywhere in segment
    runs=[];cur=0;st=None
    for j,x in enumerate(v):
        if x<1e-4:
            if cur==0: st=t0+j
            cur+=1
        else:
            if cur: runs.append((st,cur)); cur=0
    if cur: runs.append((st,cur))
    lr=max(runs,key=lambda z:z[1]) if runs else (None,0)
    sp=specs.get((r['tier'],r['episode']))
    d=dict(tier=r['tier'],episode=r['episode'],seg=[t0,t1],seg_len=t1-t0,longest_static_run=lr,trailing_idle_from=idle_start,
           trailing_idle_len=t1-idle_start,swap_end=None if sp is None else sp['swap_end'],eef_at_idle=p[min(k,len(p)-1)].round(3).tolist())
    res.append(d); print(d)
json.dump(res,open(f'{OUT}/second_button_idle.json','w'),indent=1)
