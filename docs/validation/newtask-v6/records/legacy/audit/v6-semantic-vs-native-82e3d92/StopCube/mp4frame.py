import cv2,json,sys
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/StopCube'
r=[x for x in json.load(open(E+'/_raw_extract.json')) if x['tier']==sys.argv[1] and x['episode']==int(sys.argv[2])][0]
c=cv2.VideoCapture(r['mp4'])
for t in map(int,sys.argv[3].split(',')):
    c.set(1,t); ok,im=c.read()
    cv2.imwrite(f"{E}/mp4_{r['tier']}_ep{r['episode']}_f{t:04d}.png",im)
