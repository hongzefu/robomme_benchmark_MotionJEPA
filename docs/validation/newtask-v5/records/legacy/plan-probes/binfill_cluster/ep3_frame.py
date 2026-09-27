# 取 BinFill ep3 第一帧 front_rgb，按 extrinsic/intrinsic 把 spec 里 12 块方块、按钮、孔板投影上去
import json, h5py, numpy as np
from PIL import Image, ImageDraw
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
OUT='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
f=h5py.File(f'{ROOT}/artifacts/newtask-v4/v4-01/rollout/run1/episodes/BinFill_episode_3/hdf5_files/BinFill_ep3_seed4400300.h5','r')
g=f['episode_3']
ts=g['timestep_0']
rgb=ts['obs/front_rgb'][()]
E=ts['obs/front_camera_extrinsic'][()].astype(np.float64)
K=g['setup/front_camera_intrinsic'][()].astype(np.float64)
print('extrinsic\n',E)
Image.fromarray(rgb).save(f'{OUT}/ep3_frame0_raw.png')
rows=[json.loads(l) for l in open(f'{ROOT}/scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
r=[x for x in rows if x.get('task')=='BinFill' and x['seed']==4400300][0]['spec']
cubes=r['layout']['cubes']
def proj(p):
    pc=E[:, :3]@np.asarray(p)+E[:,3]
    # OpenCV 约定：z 前
    uv=K@pc
    return uv[:2]/uv[2], pc
big=Image.fromarray(rgb).resize((768,768),Image.NEAREST)
d=ImageDraw.Draw(big)
col={'red':(255,255,255),'blue':(255,255,0),'green':(255,0,255)}
for k,(x,y,yaw) in cubes.items():
    (u,v),pc=proj([x,y,0.02])
    print(k, round(x,3), round(y,3), 'uv', np.round([u,v],1), 'depth', round(pc[2],3))
    U,V=u*3,v*3
    d.ellipse([U-6,V-6,U+6,V+6],outline=col[k.split('_')[0]],width=2)
    d.text((U+7,V-7),k,fill=(255,255,255))
bx,by=r['layout']['button_xy']
(u,v),_=proj([bx,by,0.0]); d.rectangle([u*3-8,v*3-8,u*3+8,v*3+8],outline=(0,255,255),width=2); d.text((u*3+9,v*3),'button',fill=(0,255,255))
off=r['layout']['board']['offsets']; bx2,by2=0.15+off[0],off[1]
(u,v),_=proj([bx2,by2,0.0]); d.rectangle([u*3-8,v*3-8,u*3+8,v*3+8],outline=(255,128,0),width=2); d.text((u*3+9,v*3),'board',fill=(255,128,0))
# 方块区域四角
for cx,cy in [(-0.3,-0.25),(-0.3,0.25),(0.1,0.25),(0.1,-0.25)]:
    (u,v),_=proj([cx,cy,0.0]); d.ellipse([u*3-3,v*3-3,u*3+3,v*3+3],fill=(255,255,255))
big.save(f'{OUT}/ep3_frame0_annot.png')
