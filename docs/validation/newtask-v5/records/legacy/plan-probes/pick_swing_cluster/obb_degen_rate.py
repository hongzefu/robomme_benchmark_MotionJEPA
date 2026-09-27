"""复刻器（float32 位姿，与仓库一致）下立方体 2D OBB 退化率，及退化时沿哪个轴；并按 yaw 分箱。"""
import sys, math
sys.path.insert(0, sys.argv[1])
import numpy as np
from replica import cube_obb2d
rng = np.random.default_rng(1)
N = 4000
deg = []; yaws = rng.uniform(0, 2*math.pi, N)
for yaw in yaws:
    x, y = rng.uniform(-0.28, 0.08), rng.uniform(-0.18, 0.18)
    c, A, h = cube_obb2d(x, y, yaw)
    n = sorted([np.linalg.norm(A[:, 0]), np.linalg.norm(A[:, 1])])
    deg.append(n[0] < 0.5)
deg = np.array(deg)
print(f"N={N} degenerate_frac={deg.mean():.4f}")
bins = np.linspace(0, 2*math.pi, 13)
idx = np.digitize(yaws, bins) - 1
print("per 30deg yaw bin degenerate frac:", [round(float(deg[idx == b].mean()), 3) for b in range(12)])
# yaw 固定、位置不同：是否稳定
for yaw in [0.0, 0.3, 1.0, math.pi/4]:
    r = [min(np.linalg.norm(cube_obb2d(rng.uniform(-0.28, 0.08), rng.uniform(-0.18, 0.18), yaw)[1], axis=0)) < 0.5 for _ in range(200)]
    print(f"yaw={yaw:.3f} degenerate over 200 random xy: {np.mean(r):.3f}")
