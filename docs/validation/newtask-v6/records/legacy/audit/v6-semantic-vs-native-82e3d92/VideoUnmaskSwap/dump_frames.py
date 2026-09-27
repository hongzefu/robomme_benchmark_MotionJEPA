import h5py, json, sys, cv2, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
recs={(r['tier'],r['seed']):r for r in json.load(open(E+'/raw_extract.json'))}
tier=sys.argv[1]; seed=int(sys.argv[2]); steps=[int(x) for x in sys.argv[3].split(',')]
r=recs[(tier,seed)]
f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
tiles=[]
for t in steps:
    im=g[f'timestep_{t}']['obs/front_rgb'][()]
    im=cv2.resize(im,(384,384),interpolation=cv2.INTER_NEAREST)
    im=cv2.cvtColor(im,cv2.COLOR_RGB2BGR)
    cv2.putText(im,f'{tier} s{seed} t{t}',(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
    tiles.append(im)
while len(tiles)%4: tiles.append(np.zeros_like(tiles[0]))
rows=[np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]
out=f"{E}/frames/{tier}_s{seed}_front_{'-'.join(map(str,steps))}.png"
cv2.imwrite(out,np.vstack(rows)); print(out)
