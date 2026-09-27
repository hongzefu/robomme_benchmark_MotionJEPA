import json,cv2
OUT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmask'
for r in json.load(open(f'{OUT}/records.json')):
    for p in r['mp4']:
        c=cv2.VideoCapture(p); n=int(c.get(cv2.CAP_PROP_FRAME_COUNT)); w=int(c.get(3)); h=int(c.get(4))
        print(r['tier'],r['episode'],r['n_steps'],n,w,h,'NO_OBJECT' if 'NO_OBJECT' in p else '')
