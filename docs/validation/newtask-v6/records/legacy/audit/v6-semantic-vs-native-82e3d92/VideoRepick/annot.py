import cv2,json,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoRepick'
raw=json.load(open(E+'/records_raw.json'))
def get(d,ep): return [r for r in raw if (r.get('difficulty') or r['setup']['difficulty'])==d and r['episode']==ep][0]
def tile(m,f,lab):
    c=cv2.VideoCapture(m); c.set(cv2.CAP_PROP_POS_FRAMES,f); ok,im=c.read()
    mm=im[:,0:256].mean(axis=(1,2)); Y0=[y for y in range(40,im.shape[0]-256) if (mm[y:y+200]>45).all()][0]
    t=np.concatenate([im[Y0:Y0+256,0:256],im[Y0:Y0+256,512:1024]],1).copy()
    cv2.rectangle(t,(0,0),(768,34),(0,0,0),-1)
    for i,l in enumerate(lab.split('\n')): cv2.putText(t,l,(4,14+i*15),cv2.FONT_HERSHEY_SIMPLEX,0.42,(255,255,255),1)
    return t
r=get('xhard4',3); m=r['mp4'][0]
tiles=[tile(m,816,'xhard4 ep3 f816 first exec pick -> pick guard window [866,1316]'),
       tile(m,1376,'f1376 5th pick: OUTSIDE pick guard (>1316)\nbutton press here not flagged as failure'),
       tile(m,1503,'f1503 6th pick: OUTSIDE pick guard'),
       tile(m,1576,'f1576 6th put-down: OUTSIDE put guard [978,1428]')]
cv2.imwrite(E+'/frames/finding_timewindow_xhard4_ep3.png',np.concatenate(tiles,0))
r=get('xhard2',3); m=r['mp4'][0]
tiles=[tile(m,0,'xhard2 ep3 f0 demo pick: target at <58,90>'),tile(m,588,'f588 end of 6 swaps: target back at same slot'),tile(m,589,'f589 exec pick 1: grounded <57,90>')]
cv2.imwrite(E+'/frames/finding_target_return_xhard2_ep3.png',np.concatenate(tiles,0))
