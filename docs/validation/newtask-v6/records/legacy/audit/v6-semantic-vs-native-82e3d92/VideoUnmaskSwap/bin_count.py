import h5py, json, cv2, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
recs=json.load(open(E+'/raw_extract.json'))
exp={'easy':3,'medium':4,'hard':4,'xhard1':8,'xhard2':10,'xhard3':12,'xhard4':14}
def white(im):
    im=im.astype(int); mn=im.min(-1); mx=im.max(-1)
    m=((mn>150)&(mx-mn<30)).astype(np.uint8)
    m[:20,:]=0  # robot base strip at top
    n,lab,st,cen=cv2.connectedComponentsWithStats(m,8)
    return [ (int(cen[i][0]),int(cen[i][1]),int(st[i][4])) for i in range(1,n) if st[i][4]>=30]
out=[]
for r in recs:
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    c50=len(white(g['timestep_50']['obs/front_rgb'][()]))
    c63=len(white(g['timestep_63']['obs/front_rgb'][()]))
    cl=len(white(g[f"timestep_{r['demo_last_step']}"]['obs/front_rgb'][()]))
    out.append(dict(tier=r['tier'],seed=r['seed'],t50=c50,t63=c63,demo_last=cl,expected=exp[r['tier']]))
    print(r['tier'],r['seed'],'white blobs t50',c50,'t63',c63,'demo_last',cl,'expected containers',exp[r['tier']])
json.dump(out,open(E+'/bin_count.json','w'),indent=1)
