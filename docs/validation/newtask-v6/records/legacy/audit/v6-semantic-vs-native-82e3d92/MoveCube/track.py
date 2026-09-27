import h5py,json,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
raw=json.load(open(E+'/raw_extract.json'))
def cent(m):
    ys,xs=np.nonzero(m); 
    return (None if len(ys)==0 else [round(float(ys.mean()),1),round(float(xs.mean()),1)]), int(len(ys))
res={}
for r in raw:
    f=h5py.File(r['h5'],'r'); ep=f[list(f)[0]]
    tag=('xhard4' if r['kind']=='new' else r['setup']['difficulty'])+f"_ep{r['episode']}"
    n=r['n_steps']; tr=[]
    for k in range(n):
        im=ep[f'timestep_{k}/obs/front_rgb'][()].astype(int)
        red=(im[...,0]>120)&(im[...,1]<35)&(im[...,2]<35)
        pur=(im[...,2]>170)&(im[...,1]<130)&(im[...,0]>140)
        rc,rn=cent(red); pc,pn=cent(pur)
        tr.append(dict(t=k,red=rc,red_n=rn,pur=pc,pur_n=pn,demo=bool(ep[f'timestep_{k}/info/is_video_demo'][()]),grip=bool(ep[f'timestep_{k}/obs/is_gripper_close'][()]),eefz=float(ep[f'timestep_{k}/obs/eef_state'][()][2])))
    res[tag]=tr
    segs=r['segments']; b=[s['step'] for s in segs if s['boundary']]
    ex0=[s['step'] for s in segs if s['boundary'] and not s['demo']][0]
    st=[s['step'] for s in segs if s['boundary'] and s['simple']=='static'][0]
    def d(t):
        x=tr[t]; 
        if x['red'] is None or x['pur'] is None: return None
        return round(float(np.hypot(x['red'][0]-x['pur'][0],x['red'][1]-x['pur'][1])),1)
    print(tag,'n',n,'| t0 red',tr[0]['red'],tr[0]['red_n'],'pur',tr[0]['pur'],tr[0]['pur_n'],
          '| static',st,'red',tr[st]['red'],tr[st]['red_n'],'pur',tr[st]['pur'],'d',d(st),
          '| staticEnd',ex0-1,'d',d(ex0-1),tr[ex0-1]['red_n'],
          '| exec0',ex0,'red',tr[ex0]['red'],tr[ex0]['red_n'],'pur',tr[ex0]['pur'],tr[ex0]['pur_n'],
          '| last',n-1,'red',tr[n-1]['red'],tr[n-1]['red_n'],'pur',tr[n-1]['pur'],'d',d(n-1))
json.dump(res,open(E+'/pixel_tracks.json','w'))
