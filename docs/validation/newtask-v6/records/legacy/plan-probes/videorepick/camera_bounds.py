# 只读：用 v5-01 VideoRepick h5 的 front 相机内外参，反投影求桌面 z=0 上可见范围，并检查区域外扩后是否仍在画面内
import h5py, numpy as np, glob
p = glob.glob("artifacts/newtask-v5/v5-01/rollout/run1/episodes/VideoRepick_episode_0/hdf5_files/*.h5")[0]
with h5py.File(p, "r") as f:
    ep = f[list(f.keys())[0]]
    K = np.asarray(ep["setup"]["front_camera_intrinsic"], dtype=np.float64).reshape(3, 3)
    E = np.asarray(ep["timestep_0"]["obs"]["front_camera_extrinsic"], dtype=np.float64).reshape(-1, 4)[:3]
    img = np.asarray(ep["timestep_0"]["obs"]["front_rgb"]); H, W = img.shape[-3:-1]
def proj(xyz):
    pc = (E[:, :3] @ np.atleast_2d(xyz).T + E[:, 3:4]).T; uv = (K @ pc.T).T; return uv[:, :2] / uv[:, 2:3]
print("图像", W, "x", H)
for name, (cx, cy, hx, hy) in {"V5区域": (-0.1, 0, 0.2, 0.25), "外扩x+0.05": (-0.075, 0, 0.225, 0.25),
                               "外扩y±0.05": (-0.1, 0, 0.2, 0.30), "外扩y±0.10": (-0.1, 0, 0.2, 0.35),
                               "外扩x远端+0.1": (-0.05, 0, 0.25, 0.25)}.items():
    c = np.array([[cx - hx, cy - hy, 0.04], [cx - hx, cy + hy, 0.04], [cx + hx, cy + hy, 0.04], [cx + hx, cy - hy, 0.04],
                  [cx - hx, cy - hy, 0], [cx + hx, cy + hy, 0]])
    uv = proj(c); inside = (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
    print(f"{name}: 角点像素 {uv[:4].round(1).tolist()} 全在画面内={bool(inside.all())}")
# 画面内 z=0 可见 x、y 范围（逐像素反投影）
R = E[:, :3]; t = E[:, 3]; C = -R.T @ t; Kinv = np.linalg.inv(K)
us, vs = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
rays = (R.T @ (Kinv @ np.stack([us.ravel(), vs.ravel(), np.ones(us.size)]))).T
s = -C[2] / rays[:, 2]; pts = C + rays * s[:, None]; ok = s > 0
for yq in (0.0,):
    pass
X, Y = pts[ok, 0], pts[ok, 1]
print(f"画面内桌面可见 x∈[{X.min():.3f},{X.max():.3f}]（相机端到远端）")
for xq in (-0.3, -0.2, -0.1, 0.0, 0.1, 0.15):
    sel = np.abs(X - xq) < 0.005
    if sel.any(): print(f"  x={xq:+.2f} 处可见 y∈[{Y[sel].min():.3f},{Y[sel].max():.3f}]")
print("相机位置", C.round(3).tolist())
