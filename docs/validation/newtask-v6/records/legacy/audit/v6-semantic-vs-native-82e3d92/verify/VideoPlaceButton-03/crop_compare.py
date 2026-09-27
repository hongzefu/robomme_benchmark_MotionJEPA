import h5py
import numpy as np
from PIL import Image

h5path = '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/VideoPlaceButton_episode_0/hdf5_files/VideoPlaceButton_ep0_seed9000000.h5'
f = h5py.File(h5path, 'r')
ep = f[next(iter(f))]

def crop(t, cy, cx, half=30):
    frame = ep[f'timestep_{t}']['obs/front_rgb'][()]
    y0, y1 = max(0, cy-half), min(256, cy+half)
    x0, x1 = max(0, cx-half), min(256, cx+half)
    return frame[y0:y1, x0:x1]

# 初始 pick 坐标来自 env 自身 segmentation 输出：'pick up the cube at <116, 138>'
c0 = crop(0, 116, 138)
c840 = crop(840, 116, 138)
canvas = Image.new('RGB', (120, 60), 'white')
canvas.paste(Image.fromarray(c0).resize((60,60)), (0,0))
canvas.paste(Image.fromarray(c840).resize((60,60)), (60,0))
canvas.save('artifacts/audit/v6-semantic-vs-native-82e3d92/verify/VideoPlaceButton-03/crop_t0_vs_t840.png')

# 用红色掩膜在局部窗口内找质心，窗口小、干扰少
def red_centroid_local(t, cy, cx, half=40):
    frame = ep[f'timestep_{t}']['obs/front_rgb'][()]
    y0, y1 = max(0, cy-half), min(256, cy+half)
    x0, x1 = max(0, cx-half), min(256, cx+half)
    patch = frame[y0:y1, x0:x1].astype(int)
    r, g, b = patch[...,0], patch[...,1], patch[...,2]
    mask = (r > 100) & (r - g > 60) & (r - b > 60)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return None, 0
    return (float(ys.mean()) + y0, float(xs.mean()) + x0), int(mask.sum())

c0_center, n0 = red_centroid_local(0, 116, 138)
c840_center, n840 = red_centroid_local(840, 116, 138)
print('local_t0_center=', c0_center, 'px=', n0)
print('local_t840_center=', c840_center, 'px=', n840)
if c0_center and c840_center:
    d = ((c0_center[0]-c840_center[0])**2 + (c0_center[1]-c840_center[1])**2) ** 0.5
    print('LOCAL_DIST=', d)
