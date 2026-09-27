# 抽查：Unmask 外环按密度推导的容器数（独立复算，2 mm 栅格）
import numpy as np
from scipy.ndimage import binary_dilation
from robomme.robomme_env.utils.unmask_distractors import visible_in_camera, bin_corners, bin_geometry
half, reach, h = bin_geometry(0.02)
print("bin_geometry", half, reach, h)
step = 0.002
xs = np.arange(-0.6, 0.5 + 1e-9, step); ys = np.arange(-0.6, 0.6 + 1e-9, step)
X, Y = np.meshgrid(xs, ys, indexing="ij")
vis = np.zeros(X.shape, bool)
cheb = np.maximum(np.abs(X), np.abs(Y))
cand = (cheb > 0.2) & (cheb < 0.46)
for i, j in zip(*np.nonzero(cand)):
    vis[i, j] = visible_in_camera(bin_corners(X[i, j], Y[i, j], reach, h))
def usable(r_in, r_out, inner=0.2):
    centres = vis & (cheb >= r_in) & (cheb <= r_out)
    k = int(round(half / step))
    fp = binary_dilation(centres, structure=np.ones((2 * k + 1, 2 * k + 1), bool))
    fp &= (cheb >= r_in - half) & (cheb <= r_out + half)
    return fp.sum() * step * step, centres.sum() * step * step
rho = 8 / 0.4 ** 2
for name, ring in [("V4 ring", (0.2675, 0.45)), ("ringA VU", (0.2425, 0.3289)), ("ringA VUS", (0.2539, 0.3403)), ("ringC", (0.2675, 0.3539))]:
    A, Ac = usable(*ring)
    print(f"{name} ring={ring} A_fp={A:.4f} m2  N=rho*A={rho*A:.2f}  (centre area {Ac:.4f})")
