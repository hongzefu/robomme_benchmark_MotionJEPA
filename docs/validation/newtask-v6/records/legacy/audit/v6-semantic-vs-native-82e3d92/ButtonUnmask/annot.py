"""Annotated evidence PNGs: reveal frame with cube blobs + grounded pick coords + grasp projections; plus custom frames."""
import h5py, json, numpy as np, cv2, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import blobs, proj
OUT = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f'{OUT}/records_raw.json'))
BGR = dict(red=(0,0,255), green=(0,200,0), blue=(255,0,0), yellow=(0,255,255), cyan=(255,255,0), magenta=(255,0,255))
os.makedirs(f'{OUT}/annotated', exist_ok=True)
for r in R:
    f = h5py.File(r['h5'], 'r'); ep = f[list(f.keys())[0]]
    rgb = ep['timestep_16/obs/front_rgb'][()]
    img = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), (768, 768), interpolation=cv2.INTER_NEAREST)
    b = blobs(rgb)
    for c, bl in b.items():
        for x in bl:
            y0, x0 = [int(v*3) for v in x['rc']]
            cv2.circle(img, (x0, y0), 16, BGR[c], 2); cv2.putText(img, c[:3], (x0+14, y0-10), 0, 0.5, (255,255,255), 1)
    for k, p in enumerate(r['picks']):
        gy, gx = [v*3 for v in p['grounded_rc']]
        cv2.drawMarker(img, (gx, gy), (255,255,255), cv2.MARKER_CROSS, 24, 2)
        cv2.putText(img, f"pick{k+1}:{p['named']} grounded", (gx+8, gy+22), 0, 0.5, (255,255,255), 1)
    y = 20
    for k, s in enumerate(r['segments']):
        cv2.putText(img, f"{s['t0']}-{s['t1']} {s['gs'][:70]}", (5, y), 0, 0.42, (255,255,255), 1); y += 16
    cv2.putText(img, f"{r['tier']} ep{r['episode']} t16 reveal", (5, 760), 0, 0.6, (255,255,255), 2)
    cv2.imwrite(f"{OUT}/annotated/{r['tier']}_ep{r['episode']}_reveal_t0016.png", img)
# custom: xhard4 ep6 t280 (segment start, grounded fallback)
r = [r for r in R if r['tier']=='xhard4' and r['episode']==6][0]
f = h5py.File(r['h5'], 'r'); ep = f[list(f.keys())[0]]
for t in (276, 280, 356, 385):
    g = ep[f'timestep_{t}']
    img = cv2.resize(cv2.cvtColor(g['obs/front_rgb'][()], cv2.COLOR_RGB2BGR), (768,768), interpolation=cv2.INTER_NEAREST)
    cv2.drawMarker(img, (111*3, 78*3), (255,255,255), cv2.MARKER_CROSS, 30, 2)
    cv2.putText(img, 'online <78,111> (blue cube reveal at 82,112)', (111*3-150, 78*3-20), 0, 0.5, (255,255,255), 1)
    cv2.putText(img, f"t{t} gs='{g['info/grounded_subgoal'][()].decode()}'", (5, 20), 0, 0.42, (255,255,255), 1)
    cv2.putText(img, f"online='{g['info/grounded_subgoal_online'][()].decode()}'", (5, 38), 0, 0.42, (255,255,255), 1)
    cv2.imwrite(f"{OUT}/annotated/xhard4_ep6_blue_segment_t{t:04d}.png", img)
    w = cv2.resize(cv2.cvtColor(g['obs/wrist_rgb'][()], cv2.COLOR_RGB2BGR), (384,384))
    cv2.imwrite(f"{OUT}/annotated/xhard4_ep6_wrist_t{t:04d}.png", w)
print('ok')
