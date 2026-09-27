"""只读：按颜色统计方块顶面世界面积，估计同色相邻方块数量。"""
import sys,json,h5py,numpy as np,cv2
from concurrent.futures import ProcessPoolExecutor
E=sys.argv[1]; sys.path.insert(0,E); from geom import world,cam_params,plane_footprint
from counts import hue_name
def est(x,t=0):
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        pw,d=world(g,t); K,ext=cam_params(g,t)
        rgb=g[f'timestep_{t}']['obs']['front_rgb'][()]
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV); z=pw[...,2]
    A=plane_footprint(K,ext,0.04)
    top=(z>0.032)&(z<0.05)&(pw[...,0]>-0.5)&(np.abs(pw[...,1])<0.7)
    names=np.vectorize(hue_name)(hsv[...,0],hsv[...,1],hsv[...,2])
    res={}
    for c in ['red','green','blue','yellow','cyan','magenta']:
        m=top&(names==c)
        n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),connectivity=8)
        comps=[]
        for i in range(1,n):
            sel=lab==i
            if sel.sum()<4: continue
            comps.append(round(float(np.nansum(A[sel]))*1e4,1))
        if comps: res[c]=dict(n_comp=len(comps),area_cm2=comps,est=sum(max(1,round(a/15.0)) for a in comps))
    return res
def run(x): return dict(task=x['task'],tier=x['setup']['difficulty'],ep=x['episode'],colors=est(x))
if __name__=='__main__':
    r=json.load(open(E+'/scan_raw.json'))
    tasks=sys.argv[2].split(',')
    xs=[x for x in r if x['task'] in tasks]
    with ProcessPoolExecutor(16) as ex: out=list(ex.map(run,xs))
    json.dump(out,open(E+'/cubearea_raw.json','w'),indent=1)
    order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
    for o in sorted(out,key=lambda o:(o['task'],order.index(o['tier']),o['ep'])):
        print(o['task'],o['tier'],o['ep'],'total',sum(v['est'] for v in o['colors'].values()),{k:(v['est'],v['area_cm2']) for k,v in o['colors'].items()})
