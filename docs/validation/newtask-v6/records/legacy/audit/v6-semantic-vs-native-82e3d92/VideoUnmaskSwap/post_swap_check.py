import h5py, json, numpy as np
import importlib.util
spec=importlib.util.spec_from_file_location('cc','/dev/null')
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
import cv2
def masks(im):
    im=im.astype(int); r,g,b=im[...,0],im[...,1],im[...,2]; hi=90; lo=60
    return {'red':(r>hi)&(g<lo)&(b<lo),'green':(g>hi)&(r<lo)&(b<lo),'blue':(b>hi)&(r<lo)&(g<lo),
            'yellow':(r>120)&(g>120)&(b<60)&(np.abs(r-g)<40),'cyan':(g>hi)&(b>hi)&(r<lo),'magenta':(r>hi)&(b>hi)&(g<lo)}
out=[]
for r in json.load(open(E+'/raw_extract.json')):
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    first_exec=r['demo_last_step']+1
    res={}
    for t in [first_exec+2, first_exec+10]:
        im=g[f'timestep_{t}']['obs/front_rgb'][()]
        res[t]={k:int(v.sum()) for k,v in masks(im).items() if v.sum()>0}
    out.append(dict(tier=r['tier'],seed=r['seed'],colored_px=res)); print(r['tier'],r['seed'],res)
json.dump(out,open(E+'/post_swap_check.json','w'),indent=1)
