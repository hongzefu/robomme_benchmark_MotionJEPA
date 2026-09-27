import json,cv2
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/PatternLock/records_raw.json'))
for r in R:
    c=cv2.VideoCapture(r['mp4']); n=int(c.get(cv2.CAP_PROP_FRAME_COUNT)); w=c.get(3); h=c.get(4); fps=c.get(5)
    print(r['kind'],r['tier'],r['episode'],'h5',r['frames'],'mp4',n,w,h,fps)
