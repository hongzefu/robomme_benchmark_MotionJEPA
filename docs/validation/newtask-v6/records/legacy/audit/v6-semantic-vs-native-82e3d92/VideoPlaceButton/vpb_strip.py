# usage: strip <tier> <ep> <t1,t2,...> <label> <out> [x,y marker in 256 px]
import h5py,cv2,json,sys
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceButton/raw_extract.json'))
r=[x for x in R if x['difficulty']==sys.argv[1] and x['episode']==int(sys.argv[2])][0]
f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
mk=[int(a) for a in sys.argv[6].split(',')] if len(sys.argv)>6 else None
ims=[]
for t in [int(a) for a in sys.argv[3].split(',')]:
    im=cv2.cvtColor(g[f'timestep_{t}/obs/front_rgb'][()],cv2.COLOR_RGB2BGR); im=cv2.resize(im,(384,384),interpolation=cv2.INTER_NEAREST)
    ss=g[f'timestep_{t}/info/simple_subgoal'][()]; ss=ss.decode() if isinstance(ss,bytes) else str(ss)
    if mk: cv2.circle(im,(int(mk[0]*1.5),int(mk[1]*1.5)),30,(0,255,255),2)
    cv2.rectangle(im,(0,0),(384,44),(0,0,0),-1)
    cv2.putText(im,f'{sys.argv[1]} ep{sys.argv[2]} t={t}',(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
    cv2.putText(im,ss[:44],(4,36),cv2.FONT_HERSHEY_SIMPLEX,0.45,(0,255,255),1)
    ims.append(im)
top=cv2.hconcat(ims); bar=top[:30].copy(); bar[:]=0
cv2.putText(bar,sys.argv[4],(4,20),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1)
cv2.imwrite(sys.argv[5],cv2.vconcat([bar,top]))
