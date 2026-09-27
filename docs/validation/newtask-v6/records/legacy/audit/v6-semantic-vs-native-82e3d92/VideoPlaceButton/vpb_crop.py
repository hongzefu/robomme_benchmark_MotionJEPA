import h5py,cv2,json,sys
R=json.load(open(sys.argv[1]))
r=[x for x in R if x['difficulty']==sys.argv[2] and x['episode']==int(sys.argv[3])][0]
f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
x,y,h=[int(a) for a in sys.argv[5].split(',')]
ims=[]
for t in [int(a) for a in sys.argv[4].split(',')]:
    im=g[f'timestep_{t}/obs/front_rgb'][()][max(0,y-h):y+h,max(0,x-h):x+h]; im=cv2.cvtColor(im,cv2.COLOR_RGB2BGR); im=cv2.resize(im,(256,256),interpolation=cv2.INTER_NEAREST)
    cv2.putText(im,f't={t}',(5,20),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2); ims.append(im)
cv2.imwrite(sys.argv[6],cv2.hconcat(ims))
