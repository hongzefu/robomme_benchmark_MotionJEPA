"""只读：按桌面高度带逐帧变化量计数交换窗口（内环/外环分别计）。"""
import sys,json,h5py,numpy as np
from concurrent.futures import ProcessPoolExecutor
E=sys.argv[1]; sys.path.insert(0,E); from geom import world
def segs(sig,frac=0.1,minlen=18,absmin=8):
    sig=np.asarray(sig,float)
    if sig.max()<=absmin: return []
    thr=max(absmin,frac*np.percentile(sig[sig>absmin],90))
    act=sig>thr; w=[]; i=0
    while i<len(sig):
        if act[i]:
            j=i
            while j+1<len(sig) and act[j+1]: j+=1
            if j-i+1>=minlen: w.append([i,j])
            i=j+1
        else: i+=1
    return w,thr
def run(args):
    x,zlo,zhi,t0,t1,ring=args
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        prev=None; si=[];so=[];sa=[]
        for t in range(t0,t1):
            pw,d=world(g,t); z=pw[...,2]; mx=np.maximum(np.abs(pw[...,0]),np.abs(pw[...,1]))
            m=(z>zlo)&(z<zhi)&(pw[...,0]>-0.55)&(np.abs(pw[...,1])<0.7)
            if prev is not None:
                ch=m^prev[0]; inner=(mx<ring)|(prev[1]<ring)
                sa.append(int(ch.sum())); si.append(int((ch&inner).sum())); so.append(int((ch&~inner).sum()))
            prev=(m,mx)
    res={}
    for k,s in (('all',sa),('inner',si),('outer',so)):
        w=segs(s)
        res[k]=dict(windows=[[a+t0+1,b+t0+1] for a,b in w[0]] if w else [],thr=w[1] if w else None)
    return dict(task=x['task'],tier=x['setup']['difficulty'],ep=x['episode'],t0=t0,t1=t1,**res)
if __name__=='__main__':
    r=json.load(open(E+'/scan_raw.json'))
    jobs=[]
    for x in r:
        b=x['boundaries']
        if x['task']=='VideoUnmaskSwap':
            jobs.append((x,0.055,0.095,33,x['n_demo'],0.235))
        elif x['task']=='ButtonUnmaskSwap':
            tp=[bb['t'] for bb in b if bb['s'].startswith('pick up the container')][0]
            jobs.append((x,0.055,0.095,33,tp,0.235))
        elif x['task']=='VideoRepick':
            td=[bb['t'] for bb in b if bb['s'].startswith('drop the cube')][0]
            jobs.append((x,0.012,0.055,td+40,x['n_demo'],9.0))
    with ProcessPoolExecutor(16) as ex: out=list(ex.map(run,jobs))
    json.dump(out,open(E+'/swaps_raw.json','w'),indent=1)
    order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
    for o in sorted(out,key=lambda o:(o['task'],order.index(o['tier']),o['ep'])):
        print(o['task'],o['tier'],o['ep'],'all',len(o['all']['windows']),'inner',len(o['inner']['windows']),'outer',len(o['outer']['windows']),'lens',[b-a+1 for a,b in o['all']['windows']])
