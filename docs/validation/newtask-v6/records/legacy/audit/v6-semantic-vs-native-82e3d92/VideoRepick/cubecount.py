import cv2,json,numpy as np,colorsys
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoRepick'
recs=json.load(open(E+'/records_raw.json')); out=[]
def findY0(im):
    m=im[:,0:256].mean(axis=(1,2))
    for y in range(40,im.shape[0]-256):
        if (m[y:y+200]>45).all(): return y
for r in recs:
    if r['kind']!='new': continue
    c=cv2.VideoCapture(r['mp4'][0]); ok,im=c.read(); Y0=findY0(im)
    front=im[Y0:Y0+256,0:256]; seg=im[Y0:Y0+256,512:768].astype(int)
    hsv=cv2.cvtColor(front,cv2.COLOR_BGR2HSV).astype(int)
    rgb=r['spec']['objects']['color_rgb']; h,s,v=colorsys.rgb_to_hsv(*rgb); H=h*180
    dh=np.minimum(abs(hsv[...,0]-H),180-abs(hsv[...,0]-H))
    mask=((dh<10)&(hsv[...,1]>90)).astype(np.uint8)
    # exclude table: table hue ~10-20 orange; if cube hue near table, rely on seg non-black
    mask&=(np.linalg.norm(seg,axis=2)>60).astype(np.uint8)
    n,lab,st,cen=cv2.connectedComponentsWithStats(mask,8)
    blobs=[int(st[i,4]) for i in range(1,n) if st[i,4]>=15]
    rec=dict(difficulty=r['difficulty'],episode=r['episode'],spec_cube_count=r['spec']['objects']['cube_count']['actual'],visible_color_blobs_frame0=len(blobs),blob_areas=blobs,hue_deg=round(h*360,1))
    out.append(rec); print(rec)
    cv2.imwrite(E+f"/frames/frame0_mask_{r['difficulty']}_ep{r['episode']}.png",np.concatenate([front,cv2.cvtColor(mask*255,cv2.COLOR_GRAY2BGR)],1))
json.dump(out,open(E+'/cube_count_check.json','w'),indent=1)
