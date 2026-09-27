import sys,json,h5py,numpy as np
sys.path.insert(0,sys.argv[1]); from geom import components
r=json.load(open(sys.argv[1]+'/scan_raw.json'))
task,tier,ep,t=sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5])
x=[x for x in r if x['task']==task and x['setup']['difficulty']==tier and x['episode']==ep][0]
with h5py.File(x['h5']) as f:
    g=f[list(f.keys())[0]]
    comps,*_=components(g,t)
for c in comps: print({k:(round(v,3) if isinstance(v,float) else [round(a) for a in v] if isinstance(v,list) else v) for k,v in c.items()})
