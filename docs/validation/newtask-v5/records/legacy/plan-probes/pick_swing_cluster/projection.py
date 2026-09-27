"""用 h5 里的 front_camera_extrinsic（cv 约定）+ fov=pi/2、256x256 内参，把桌面点投到 front_rgb 像素。
核对：把 PickXtimes ep3 各方块中心投影出来，与首帧里的色块位置比对。"""
import h5py, numpy as np, glob, json, math
f = glob.glob("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes/PickXtimes_episode_3/hdf5_files/*.h5")[0]
h = h5py.File(f, "r"); g = h[list(h.keys())[0]]
E = np.array(g["timestep_0"]["obs"]["front_camera_extrinsic"]).reshape(-1, 4)[:3]
print("extrinsic\n", E.round(3))
K = np.array([[128, 0, 128], [0, 128, 128], [0, 0, 1.0]])
def proj(x, y, z=0.02):
    pc = E @ np.array([x, y, z, 1.0]); uv = K @ pc
    return uv[:2] / uv[2]
# ep3 实际布局
L = {"blue": (-0.009, 0.136), "green": (0.063, -0.153), "red": (0.067, 0.066), "cyan": (0.024, -0.027),
     "magenta": (-0.128, -0.041), "yellow": (-0.253, 0.016), "disk": (-0.217, 0.139), "button": (-0.22, -0.179)}
for k, (x, y) in L.items():
    u, v = proj(x, y); print(f"{k:8s} world=({x:+.3f},{y:+.3f}) -> px(u={u:.1f}, v={v:.1f}) [x3 upscale: {3*u:.0f},{3*v:.0f}]")
# 区域四角
for name, (xl, xh, yl, yh) in {"Pick region(0.4x0.4)": (-0.3, 0.1, -0.2, 0.2), "Swing region(0.5x0.5)": (-0.35, 0.15, -0.25, 0.25)}.items():
    pts = [proj(a, b, 0.0) for a in (xl, xh) for b in (yl, yh)]
    us = [p[0] for p in pts]; vs = [p[1] for p in pts]
    # 四边形面积（鞋带公式，按顺序 xl-yl, xl-yh, xh-yh, xh-yl）
    q = [proj(xl, yl, 0), proj(xl, yh, 0), proj(xh, yh, 0), proj(xh, yl, 0)]
    area = 0.5 * abs(sum(q[i][0] * q[(i + 1) % 4][1] - q[(i + 1) % 4][0] * q[i][1] for i in range(4)))
    print(f"{name}: u∈[{min(us):.0f},{max(us):.0f}] v∈[{min(vs):.0f},{max(vs):.0f}] area={area:.0f}px² = {area/65536*100:.1f}% of 256x256")
# 同样 6cm / 10cm 物理间距在近机器人端与近相机端的像素长度
for x in (-0.28, -0.1, 0.08):
    for d in (0.06, 0.10):
        du = np.linalg.norm(proj(x, 0.0) - proj(x, d)); dv = np.linalg.norm(proj(x, 0.0) - proj(x + d, 0.0))
        print(f"x={x:+.2f}: {d*100:.0f}cm along y = {du:.1f}px ; along x = {dv:.1f}px")
