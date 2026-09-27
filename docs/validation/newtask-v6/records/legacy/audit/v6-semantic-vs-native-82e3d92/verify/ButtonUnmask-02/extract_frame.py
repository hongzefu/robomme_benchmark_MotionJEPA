import h5py, sys, cv2, numpy as np

h5path, t, outpath = sys.argv[1], int(sys.argv[2]), sys.argv[3]
with h5py.File(h5path, 'r') as f:
    ep = list(f.keys())[0]
    key = f"timestep_{t}"
    if key not in f[ep]:
        keys = sorted([k for k in f[ep].keys() if k.startswith('timestep_')], key=lambda x: int(x.split('_')[1]))
        print("max timestep available:", keys[-1])
        key = keys[-1]
    rgb = f[ep][key]['obs']['front_rgb'][()]
bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
cv2.imwrite(outpath, bgr)
print("wrote", outpath, rgb.shape)
