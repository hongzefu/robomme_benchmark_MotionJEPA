# 抽查：立方体经 trimesh bounding_box_oriented → _trimesh_box_to_obb2d 的退化率
import numpy as np, trimesh
from robomme.robomme_env.utils.object_generation import _trimesh_box_to_obb2d
rng = np.random.default_rng(0)
deg = 0; N = 2000; minsv = []
for _ in range(N):
    yaw = rng.uniform(0, 2*np.pi); x, y = rng.uniform(-0.2, 0.2, 2)
    c, s = np.cos(yaw), np.sin(yaw)
    T = np.eye(4, dtype=np.float32); T[:3,:3] = np.array([[c,-s,0],[s,c,0],[0,0,1]], np.float32); T[:3,3] = [x, y, 0.02]
    m = trimesh.creation.box(extents=[0.04]*3); m.apply_transform(T.astype(np.float64))
    obb = m.bounding_box_oriented
    cc, A, h = _trimesh_box_to_obb2d(obb)
    sv = np.linalg.svd(A, compute_uv=False).min()
    minsv.append(sv); deg += sv < 1e-3
print(f"degenerate {deg}/{N} = {deg/N:.3f}")
