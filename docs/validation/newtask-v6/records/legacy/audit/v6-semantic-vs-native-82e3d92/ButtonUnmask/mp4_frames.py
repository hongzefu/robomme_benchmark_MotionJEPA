"""Grab key frames from delivered mp4s (reveal t16, grasp moments) to confirm the video matches HDF5."""
import cv2, json, os
OUT = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f'{OUT}/records_raw.json'))
os.makedirs(f'{OUT}/mp4_frames', exist_ok=True)
for r in R:
    if not (r['tier'].startswith('xhard') or r['episode'] in (10, 11)): continue
    mp = [m for m in r['mp4'] if 'NO_OBJECT' not in os.path.basename(m)][0]
    cap = cv2.VideoCapture(mp)
    want = [16] + [p['grasp_t'] + 12 for p in r['picks']]
    for t in want:
        cap.set(cv2.CAP_PROP_POS_FRAMES, t); ok, fr = cap.read()
        if ok: cv2.imwrite(f"{OUT}/mp4_frames/{r['tier']}_ep{r['episode']}_mp4_f{t:04d}.jpg", cv2.resize(fr, (960, 576)))
    cap.release()
print('ok')
