"""只读：逐帧计算桌面物体高度带内的变化量（排除机械臂高度），输出活动窗口。"""
import sys,json,h5py,numpy as np
sys.path.insert(0,sys.argv[1]); from geom import world
def band_masks(g,ts,zlo,zhi):
    out=[]
    for t in ts:
        pw,d=world(g,t); z=pw[...,2]
        out.append(((z>zlo)&(z<zhi)&(pw[...,0]>-0.5)&(np.abs(pw[...,1])<0.7)))
    return out
def windows(sig,thr,gap=3,minlen=3):
    act=np.where(np.array(sig)>thr)[0]; w=[]
    for a in act:
        if w and a-w[-1][1]<=gap: w[-1][1]=a
        else: w.append([a,a])
    return [x for x in w if x[1]-x[0]+1>=minlen]
if __name__=='__main__':
    r=json.load(open(sys.argv[1]+'/scan_raw.json'))
    task,tier,ep=sys.argv[2],sys.argv[3],int(sys.argv[4]); zlo,zhi=float(sys.argv[5]),float(sys.argv[6])
    t1=int(sys.argv[7]) if len(sys.argv)>7 else None
    x=[x for x in r if x['task']==task and x['setup']['difficulty']==tier and x['episode']==ep][0]
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        T=t1 or x['n_steps']
        ms=band_masks(g,range(T),zlo,zhi)
    sig=[0]+[int((ms[i]^ms[i-1]).sum()) for i in range(1,T)]
    print('sig',sig)
    print('windows',windows(sig,4))
