import cv2,json,sys
out=json.load(open(sys.argv[1]))
for r in out:
    for m in r['mp4']:
        c=cv2.VideoCapture(m); print(r['kind'],r.get('difficulty'),r['episode'],int(c.get(7)),int(c.get(3)),int(c.get(4)),c.get(5),'steps',r['n_steps'],m.split('/')[-1][:40])
