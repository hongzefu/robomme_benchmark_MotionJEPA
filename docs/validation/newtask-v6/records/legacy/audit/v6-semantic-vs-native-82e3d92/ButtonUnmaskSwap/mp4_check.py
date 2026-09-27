"""Read-only: mp4 frame count / size vs HDF5 step count."""
import cv2, json, os
OUT=os.path.dirname(os.path.abspath(__file__)); res=[]
for r in json.load(open(f'{OUT}/records_raw.json')):
    c=cv2.VideoCapture(r['mp4']); n=int(c.get(cv2.CAP_PROP_FRAME_COUNT)); w=int(c.get(3)); h=int(c.get(4))
    res.append(dict(tier=r['tier'],episode=r['episode'],mp4_frames=n,h5_steps=r['n_steps'],size=[w,h])); print(res[-1])
json.dump(res,open(f'{OUT}/mp4_check.json','w'),indent=1)
