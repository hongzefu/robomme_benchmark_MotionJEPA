import cv2,sys
m=sys.argv[1]; ts=[int(x) for x in sys.argv[2].split(',')]; out=sys.argv[3]
c=cv2.VideoCapture(m)
import numpy as np
ims=[]
for t in ts:
    c.set(cv2.CAP_PROP_POS_FRAMES,t); ok,f=c.read(); assert ok
    cv2.putText(f,f'mp4 frame {t}',(1000,760),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,255),2); ims.append(f)
cv2.imwrite(out,np.vstack(ims)); print(out)
