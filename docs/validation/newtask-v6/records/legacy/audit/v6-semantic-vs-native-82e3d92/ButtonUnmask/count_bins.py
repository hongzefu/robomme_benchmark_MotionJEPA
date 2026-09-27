"""Count white container blobs in the front frame at t=33 (after reveal drop, arm still near home)."""
import h5py, json, numpy as np, cv2, os
OUT = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f'{OUT}/records_raw.json'))
exp = dict(easy=3, medium=5, hard=15, xhard1=16, xhard2=18, xhard3=20, xhard4=22)
res = []
for r in R:
    f = h5py.File(r['h5'], 'r'); ep = f[list(f.keys())[0]]
    rgb = ep['timestep_33/obs/front_rgb'][()]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    m = ((hsv[..., 1] < 40) & (hsv[..., 2] > 150)).astype(np.uint8)
    m[:12] = 0  # exclude robot base region at image top rows
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, 8)
    areas = sorted([int(st[i, 4]) for i in range(1, n) if st[i, 4] >= 40])
    res.append(dict(tier=r['tier'], ep=r['episode'], white_blobs=len(areas), expected_bins_plus_button=exp[r['tier']] + 1, areas=areas))
    print(r['tier'], r['episode'], 'white blobs>=40px:', len(areas), 'expected containers+button', exp[r['tier']] + 1, areas)
json.dump(res, open(f'{OUT}/container_count_t33.json', 'w'), indent=1)
