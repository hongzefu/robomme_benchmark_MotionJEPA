"""Read-only: per button segment, lowest eef z and its xy (confirms a physical press on which button)."""
import h5py, json, os, numpy as np
OUT=os.path.dirname(os.path.abspath(__file__))
recs=json.load(open(f'{OUT}/records_raw.json')); res=[]
for r in recs:
    f=h5py.File(r['h5'],'r'); ep=f[list(f.keys())[0]]; s=r['segments']; row=dict(tier=r['tier'],episode=r['episode'])
    for i,x in enumerate(s[:2]):
        t0,t1=x['t'],s[i+1]['t']
        p=np.array([ep[f'timestep_{t}/obs/eef_state'][()][:3] for t in range(t0,t1)])
        j=int(p[:,2].argmin()); row[x['subgoal']]=dict(t=t0+j,xyz=p[j].round(3).tolist())
    res.append(row); print(row)
json.dump(res,open(f'{OUT}/button_press.json','w'),indent=1)
