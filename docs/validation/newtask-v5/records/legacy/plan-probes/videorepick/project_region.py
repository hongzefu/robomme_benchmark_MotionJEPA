# 把 xhard 方块区域 / 按钮 / 6 个槽位投影到 front 相机像素（用 h5 里记录的内外参），量化「画面里占多大」
import h5py, numpy as np, json, sys, os
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(__file__))
from v4rep import v4_reset
H5 = "artifacts/newtask-v4/v4-01/rollout/run1/episodes/VideoRepick_episode_3/hdf5_files/VideoRepick_ep3_seed4900300.h5"
f = h5py.File(H5, "r"); ep = f["episode_3"]
K = np.asarray(ep["setup"]["front_camera_intrinsic"], dtype=np.float64)
E = np.asarray(ep["timestep_0"]["obs"]["front_camera_extrinsic"], dtype=np.float64)  # 3x4 world->cam (OpenCV)
img = np.asarray(ep["timestep_0"]["obs"]["front_rgb"])
print("K=", K.round(2).tolist()); print("E=", E.round(3).tolist())
def proj(xyz):
    xyz = np.atleast_2d(xyz); pc = (E[:, :3] @ xyz.T + E[:, 3:4]).T
    uv = (K @ pc.T).T; return uv[:, :2] / uv[:, 2:3], pc[:, 2]
lay = v4_reset(4900300)
uv, z = proj(np.array([[c[0], c[1], 0.02] for c in lay["cubes"]]))
print("cube px (u,v):", uv.round(1).tolist())
# 区域四角（方块中心可达区域 与 区域外廓）
def rect(cx, cy, hx, hy):
    return np.array([[cx-hx, cy-hy, 0], [cx-hx, cy+hy, 0], [cx+hx, cy+hy, 0], [cx+hx, cy-hy, 0]])
reg = rect(-0.1, 0, 0.2, 0.25)
uvr, _ = proj(reg); print("region corners px:", uvr.round(1).tolist())
# 可见桌面：在像素网格上反投影到 z=0 平面，统计落在桌面 [-0.7245,0.4845]x[-?]、以及落在区域内的像素比例
H, W = img.shape[:2]
R = E[:, :3]; t = E[:, 3]; Kinv = np.linalg.inv(K); C = -R.T @ t
us, vs = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
rays = (R.T @ (Kinv @ np.stack([us.ravel(), vs.ravel(), np.ones(us.size)]))).T
s = -C[2] / rays[:, 2]; pts = C + rays * s[:, None]
ground = s > 0
table = ground & (pts[:, 0] > -0.7245) & (pts[:, 0] < 0.4845) & (np.abs(pts[:, 1]) < 1.2)
inreg = table & (pts[:, 0] > -0.3) & (pts[:, 0] < 0.1) & (np.abs(pts[:, 1]) < 0.25)
print(f"image pixels on table={table.mean():.3f}  in xhard region={inreg.mean():.3f}  region/table={inreg.sum()/table.sum():.3f}")
vv = vs.ravel()
print("region pixel rows v in [%.0f, %.0f] of %d" % (vv[inreg].min(), vv[inreg].max(), H))
print("table x range visible: [%.3f, %.3f]" % (pts[table, 0].min(), pts[table, 0].max()))
# 画注释图
im = Image.fromarray(img).resize((512, 512), Image.NEAREST); d = ImageDraw.Draw(im)
q = [tuple((p * 2).tolist()) for p in uvr]; d.polygon(q, outline=(0, 255, 0))
bx, by = lay["button"]; ub, _ = proj(rect(bx, by, 0.05625 + 0.04, 0.05625 + 0.04)); d.polygon([tuple((p * 2).tolist()) for p in ub], outline=(255, 0, 255))
for i, (u, v) in enumerate(uv):
    d.text((u * 2 + 8, v * 2 - 6), f"bin_{i}", fill=(255, 255, 255))
out = os.path.join(os.path.dirname(__file__), "ep3_t0_annot.png"); im.save(out); print("saved", out)
