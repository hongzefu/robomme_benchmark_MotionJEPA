"""Read-only: montage of front_rgb frames from an HDF5 at given timesteps (upscaled 2x nearest) with labels."""
import h5py, sys, cv2, numpy as np, json
h5, out = sys.argv[1], sys.argv[2]; ts=[int(x) for x in sys.argv[3].split(',')]
f=h5py.File(h5,'r'); ep=f[list(f.keys())[0]]
tiles=[]
for t in ts:
    g=ep[f'timestep_{t}']
    im=g['obs/front_rgb'][()][:,:,::-1].copy()
    im=cv2.resize(im,(512,512),interpolation=cv2.INTER_NEAREST)
    sg=g['info/simple_subgoal'][()].decode()
    cv2.rectangle(im,(0,0),(512,40),(0,0,0),-1)
    cv2.putText(im,f't={t}',(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
    cv2.putText(im,sg[:60],(4,34),cv2.FONT_HERSHEY_SIMPLEX,0.42,(255,255,255),1)
    tiles.append(im)
while len(tiles)%4: tiles.append(np.zeros_like(tiles[0]))
rows=[np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]
cv2.imwrite(out,np.vstack(rows))
