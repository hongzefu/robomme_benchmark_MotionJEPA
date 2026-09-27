"""Native dynamic-mode check: for each pick subgoal target point (grounded <row,col>), at which step does a cube of the
named colour first appear at that pixel?  If ordinal k ~ appearance order, 'second/third' has a visual anchor in native dynamic."""
import json,h5py,numpy as np,re
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill'
R=json.load(open(ROOT+'/records.json')); CH={'red':0,'green':1,'blue':2}
def iscol(rgb,u,v,c,r=1):
    p=rgb[v-r:v+r+1,u-r:u+r+1].reshape(-1,3).astype(float); ch=CH[c]; o=np.max(p[:,[k for k in range(3) if k!=ch]],axis=1)
    return int(((p[:,ch]>60)&(p[:,ch]>o*2.5)).sum())>0
out=[]
for r in R:
    f=h5py.File(r['h5'],'r'); e=f[list(f.keys())[0]]
    rows=[]
    for g in r['grounded_checks']:
        if not g['expected']: continue
        m=re.search(r'<(\d+), (\d+)>',g['text']); a,b=int(m.group(1)),int(m.group(2))
        first=None
        for t in range(0,g['t']+1,5):
            if iscol(e[f'timestep_{t}/obs/front_rgb'][()],b,a,g['expected']): first=t; break
        rows.append((g['text'].split(' at ')[0],g['t'],first))
    out.append(dict(kind=r['kind'],diff=r['difficulty'],ep=r['episode'],picks=rows))
    print(r['kind'],r['difficulty'],r['episode'],rows)
json.dump(out,open(ROOT+'/ordinal_appearance.json','w'),indent=1)
