import cv2,json
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/StopCube'
for r in json.load(open(E+'/_raw_extract.json')):
    c=cv2.VideoCapture(r['mp4']); print(r['tier'],r['episode'],'mp4 frames',int(c.get(7)),'fps',c.get(5),'size',int(c.get(3)),int(c.get(4)),'h5 steps',r['n_steps'])
