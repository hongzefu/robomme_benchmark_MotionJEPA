"""独立于此前审查脚本，重新用简单颜色阈值定位红方块中心，核对 home 返回段前后位置是否吻合。"""
import h5py
import numpy as np
from PIL import Image

h5path = '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/VideoPlaceButton_episode_0/hdf5_files/VideoPlaceButton_ep0_seed9000000.h5'
f = h5py.File(h5path, 'r')
ep = f[next(iter(f))]

def red_centroid(frame):
    r, g, b = frame[..., 0].astype(int), frame[..., 1].astype(int), frame[..., 2].astype(int)
    mask = (r > 120) & (r - g > 40) & (r - b > 40)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return None, 0
    return (float(ys.mean()), float(xs.mean())), int(mask.sum())

# 起点：t=0（第一次 pick up 之前，方块仍在初始位姿）
f0 = ep['timestep_0']['obs/front_rgb'][()]
c0, n0 = red_centroid(f0)
# home 返回段结束帧：t=840（'static' 段起点 841 的前一帧，drop 已完成）
f_end = ep['timestep_840']['obs/front_rgb'][()]
c_end, n_end = red_centroid(f_end)
# 对照：home 段刚开始时（cube 仍被抓在手上，t=756附近，应远离起点）
f_mid = ep['timestep_756']['obs/front_rgb'][()]
c_mid, n_mid = red_centroid(f_mid)

print('t0_center=', c0, 'pixels=', n0)
print('t756_center(during pick, cube in gripper start of home move)=', c_mid, 'pixels=', n_mid)
print('t840_center(end of home segment)=', c_end, 'pixels=', n_end)
if c0 and c_end:
    d = ((c0[0]-c_end[0])**2 + (c0[1]-c_end[1])**2) ** 0.5
    print('DIST_T0_T840=', d)

Image.fromarray(f0).save('artifacts/audit/v6-semantic-vs-native-82e3d92/verify/VideoPlaceButton-03/frame_t0.png')
Image.fromarray(f_end).save('artifacts/audit/v6-semantic-vs-native-82e3d92/verify/VideoPlaceButton-03/frame_t840.png')
