"""Visual check: at each node contact, which projected grid node shows the red highlight disk in front_rgb."""
import h5py,numpy as np,json,cv2
B='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/PatternLock'
R=json.load(open(B+'/records_raw.json'))
G={'easy':3,'medium':4,'hard':5}
def nxy(k,g):
    r,c=divmod(k,g); rc=(g-1)/2; return np.array([-0.1+(r-rc)*0.1,(c-rc)*0.1,0.01])
summary=[]
for r in R:
    g=G.get(r['tier'],5)
    f=h5py.File(r['h5'],'r'); ep=f[next(iter(f))]; K=ep['setup/front_camera_intrinsic'][()]
    X=ep['timestep_0/obs/front_camera_extrinsic'][()]
    uv=[]
    for k in range(g*g):
        c=K@(X@np.r_[nxy(k,g),1]); uv.append(c[:2]/c[2])
    uv=np.array(uv)
    n=r['frames']; allc={}
    for i in range(n):
        q=ep[f'timestep_{i}/obs/eef_state'][()][:3]
        d=np.linalg.norm(uv*0+0,axis=1) if False else None
        dd=[np.linalg.norm(nxy(k,g)[:2]-q[:2]) for k in range(g*g)]
        k=int(np.argmin(dd))
        if dd[k]<=0.01 and q[2]<0.1: allc.setdefault(k,[]).append(i)
    res=[]
    for part,nodes,steps in (('demo',r['demo_nodes'],r['demo_node_steps']),('exec',r['exec_nodes'],r['exec_node_steps'])):
        for j,(k,s) in enumerate(zip(nodes,steps)):
            fi=min(s+4,r['frames']-1)
            im=ep[f'timestep_{fi}/obs/front_rgb'][()].astype(int)
            red=(im[...,0]>150)&(im[...,1]<90)&(im[...,2]<90)
            yy,xx=np.mgrid[0:256,0:256]
            cnt=[int((red&((xx-u)**2+(yy-v)**2<=16)).sum()) for u,v in uv]
            # nodes highlighted within 40 steps before: previous node(s) may still be red
            recent=[k2 for k2,ss in allc.items() if any(0<=fi-x<=41 for x in ss)]
            lit=[i for i,cn in enumerate(cnt) if cn>=3]
            res.append(dict(part=part,idx=j,node=k,step=s,frame=fi,red_at_node=cnt[k],lit=lit,unexpected_lit=[i for i in lit if i not in recent]))
    bad=[x for x in res if x['red_at_node']<3 or x['unexpected_lit']]
    summary.append(dict(tier=r['tier'],episode=r['episode'],kind=r['kind'],contacts=len(res),bad=bad,uv=uv.round(1).tolist()))
    print(r['kind'],r['tier'],r['episode'],'contacts',len(res),'bad',len(bad),[ (b['part'],b['idx'],b['node'],b['red_at_node'],b['unexpected_lit']) for b in bad][:6])
json.dump(summary,open(B+'/visual_highlight_check.json','w'),indent=1)
