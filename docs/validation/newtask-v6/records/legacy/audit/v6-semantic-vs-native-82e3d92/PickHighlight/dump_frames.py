import h5py,numpy as np,cv2,sys,os
h,tag=sys.argv[1],sys.argv[2]; frames=[int(x) for x in sys.argv[3].split(',')]
f=h5py.File(h,'r'); ep=f[list(f.keys())[0]]
os.makedirs(os.path.dirname(os.path.abspath(__file__))+'/frames',exist_ok=True)
imgs=[]
for t in frames:
    im=ep[f'timestep_{t}/obs/front_rgb'][()]
    im=cv2.resize(im,(512,512),interpolation=cv2.INTER_NEAREST)
    cv2.putText(im,f'{tag} t={t}',(5,20),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,0),2)
    imgs.append(im)
out=np.concatenate(imgs,1)
p=os.path.dirname(os.path.abspath(__file__))+f'/frames/{tag}_t{"-".join(map(str,frames))}.png'
cv2.imwrite(p,cv2.cvtColor(out,cv2.COLOR_RGB2BGR)); print(p)
