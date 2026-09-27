import cv2,sys,glob
p=glob.glob(sys.argv[1])[0]; cap=cv2.VideoCapture(p); n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); print('frames',n,cap.get(cv2.CAP_PROP_FRAME_WIDTH),cap.get(cv2.CAP_PROP_FRAME_HEIGHT),cap.get(cv2.CAP_PROP_FPS))
for fi in map(int,sys.argv[3:]):
    cap.set(cv2.CAP_PROP_POS_FRAMES,fi); ok,im=cap.read(); print(fi,ok)
    if ok: cv2.imwrite(sys.argv[2].replace('.png',f'_f{fi}.png'),im)
