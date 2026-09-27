"""只读：按任务在固定帧上计数方块（按颜色）与容器（内/外环）。"""
import sys,json,h5py,numpy as np,cv2
from concurrent.futures import ProcessPoolExecutor
E=sys.argv[1]; sys.path.insert(0,E); from geom import world
def hue_name(h,s,v):
    if s<60: return 'white'
    if h<8 or h>=170: return 'red'
    if 20<=h<40: return 'yellow'
    if 45<=h<75: return 'green'
    if 80<=h<100: return 'cyan'
    if 105<=h<135: return 'blue'
    if 140<=h<170: return 'magenta'
    return f'h{int(h)}'
def cubes(g,t):
    pw,d=world(g,t); z=pw[...,2]
    rgb=g[f'timestep_{t}']['obs']['front_rgb'][()]; hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    m=(z>0.012)&(z<0.055)&(pw[...,0]>-0.5)&(np.abs(pw[...,1])<0.7)
    n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),connectivity=4)
    out=[]
    for i in range(1,n):
        sel=lab==i
        if sel.sum()<8: continue
        h,s,v=[float(np.median(hsv[...,k][sel])) for k in range(3)]
        out.append(dict(npix=int(sel.sum()),u=round(cen[i][0],1),v=round(cen[i][1],1),x=round(float(np.median(pw[...,0][sel])),3),y=round(float(np.median(pw[...,1][sel])),3),zmax=round(float(np.percentile(z[sel],95)),3),color=hue_name(h,s,v),hsv=[round(h),round(s),round(v)]))
    return out
def bins(g,t,ring):
    pw,d=world(g,t); z=pw[...,2]
    m=(z>0.055)&(z<0.095)&(pw[...,0]>-0.5)&(np.abs(pw[...,1])<0.7)
    n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),connectivity=4)
    out=[]
    for i in range(1,n):
        sel=lab==i
        if sel.sum()<5: continue
        x,y=float(np.median(pw[...,0][sel])),float(np.median(pw[...,1][sel]))
        out.append(dict(npix=int(sel.sum()),x=round(x,3),y=round(y,3),ring='outer' if max(abs(x),abs(y))>ring else 'inner'))
    return out
def run(x):
    task=x['task']; res=dict(task=task,tier=x['setup']['difficulty'],ep=x['episode'],h5=x['h5'])
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        res['t0_objects']=cubes(g,0)
        if task in ('VideoUnmask','ButtonUnmask'):
            res['bins_t']=65 if task=='VideoUnmask' else 40
            res['bins']=bins(g,res['bins_t'],0.235)
        if task in ('VideoUnmaskSwap','ButtonUnmaskSwap'):
            res['bins_t']=40
            res['bins']=bins(g,40,0.235)
    return res
if __name__=='__main__':
    r=json.load(open(E+'/scan_raw.json'))
    with ProcessPoolExecutor(16) as ex: out=list(ex.map(run,r))
    json.dump(out,open(E+'/counts_raw.json','w'),indent=1)
    from collections import Counter
    order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
    for o in sorted(out,key=lambda o:(o['task'],order.index(o['tier']),o['ep'])):
        c=Counter(a['color'] for a in o['t0_objects'] if 0.03<a['zmax']<0.05)
        big=[a['npix'] for a in o['t0_objects'] if a['npix']>400]
        s=f"{o['task']} {o['tier']} {o['ep']} cubes={sum(v for k,v in c.items() if k!='white')} {dict(c)} big={big}"
        if 'bins' in o: s+=f" bins={Counter(b['ring'] for b in o['bins'])}"
        print(s)
