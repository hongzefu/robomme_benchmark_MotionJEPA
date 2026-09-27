import json,cv2,sys
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/PatternLock/records_raw.json'))
r=R[int(sys.argv[1])]; c=cv2.VideoCapture(r['mp4'])
for fi in map(int,sys.argv[2:]):
    c.set(cv2.CAP_PROP_POS_FRAMES,fi); ok,im=c.read()
    cv2.imwrite(f"/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/PatternLock/frames/raw_{r['tier']}_ep{r['episode']}_f{fi}.png",im)
