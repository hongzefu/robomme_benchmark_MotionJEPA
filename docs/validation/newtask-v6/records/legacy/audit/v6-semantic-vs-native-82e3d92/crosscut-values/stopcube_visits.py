"""只读：StopCube 在方块远离靶时重估靶心，统计方块经过靶心次数（含起点与最终停止）。"""
import sys,json,h5py,math,numpy as np,cv2
E=sys.argv[1]; sys.path.insert(0,E); from geom import world
from track import target_xy
out=json.load(open(E+'/track_raw.json')); r={(x['task'],x['setup']['difficulty'],x['episode']):x for x in json.load(open(E+'/scan_raw.json'))}
res=[]
order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
for o in sorted([o for o in out if o['task']=='StopCube'],key=lambda o:(order.index(o['tier']),o['ep'])):
    x=r[('StopCube',o['tier'],o['ep'])]; tr=o['traj']
    valid=[(t,p) for t,p in enumerate(tr) if p]
    start=valid[0][1]
    tfar=max(valid,key=lambda tp:math.dist(tp[1],start))[0]
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        pw,d=world(g,tfar); rgb=g[f'timestep_{tfar}']['obs']['front_rgb'][()]; hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
        z=pw[...,2]; cp=tr[tfar]
        far=(pw[...,0]-cp[0])**2+(pw[...,1]-cp[1])**2>0.05**2
        m=(z>-0.005)&(z<0.02)&(hsv[...,0]>125)&(hsv[...,0]<165)&(hsv[...,1]>50)&(pw[...,0]>-0.5)&far
        T=[float(np.mean(pw[...,0][m])),float(np.mean(pw[...,1][m]))]
    dist=[math.dist(p,T) if p else None for p in tr]
    eps=0.03
    visits=[]; inside=False
    for t,dd in enumerate(dist):
        if dd is None: continue
        if dd<eps and not inside: visits.append(t); inside=True
        elif dd>=eps+0.01: inside=False
    final=[dd for dd in dist if dd is not None][-1]
    ordw=o['goal'].split('for the ')[-1].replace(' time','')
    ys=[p[1] for p in tr if p]
    res.append(dict(tier=o['tier'],ep=o['ep'],goal_ordinal=ordw,visits_t=visits,n_visits=len(visits),final_dist_m=round(final,4),target=[round(v,3) for v in T],t_far=tfar,y_range=[round(min(ys),3),round(max(ys),3)],lost_frames=sum(p is None for p in tr)))
    print(res[-1])
json.dump(res,open(E+'/stopcube_visits.json','w'),indent=1)
