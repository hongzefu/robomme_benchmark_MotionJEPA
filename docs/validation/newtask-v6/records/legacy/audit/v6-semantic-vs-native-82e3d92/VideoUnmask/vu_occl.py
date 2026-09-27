import h5py,json,cv2,numpy as np,glob
OUT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmask'
recs=json.load(open(f'{OUT}/raw_extract.json'))
e=[r for r in recs if r['tier']=='xhard2' and r['episode']==0][0]
f=h5py.File(e['h5'],'r'); g=f[[k for k in f if k.startswith('episode_')][0]]
for t in [386,387,388,389,395,420]:
    i=g[f'timestep_{t}']
    print(t,[i['info'][k][()] for k in ['simple_subgoal','grounded_subgoal','grounded_subgoal_online','is_subgoal_boundary']],i['action']['choice_action'][()])
ims=[]
for t in [10,387,388,420,483]:
    im=cv2.cvtColor(g[f'timestep_{t}']['obs']['front_rgb'][()],cv2.COLOR_RGB2BGR); im=cv2.resize(im,(512,512),interpolation=cv2.INTER_NEAREST)
    cv2.circle(im,(int(137*2),int(93.5*2)),14,(255,255,255),2); cv2.putText(im,f't={t} blue-cube reveal pos (y93.5,x137)',(4,18),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1); ims.append(im)
cv2.imwrite(f'{OUT}/frames/xhard2_ep0_pick3_target_occluded_t388.png',np.hstack(ims))
for p in glob.glob(e['h5'].rsplit('/hdf5_files',1)[0]+'/videos/*.mp4'):
    c=cv2.VideoCapture(p); print(int(c.get(cv2.CAP_PROP_FRAME_COUNT)),p.split('/')[-1][:40])
