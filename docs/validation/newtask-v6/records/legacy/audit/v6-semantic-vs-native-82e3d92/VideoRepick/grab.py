import cv2,sys,os
m=sys.argv[1]; out=sys.argv[2]; frames=[int(x) for x in sys.argv[3].split(',')]
c=cv2.VideoCapture(m)
for f in frames:
    c.set(cv2.CAP_PROP_POS_FRAMES,f); ok,im=c.read()
    if ok: cv2.imwrite(f"{out}_f{f:05d}.png",im)
