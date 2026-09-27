# 步 9：推荐环带的按密度个数在 1 mm / 2 mm 网格下是否稳定（四舍五入边界检查）
import sys, math
import numpy as np
from scipy.ndimage import maximum_filter
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
CASES = {
    "VU": ((-0.2, 0.2, -0.2, 0.2), None),
    "BU": ((-0.2, 0.2, -0.2, 0.2), "bu"),
    "VUS": ((-0.2114, 0.2114, -0.2114, 0.2114), None),
    "BUS+btn": ((-0.2625, 0.17, -0.17, 0.27), "bus"),
    "BUS(no-btn)": ((-0.07, 0.17, -0.17, 0.27), "bus"),
}
for step in (0.002, 0.001):
    XS = np.arange(-0.6 + step / 2, 0.5, step); YS = np.arange(-0.6 + step / 2, 0.6, step)
    X, Y = np.meshgrid(XS, YS, indexing="ij")
    VIS = L.vis_center_exact(X, Y)
    K = int(round(2 * L.HALF / step)) + 1
    for name, (inner, fixed) in CASES.items():
        for g, W in ((0.015, 1 / math.sqrt(50)), (0.04, 1 / math.sqrt(50)), (0.015, 0.085)):
            ring = L.RectRing(inner, g + L.HALF, g + W - L.HALF)
            cb = ring.contains(X, Y) & VIS
            fpb = L.RectRing(inner, g, g + W).contains(X, Y)
            fp = (maximum_filter(cb.astype(np.uint8), size=K) > 0) & fpb
            rng = np.random.default_rng(1)
            blk = np.zeros_like(X)
            if fixed:
                nb = 300
                for _ in range(nb):
                    bases = [[-0.2, 0.0]] if fixed == "bu" else [[-0.2, -0.1], [-0.2, 0.1]]
                    rr = 0.1 if fixed == "bu" else 0.05
                    m = np.zeros_like(X, bool)
                    for base in bases:
                        c = np.array(base) + (rng.random(2) - 0.5) * rr
                        d = np.hypot(np.maximum(np.abs(X - c[0]) - L.BTN_HALF, 0), np.maximum(np.abs(Y - c[1]) - L.BTN_HALF, 0))
                        m |= d < L.HALF + 0.015
                    blk += m
                blk /= nb
            frac = float((blk * cb).sum() / cb.sum())
            A = fp.sum() * step * step * (1 - frac)
            print(f"grid {step*1000:.0f}mm {name:12s} g={g:.3f} W={W:.4f}: A_use={A:.4f} m², block={100*frac:.1f}%, ρA={50*A:.2f} → round {int(math.floor(50*A+0.5))}, floor {int(50*A)}")
