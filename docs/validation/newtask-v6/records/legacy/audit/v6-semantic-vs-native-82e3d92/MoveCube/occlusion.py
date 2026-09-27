import h5py,json,numpy as np,cv2
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
recs=json.load(open(E+'/records.json'))
out={}
for r in recs:
    f=h5py.File(r['h5'],'r'); ep=f[list(f)[0]]
    st=r['demo_end']['step']; ex0=r['exec_start']['step']
    fr=[];wr=[]
    for k in range(st,ex0):
        for cam,lst in (('front_rgb',fr),('wrist_rgb',wr)):
            im=ep[f'timestep_{k}/obs/{cam}'][()].astype(int)
            lst.append(int(((im[...,0]>120)&(im[...,1]<35)&(im[...,2]<35)).sum()))
    out[r['tag']]=dict(static=[st,ex0-1],front_red_min=min(fr),front_red_max=max(fr),wrist_red_min=min(wr),wrist_red_max=max(wr))
    print(r['tag'],out[r['tag']])
    if r['tag'] in ('xhard4_ep3','hard_ep11'):
        k=(st+ex0)//2
        a=cv2.resize(ep[f'timestep_{k}/obs/front_rgb'][()],(384,384),interpolation=cv2.INTER_NEAREST)
        b=cv2.resize(ep[f'timestep_{k}/obs/wrist_rgb'][()],(384,384),interpolation=cv2.INTER_NEAREST)
        im=cv2.cvtColor(np.hstack([a,b]),cv2.COLOR_RGB2BGR)
        cv2.putText(im,f"{r['tag']} t={k} demo static: front (L, cube red px={fr[k-st]}) | wrist (R, {wr[k-st]})",(4,14),cv2.FONT_HERSHEY_SIMPLEX,0.42,(255,255,255),1)
        cv2.imwrite(f"{E}/occlusion_{r['tag']}_t{k:04d}.png",im)
json.dump(out,open(E+'/demo_end_occlusion.json','w'),indent=1)
