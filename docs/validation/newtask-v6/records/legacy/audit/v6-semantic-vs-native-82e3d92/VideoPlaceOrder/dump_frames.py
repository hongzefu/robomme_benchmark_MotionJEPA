import h5py, json, sys, cv2, numpy as np, os
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceOrder'
d=json.load(open(f'{E}/raw_extract.json'))
tier,epi=sys.argv[1],int(sys.argv[2]); ts=[int(x) for x in sys.argv[3].split(',')]
ep=[e for e in d if e['tier']==tier and e['episode']==epi][0]
f=h5py.File(ep['h5'],'r'); g=f[[k for k in f.keys() if k.startswith('episode_')][0]]
imgs=[]
for t in ts:
    im=g[f'timestep_{t}/obs/front_rgb'][()]
    im=cv2.resize(im,(512,512),interpolation=cv2.INTER_NEAREST)
    im=cv2.cvtColor(im,cv2.COLOR_RGB2BGR)
    cv2.putText(im,f'{tier} ep{epi} t={t}',(5,20),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)
    imgs.append(im)
row=[np.concatenate(imgs[i:i+4]+[np.zeros_like(imgs[0])]*(4-len(imgs[i:i+4])),1) for i in range(0,len(imgs),4)]
out=f'{E}/frames/{tier}_ep{epi}_{sys.argv[4] if len(sys.argv)>4 else "m"}.png'
cv2.imwrite(out,np.concatenate(row,0)); print(out)
