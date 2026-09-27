import cv2,json,sys
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
raw=json.load(open(E+'/raw_extract.json'))
kind,ep,ts=sys.argv[1],int(sys.argv[2]),[int(x) for x in sys.argv[3].split(',')]
r=[x for x in raw if x['kind']==kind and x['episode']==ep][0]
p=r['mp4'] if isinstance(r['mp4'],str) else r['mp4'][0]
tag=('xhard4' if kind=='new' else r['setup']['difficulty'])+f'_ep{ep}'
c=cv2.VideoCapture(p)
for t in ts:
    c.set(1,t); ok,fr=c.read()
    cv2.imwrite(f'{E}/frames/mp4_{tag}_f{t:04d}.png',fr); print(ok,t)
