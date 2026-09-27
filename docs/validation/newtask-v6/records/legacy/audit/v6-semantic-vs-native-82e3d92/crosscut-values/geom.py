"""只读：深度反投影到世界坐标，按高度分割物体。"""
import h5py, numpy as np, cv2
def world(g,t,cam='front'):
    s=g[f'timestep_{t}']['obs']
    d=s[f'{cam}_depth'][()][...,0].astype(np.float64)/1000.0
    K=g['setup'][f'{cam}_camera_intrinsic'][()].astype(np.float64)
    ext=s[f'{cam}_camera_extrinsic'][()].astype(np.float64)
    H,W=d.shape; u,v=np.meshgrid(np.arange(W),np.arange(H))
    x=(u-K[0,2])/K[0,0]*d; y=(v-K[1,2])/K[1,1]*d
    pc=np.stack([x,y,d,np.ones_like(d)],-1)
    T=np.eye(4); T[:3]=ext; Ti=np.linalg.inv(T)
    pw=pc@Ti.T
    return pw[...,:3], d

def cam_params(g,t,cam='front'):
    s=g[f'timestep_{t}']['obs']
    K=g['setup'][f'{cam}_camera_intrinsic'][()].astype(np.float64)
    ext=s[f'{cam}_camera_extrinsic'][()].astype(np.float64)
    return K,ext

def plane_footprint(K,ext,h,H=256,W=256):
    """每像素在世界水平面z=h上的面积(m^2)"""
    R=ext[:,:3]; t=ext[:,3]; C=-R.T@t
    u,v=np.meshgrid(np.arange(W+1)-0.5,np.arange(H+1)-0.5)
    rays=np.stack([(u-K[0,2])/K[0,0],(v-K[1,2])/K[1,1],np.ones_like(u)],-1)@R  # R^T * d
    s=(h-C[2])/rays[...,2]
    P=C+rays*s[...,None]
    a=P[:-1,1:]-P[:-1,:-1]; b=P[1:,:-1]-P[:-1,:-1]
    A=np.abs(a[...,0]*b[...,1]-a[...,1]*b[...,0])
    A[s[:-1,:-1]<0]=np.nan
    return A

def components(g,t,zlo=0.012,zhi=0.2,xlim=(-0.5,0.6),ylim=(-0.6,0.6),minpix=6,cam='front'):
    pw,d=world(g,t,cam)
    rgb=g[f'timestep_{t}']['obs'][f'{cam}_rgb'][()]
    z=pw[...,2]
    m=(z>zlo)&(z<zhi)&(pw[...,0]>xlim[0])&(pw[...,0]<xlim[1])&(pw[...,1]>ylim[0])&(pw[...,1]<ylim[1])
    n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),connectivity=8)
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    out=[]
    for i in range(1,n):
        sel=lab==i
        if sel.sum()<minpix: continue
        out.append(dict(npix=int(sel.sum()),u=float(cen[i][0]),v=float(cen[i][1]),
            x=float(np.median(pw[...,0][sel])),y=float(np.median(pw[...,1][sel])),zmax=float(np.percentile(z[sel],95)),
            hsv=[float(np.median(hsv[...,k][sel])) for k in range(3)],rgb=[float(np.median(rgb[...,k][sel])) for k in range(3)]))
    return out,lab,pw,rgb
