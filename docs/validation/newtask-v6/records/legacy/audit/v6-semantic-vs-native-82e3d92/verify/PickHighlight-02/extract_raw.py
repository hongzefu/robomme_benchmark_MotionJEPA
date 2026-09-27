import h5py, numpy as np, cv2, sys, os
h5 = sys.argv[1]
tag = sys.argv[2]
steps = [int(x) for x in sys.argv[3].split(',')]
outdir = sys.argv[4]
f = h5py.File(h5, 'r')
ep = f[list(f.keys())[0]]
keys = list(ep.keys())
print("sample keys:", keys[:3], "..." if len(keys)>3 else "")
imgs = []
for t in steps:
    im = ep[f'timestep_{t}/obs/front_rgb'][()]
    im = cv2.resize(im, (400,400), interpolation=cv2.INTER_NEAREST)
    cv2.putText(im, f'{tag} t={t}', (5,20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,0), 1)
    imgs.append(im)
out = np.concatenate(imgs, 1)
p = os.path.join(outdir, f'{tag}_raw_t{"-".join(map(str,steps))}.png')
cv2.imwrite(p, cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
print("wrote", p)
