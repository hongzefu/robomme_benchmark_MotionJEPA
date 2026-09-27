import h5py,json,numpy as np,cv2
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/InsertPeg'
r=[x for x in json.load(open(E+'/records.json')) if x['difficulty']=='xhard4' and x['episode']==6][0]
f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
tiles=[]
for t in [0,150,180,200,210,218,219,400,437]:
    im=cv2.cvtColor(g[f'timestep_{t}/obs/front_rgb'][()],cv2.COLOR_RGB2BGR)[40:110,70:150]
    im=cv2.resize(im,(320,280),interpolation=cv2.INTER_NEAREST); cv2.putText(im,f't={t}',(3,14),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1); tiles.append(im)
cv2.imwrite(E+'/frames/xhard4_ep6_peg1_box_crop_series.png',np.hstack(tiles))
