"""只读：StopCube 方块轨迹与靶心距离；MoveCube 方块/靶心位置。"""
import sys,json,h5py,numpy as np,cv2
from concurrent.futures import ProcessPoolExecutor
E=sys.argv[1]; sys.path.insert(0,E); from geom import world
def target_xy(pw,hsv):
    z=pw[...,2]
    m=(z>-0.005)&(z<0.02)&(hsv[...,0]>125)&(hsv[...,0]<165)&(hsv[...,1]>50)&(pw[...,0]>-0.5)
    if m.sum()<5: return None
    return [float(np.mean(pw[...,0][m])),float(np.mean(pw[...,1][m]))],int(m.sum())
def cube_mask(pw,hsv,h0,s0):
    z=pw[...,2]
    dh=np.abs(((hsv[...,0].astype(int)-h0+90)%180)-90)
    return (z>0.02)&(z<0.06)&(dh<10)&(hsv[...,1]>max(40,s0*0.5))&(pw[...,0]>-0.5)
def comps(pw):
    z=pw[...,2]; m=(z>0.015)&(z<0.06)&(pw[...,0]>-0.5)&(np.abs(pw[...,1])<0.7)
    n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),connectivity=8)
    out=[]
    for i in range(1,n):
        sel=lab==i
        if sel.sum()<4: continue
        top=sel&(z>0.03)
        if top.sum()<2: top=sel
        out.append((float(np.mean(pw[...,0][top])),float(np.mean(pw[...,1][top])),int(sel.sum())))
    return out
def stopcube(x):
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        pw,d=world(g,0); rgb=g['timestep_0']['obs']['front_rgb'][()]; hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
        tt=target_xy(pw,hsv); txy=tt[0] if tt else None
        c0=comps(pw)
        btn=min(c0,key=lambda c:(c[0]+0.2)**2+c[1]**2)
        rest=[c for c in c0 if c is not btn]
        prev=max(rest,key=lambda c:c[2]) if rest else None
        traj=[]
        for t in range(x['n_steps']):
            pw,d=world(g,t); cs=[c for c in comps(pw) if (c[0]-btn[0])**2+(c[1]-btn[1])**2>0.07**2]
            if cs and prev is not None:
                c=min(cs,key=lambda c:(c[0]-prev[0])**2+(c[1]-prev[1])**2)
                if (c[0]-prev[0])**2+(c[1]-prev[1])**2<0.05**2: prev=c; traj.append([c[0],c[1]]); continue
            traj.append(None)
    return dict(task='StopCube',tier=x['setup']['difficulty'],ep=x['episode'],target=txy,button=btn[:2],traj=traj,goal=x['setup']['task_goal'][0],
                press_t=[b['t'] for b in x['boundaries'] if b['s'].startswith('press')],n_steps=x['n_steps'])
def movecube(x):
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        out=[]
        for t in (0, x['n_demo']):
            pw,d=world(g,t); rgb=g[f'timestep_{t}']['obs']['front_rgb'][()]; hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
            txy=target_xy(pw,hsv)
            z=pw[...,2]
            m=(z>0.03)&(z<0.05)&((hsv[...,0]<8)|(hsv[...,0]>=172))&(hsv[...,1]>150)&(pw[...,0]>-0.5)
            cxy=[float(np.mean(pw[...,0][m])),float(np.mean(pw[...,1][m]))] if m.sum()>=4 else None
            out.append(dict(t=t,target=txy[0] if txy else None,cube=cxy))
    return dict(task='MoveCube',tier=x['setup']['difficulty'],ep=x['episode'],frames=out,chain=[b['s'] for b in x['boundaries'] if b['demo']])
def run(x): return stopcube(x) if x['task']=='StopCube' else movecube(x)
if __name__=='__main__':
    r=json.load(open(E+'/scan_raw.json'))
    xs=[x for x in r if x['task'] in ('StopCube','MoveCube')]
    with ProcessPoolExecutor(16) as ex: out=list(ex.map(run,xs))
    json.dump(out,open(E+'/track_raw.json','w'))
    print(len(out))
