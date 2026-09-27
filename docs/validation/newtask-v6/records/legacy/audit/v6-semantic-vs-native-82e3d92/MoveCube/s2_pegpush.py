import h5py,json,numpy as np,cv2,glob,re
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
out={}
def s(x):
    x=x[()]; return x.decode() if isinstance(x,bytes) else x
for sid in ['6100001','6100002','6100006']:
    h=glob.glob(f'{R}/artifacts/newtask-v6/v6-s2-20260926-01/episodes/MoveCube-xhard4-{sid}/hdf5_files/*.h5')[0]
    f=h5py.File(h,'r'); ep=f[list(f)[0]]
    ts=sorted([k for k in ep if k.startswith('timestep_')],key=lambda k:int(k.split('_')[1])); n=len(ts)
    segs=[];prev=None;tr=[]
    for i,k in enumerate(ts):
        info=ep[k]['info']; row=(s(info['simple_subgoal']),s(info['grounded_subgoal']),bool(info['is_video_demo'][()]))
        bd=bool(info['is_subgoal_boundary'][()])
        if bd or row!=prev: segs.append(dict(step=i,boundary=bd,simple=row[0],grounded=row[1],demo=row[2])); prev=row
        im=ep[k]['obs/front_rgb'][()].astype(int)
        red=(im[...,0]>120)&(im[...,1]<35)&(im[...,2]<35); pur=(im[...,2]>170)&(im[...,1]<130)&(im[...,0]>140)
        peg=(abs(im[...,0]-220)<25)&(abs(im[...,1]-117)<20)&(abs(im[...,2]-95)<20)
        c=lambda m:[round(float(np.nonzero(m)[0].mean()),1),round(float(np.nonzero(m)[1].mean()),1)] if m.any() else None
        tr.append(dict(t=i,red=c(red),red_n=int(red.sum()),pur=c(pur),peg=c(peg),peg_n=int(peg.sum()),grip=bool(ep[k]['obs/is_gripper_close'][()]),gw=ep[k]['obs/gripper_state'][()].tolist()))
    hook=[x['step'] for x in segs if x['boundary'] and x['simple'].startswith('Hook')]
    st=[x['step'] for x in segs if x['boundary'] and x['simple']=='static'][0]
    keys=sorted(set([0]+[x['step'] for x in segs]+[n-1]+[ (hook[0]+st)//2, (hook[1]+n-1)//2]))
    tiles=[]
    for k in keys:
        big=cv2.cvtColor(cv2.resize(ep[ts[k]]['obs/front_rgb'][()],(512,512),interpolation=cv2.INTER_NEAREST),cv2.COLOR_RGB2BGR)
        sg=[x for x in segs if x['step']<=k][-1]
        for m in re.findall(r'<(\d+), (\d+)>',sg['grounded'] or ''): cv2.circle(big,(int(m[1])*2,int(m[0])*2),10,(0,255,0),2)
        cv2.rectangle(big,(0,0),(512,22),(0,0,0),-1); cv2.putText(big,f"S2 {sid} t={k} {'D' if sg['demo'] else 'E'} {sg['simple'][:42]}",(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
        tiles.append(cv2.resize(big,(256,256)))
    while len(tiles)%5: tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(f'{E}/s2_{sid}_pegpush_keyframes.png',np.vstack([np.hstack(tiles[i:i+5]) for i in range(0,len(tiles),5)]))
    d=lambda t:None if tr[t]['red'] is None or tr[t]['pur'] is None else round(float(np.hypot(tr[t]['red'][0]-tr[t]['pur'][0],tr[t]['red'][1]-tr[t]['pur'][1])),1)
    # gripper closed throughout hook segment?
    exec_hook=range(hook[1],n); demo_hook=range(hook[0],st)
    out[sid]=dict(h5=h,segments=segs,keys=keys,d_static=d(st),d_last=d(n-1),red_n_static=tr[st]['red_n'],
      grip_closed_frac_demo_hook=float(np.mean([tr[t]['grip'] for t in demo_hook])),grip_closed_frac_exec_hook=float(np.mean([tr[t]['grip'] for t in exec_hook])),
      red_start=tr[0]['red'],red_hookstart_exec=tr[hook[1]]['red'],red_last=tr[n-1]['red'],pur_last=tr[n-1]['pur'])
    print(sid,json.dumps({k:v for k,v in out[sid].items() if k not in('segments','h5')}))
    for x in segs: print('   ',x['step'],'B' if x['boundary'] else '-', 'D' if x['demo'] else 'E', x['simple'][:45],'|',x['grounded'][:80])
json.dump(out,open(E+'/s2_pegpush_check.json','w'),indent=1)
