import cv2,sys
for p in sys.argv[1:]:
    cap=cv2.VideoCapture(p); n=0; last=None
    while True:
        ok,fr=cap.read()
        if not ok: break
        n+=1; last=fr
    print(n, None if last is None else last.shape, p.split('/')[-1][:50])
    if last is not None and 'NO_OBJECT' in p: cv2.imwrite(sys.argv[0].rsplit('/',1)[0]+'/xhard1_ep3_NO_OBJECT_lastframe.png',last)
