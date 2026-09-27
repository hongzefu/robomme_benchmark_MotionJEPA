import cv2,json
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
for r in json.load(open(E+'/raw_extract.json')):
    for m in r['mp4']:
        c=cv2.VideoCapture(m); n=int(c.get(cv2.CAP_PROP_FRAME_COUNT)); w=c.get(3); h=c.get(4); fps=c.get(5)
        print(r['tier'],r['seed'],r['n_steps'],n,w,h,fps,m.split('/')[-1][:40])
