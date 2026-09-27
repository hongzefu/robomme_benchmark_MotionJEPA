"""只读：从HDF5抽front_rgb帧拼图。用法: frames.py <task> <tier> <ep> <t1,t2,...> [cam]"""
import h5py, json, sys, cv2, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-values'
r=json.load(open(E+'/scan_raw.json'))
task,tier,ep,ts=sys.argv[1],sys.argv[2],int(sys.argv[3]),[int(x) for x in sys.argv[4].split(',')]
cam=sys.argv[5] if len(sys.argv)>5 else 'front_rgb'
x=[x for x in r if x['task']==task and x['setup']['difficulty']==tier and x['episode']==ep][0]
imgs=[]
with h5py.File(x['h5'],'r') as f:
    g=f[list(f.keys())[0]]
    for t in ts:
        im=g[f'timestep_{t}']['obs'][cam][()][:,:,::-1].copy()
        im=cv2.resize(im,(512,512),interpolation=cv2.INTER_NEAREST)
        cv2.putText(im,f'{task} {tier} ep{ep} t{t}',(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
        imgs.append(im)
cols=min(4,len(imgs)); rows=(len(imgs)+cols-1)//cols
canvas=np.zeros((rows*512,cols*512,3),np.uint8)
for i,im in enumerate(imgs): canvas[(i//cols)*512:(i//cols+1)*512,(i%cols)*512:(i%cols+1)*512]=im
out=f"{E}/frames/{task}-{tier}-ep{ep}-{cam}-t{'_'.join(map(str,ts))}.png"
cv2.imwrite(out,canvas); print(out)
