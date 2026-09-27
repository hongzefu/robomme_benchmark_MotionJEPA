import h5py,sys,numpy as np,cv2
f=h5py.File(sys.argv[1],'r'); ep=f[list(f.keys())[0]]
for t in [int(x) for x in sys.argv[3:]]:
    img=ep[f'timestep_{t}/obs/front_rgb'][()]
    big=cv2.resize(img[:,:,::-1],(768,768),interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(f"{sys.argv[2]}_t{t}.png",big)
