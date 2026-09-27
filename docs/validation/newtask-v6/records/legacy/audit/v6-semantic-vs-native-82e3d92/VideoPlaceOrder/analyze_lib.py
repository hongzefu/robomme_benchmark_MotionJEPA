"""Read-only semantic-vs-visual analysis of VPO episodes (h5py/numpy/cv2 only)."""
import h5py, json, re, cv2, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceOrder'

ORD={'first':1,'second':2,'third':3,'fourth':4,'fifth':5}
CFG={'xhard1':[2,3],'xhard2':[3,3],'xhard3':[3,4],'xhard4':[4,4]}
def rgb(g,t): return g[f'timestep_{t}/obs/front_rgb'][()]
def coord(s):
    m=re.search(r'<(\d+), (\d+)>',s); return (int(m.group(1)),int(m.group(2))) if m else None
def masks(im):
    im=im.astype(int); r,g,b=im[...,0],im[...,1],im[...,2]
    return {'red':(r>150)&(g<60)&(b<60),'green':(g>150)&(r<80)&(b<80),'blue':(b>150)&(r<60)&(g<60),
            'purple':(r>120)&(b>150)&(g<130)&(b-g>60)}
def blobs(m,minarea=15):
    n,l,st,c=cv2.connectedComponentsWithStats(m.astype(np.uint8),8)
    return [(float(c[i][1]),float(c[i][0]),int(st[i][4])) for i in range(1,n) if st[i][4]>=minarea]  # (row,col,area)
def cube_pos(im,color):
    b=blobs(masks(im)[color],8)
    if not b: return None
    b=max(b,key=lambda x:x[2]); return (round(b[0],1),round(b[1],1))
def targets(im):
    m=masks(im)['purple'].astype(np.uint8)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    return [(round(r,1),round(c,1),a) for r,c,a in blobs(m,30)]
def color_at(im,rc):
    r,c=rc; best=None
    for col in ('red','green','blue'):
        m=masks(im)[col][max(0,r-6):r+7,max(0,c-6):c+7].sum()
        if best is None or m>best[1]: best=(col,int(m))
    return best
def dist(a,b): return float(np.hypot(a[0]-b[0],a[1]-b[1]))
