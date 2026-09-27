import h5py, sys, numpy as np, cv2
from collections import Counter

def hue_name(h, s, v):
    # simple HSV hue bucket classifier for red/green/blue
    if h < 8 or h > 172:
        return 'red'
    if 35 <= h <= 85:
        return 'green'
    if 95 <= h <= 130:
        return 'blue'
    return 'other'

h5 = sys.argv[1]
mids = [int(x) for x in sys.argv[2:]]
with h5py.File(h5, 'r') as f:
    ep = list(f.keys())[0]
    g = f[ep]
    for t in mids:
        rgb = g[f'timestep_{t}']['obs']['wrist_rgb'][()]
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        sub = hsv[140:256, 80:176]
        m = sub[..., 1] > 150
        names = [hue_name(int(p[0]), int(p[1]), int(p[2])) for p in sub[m]]
        c = Counter(n for n in names if n in ('red', 'green', 'blue'))
        print(t, c.most_common(3))
        cv2.imwrite(f'wrist_t{t}.png', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
