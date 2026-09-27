# 步 4：机械臂/基座在初始姿态下对桌面的遮挡（用 V4 rollout 的 front_depth 实测，不起仿真）+ 各扇区容器像素尺寸
import sys, json, math, glob
import numpy as np, h5py
from PIL import Image
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
base = "artifacts/newtask-v4/v4-01/rollout/run1/episodes"
# 每个像素射线与 z=0 平面的交点与深度
uu, vv = np.meshgrid(np.arange(256) + 0.5, np.arange(256) + 0.5)
xr = (uu - 128) / 128 * L.TAN; yu = -(vv - 128) / 128 * L.TAN
dirs = L.FWD[None, None, :] + xr[..., None] * L.RIGHT + yu[..., None] * L.UP   # 每像素射线（前向分量=1）
t = -L.EYE[2] / dirs[..., 2]
plane = L.EYE + t[..., None] * dirs          # 桌面交点
plane_depth = t                               # 前向分量为 1 ⇒ t 即 z-depth（米）
print("plane depth at (0,0,0) pixel:", round(float(plane_depth[104, 127]), 4))
for env, ts in [("VideoUnmask", [0, 20]), ("ButtonUnmask", [0, 20]), ("VideoUnmaskSwap", [0, 20]), ("ButtonUnmaskSwap", [0, 20])]:
    fn = glob.glob(f"{base}/{env}_episode_0/hdf5_files/*.h5")[0]
    e = h5py.File(fn, "r")["episode_0"]
    for ti in ts:
        dep = e[f"timestep_{ti}/obs/front_depth"][()][..., 0].astype(float) / 1000.0
        above = (plane_depth - dep) > 0.005        # 比桌面近 5 mm 以上 ⇒ 有物体
        on_table = plane[..., 2] > -1   # all
        # 被遮挡的桌面点（仅统计桌面范围、x∈[-0.72,0.43]）
        P = plane[above]
        sel = (P[:, 0] > -0.7245) & (P[:, 0] < 0.4845)
        P = P[sel]
        print(f"{env} t={ti}: depth px unit check median table px depth {np.median(dep[~above]):.3f}; 物体像素 {int(above.sum())}; "
              f"被挡桌面点 x∈[{P[:,0].min():.3f},{P[:,0].max():.3f}] y∈[{P[:,1].min():.3f},{P[:,1].max():.3f}]" if len(P) else "none")
        if env == "VideoUnmask" and ti == 20:
            # 只取机器人：上方中心那一坨（v<40）
            rob = above & (vv < 40)
            Pr = plane[rob]
            print(f"   机器人遮挡的桌面区域（v<40 像素）: x∈[{Pr[:,0].min():.3f},{Pr[:,0].max():.3f}] y∈[{Pr[:,1].min():.3f},{Pr[:,1].max():.3f}]，像素数 {int(rob.sum())}")
            np.save(f"{S}/robot_occ_xy.npy", Pr[:, :2])
            eef = e[f"timestep_{ti}/obs/eef_state"][()]
            print("   eef_state (初始姿态)", np.round(eef, 4).tolist())

# 各扇区容器像素尺寸（真实外廓半边 0.03、高 0.052，yaw 0/45）
def bbox_px(x, y, yaw_deg):
    R = L.rot(math.radians(yaw_deg)); pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            o = R @ np.array([sx * 0.03, sy * 0.03])
            for z in (0, 0.052):
                pts.append([x + o[0], y + o[1], z])
    u, v, _ = L.project(np.array(pts))
    return u.max() - u.min(), v.max() - v.min(), (u.min(), u.max(), v.min(), v.max())
print("\n容器像素尺寸（宽×高，px；yaw0 / yaw45）")
for name, (x, y) in {"inner center (0,0)": (0, 0), "inner far corner (-0.17,±0.17)": (-0.1725, 0.1725), "inner near corner (+0.17,±0.17)": (0.1725, 0.1725),
                     "ring far side (-0.29,0)": (-0.2857, 0), "ring far corner (-0.33,0.33)": (-0.3289, 0.3289), "ring y side (0,0.29)": (0, 0.2857),
                     "ring near side (+0.29,0)": (0.2857, 0), "ring near corner (+0.25,0.25)": (0.25, 0.25),
                     "V4 far corner (-0.45,0.45)": (-0.45, 0.45), "V4 far side (-0.45,0)": (-0.45, 0)}.items():
    w0, h0, _ = bbox_px(x, y, 0); w1, h1, _ = bbox_px(x, y, 45)
    print(f"  {name:32s} {w0:5.1f}×{h0:4.1f} / {w1:5.1f}×{h1:4.1f}")
