import sys,json,h5py,numpy as np,cv2
sys.path.insert(0,sys.argv[1]); from geom import world,cam_params,plane_footprint
r=json.load(open(sys.argv[1]+'/scan_raw.json'))
task,tier,ep,t=sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5]); zlo=float(sys.argv[6])
x=[x for x in r if x['task']==task and x['setup']['difficulty']==tier and x['episode']==ep][0]
with h5py.File(x['h5']) as f:
    g=f[list(f.keys())[0]]
    pw,d=world(g,t); K,ext=cam_params(g,t)
z=pw[...,2]
m=(z>zlo)&(z<0.2)&(pw[...,0]>-0.5)&(np.abs(pw[...,1])<0.7)
n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),connectivity=4)
for i in range(1,n):
    sel=lab==i
    if sel.sum()<5: continue
    zm=np.percentile(z[sel],95)
    A=plane_footprint(K,ext,zm)
    area=np.nansum(A[sel])
    print(i,sel.sum(),'u,v',np.round(cen[i]).astype(int),'xy',np.round([np.median(pw[...,0][sel]),np.median(pw[...,1][sel])],3),'zmax',round(zm,3),'area_cm2',round(area*1e4,1))
