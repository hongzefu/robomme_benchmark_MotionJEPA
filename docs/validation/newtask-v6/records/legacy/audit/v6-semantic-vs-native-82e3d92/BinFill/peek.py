import h5py, cv2, numpy as np, sys
f=h5py.File(sys.argv[1],'r'); e=f[list(f.keys())[0]]; t=int(sys.argv[2]); out=sys.argv[3]
rgb=e[f'timestep_{t}/obs/front_rgb'][()]; w=e[f'timestep_{t}/obs/wrist_rgb'][()]
im=np.concatenate([rgb,w],1)[:,:,::-1].copy()
for a in sys.argv[4:]:
    y,x=map(int,a.split(',')); cv2.circle(im,(x,y),4,(255,255,255),1)
im=cv2.resize(im,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
cv2.imwrite(out,im)
