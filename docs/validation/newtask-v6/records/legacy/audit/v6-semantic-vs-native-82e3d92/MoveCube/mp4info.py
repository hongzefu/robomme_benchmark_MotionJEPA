import cv2,json,glob
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
raw=json.load(open(E+'/raw_extract.json'))
for r in raw:
    m=r['mp4'] if isinstance(r['mp4'],list) else [r['mp4']]
    for p in m:
        c=cv2.VideoCapture(p); print(r['kind'],r['episode'],int(c.get(7)),int(c.get(3)),int(c.get(4)),c.get(5),p.split('/')[-1][:60]); c.release()
