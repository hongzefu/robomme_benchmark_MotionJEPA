import h5py,cv2,numpy as np,sys
f=h5py.File(sys.argv[1],'r'); g=f[list(f.keys())[0]]
ts=[int(x) for x in sys.argv[3].split(',')]
imgs=[]
for t in ts:
    im=g[f'timestep_{t}/obs/front_rgb'][()]
    im=cv2.resize(im,(512,512),interpolation=cv2.INTER_NEAREST)
    cv2.putText(im,f't={t}',(5,25),cv2.FONT_HERSHEY_SIMPLEX,0.8,(255,255,0),2)
    imgs.append(im)
cv2.imwrite(sys.argv[2],cv2.cvtColor(np.concatenate(imgs,1),cv2.COLOR_RGB2BGR))
