# 步 2：内部密度 + 各环带方案的可用面积与按密度推出的个数（纯几何，网格 2 mm）
import sys, json, math
import numpy as np
from scipy.ndimage import maximum_filter
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L

STEP = 0.002
XS = np.arange(-0.9 + STEP / 2, 0.6, STEP); YS = np.arange(-0.9 + STEP / 2, 0.9, STEP)
X, Y = np.meshgrid(XS, YS, indexing="ij")
DA = STEP * STEP
VIS = L.vis_center_exact(X, Y)
K = int(round(2 * L.HALF / STEP)) + 1   # 采样外廓方块（半边 0.0275）的膨胀核

# ── 内部密度 ──
dens = {
    "VU/BU region (0.4x0.4, 8 bins)": 8 / 0.16,
    "VU/BU center-sampling box (0.345^2)": 8 / 0.345 ** 2,
    "BU region minus mean button overlap": None,
    "Swap per-episode union of 4 anchor boxes (4*0.14^2)": 4 / (4 * 0.14 ** 2),
    "VUS per-episode anchor bbox local (0.29x0.34)": 4 / (0.29 * 0.34),
    "BUS per-episode anchor bbox mean (0.24x(0.34+E|o1-o2|))": 4 / (0.24 * (0.34 + 0.1 / 3)),
    "VUS static envelope (disc r=0.1414 ⊕ square 0.07)": 4 / (math.pi * 0.1414 ** 2 + 8 * 0.1414 * 0.07 + 4 * 0.07 ** 2),
    "BUS static bbox (0.24x0.44)": 4 / (0.24 * 0.44),
}
rng = np.random.default_rng(3)
ov = []
for _ in range(20000):
    c = np.array([-0.2, 0.0]) + (rng.random(2) - 0.5) * 0.1
    x0, x1 = max(c[0] - L.BTN_HALF, -0.2), min(c[0] + L.BTN_HALF, 0.2)
    y0, y1 = max(c[1] - L.BTN_HALF, -0.2), min(c[1] + L.BTN_HALF, 0.2)
    ov.append(max(0, x1 - x0) * max(0, y1 - y0))
dens["BU region minus mean button overlap"] = 8 / (0.16 - float(np.mean(ov)))
print("== 内部密度（个/m²）==")
for k, v in dens.items():
    print(f"  {k}: {v:.2f}")

INNER = {
    "VU": (-0.2, 0.2, -0.2, 0.2),
    "BU": (-0.2, 0.2, -0.2, 0.2),
    "VUS": (-0.2114, 0.2114, -0.2114, 0.2114),        # 旋转包络的切比雪夫外接方
    "BUS": (-0.07, 0.17, -0.17, 0.27),                # 锚点盒并集（含 y 偏移）的外接矩形，不含按钮
    "BUS+btn": (-0.2625, 0.17, -0.17, 0.27),          # 把两按钮（底座物理范围）也算进内部范围
}


def blocked_mask(env, rng, n=200):
    """固定物（按钮）挡掉的中心点的「平均」比例图：VU/BU 判据 dist(中心, 按钮OBB) < 0.0275+0.015；Swap 判据用外接圆。"""
    if env == "BU":
        acc = np.zeros_like(X)
        for _ in range(n):
            c = np.array([-0.2, 0.0]) + (rng.random(2) - 0.5) * 0.1
            d = np.hypot(np.maximum(np.abs(X - c[0]) - L.BTN_HALF, 0), np.maximum(np.abs(Y - c[1]) - L.BTN_HALF, 0))
            acc += d < L.HALF + 0.015
        return acc / n
    if env.startswith("BUS"):
        acc_obb = np.zeros_like(X); acc_circ = np.zeros_like(X)
        for _ in range(n):
            for base in ([-0.2, -0.1], [-0.2, 0.1]):
                c = np.array(base) + (rng.random(2) - 0.5) * 0.05
                d = np.hypot(np.maximum(np.abs(X - c[0]) - L.BTN_HALF, 0), np.maximum(np.abs(Y - c[1]) - L.BTN_HALF, 0))
                acc_obb += d < L.HALF + 0.015
                acc_circ += np.hypot(X - c[0], Y - c[1]) < L.BTN_HALF * math.sqrt(2) + L.SWAP_R + 0.04
        return np.minimum(acc_obb / n, 1.0)   # 近似：两按钮不重叠
    return np.zeros_like(X)


rows = []
rng = np.random.default_rng(5)
for env, inner in INNER.items():
    ring0 = L.RectRing(inner, 0, 0)
    cheb = ring0.cheb(X, Y)
    blk = blocked_mask(env, rng)
    for g in (0.0, 0.015, 0.04):
        for W in (0.07, 0.085, 0.1, 0.1414, 0.17, 0.2):
            if W < 2 * L.HALF + 1e-9:
                continue
            cband = (cheb >= g + L.HALF) & (cheb <= g + W - L.HALF)
            fpband = (cheb >= g) & (cheb <= g + W)
            usable_c = cband & VIS
            A_fp = fpband.sum() * DA
            # 可用外廓面积：可用中心的采样外廓方块并集（期望意义下按按钮遮挡概率加权）
            fp_vis = maximum_filter(usable_c.astype(np.uint8), size=K) > 0
            fp_vis &= fpband
            A_fp_vis = fp_vis.sum() * DA
            # 按钮遮挡：中心被挡的期望比例，外廓面积按同比例扣
            frac_blk = float((blk * usable_c).sum() / max(usable_c.sum(), 1))
            A_fp_use = A_fp_vis * (1 - frac_blk)
            A_c = cband.sum() * DA; A_c_vis = usable_c.sum() * DA
            rows.append(dict(env=env, g=g, W=W, centers=[round(g + L.HALF, 4), round(g + W - L.HALF, 4)],
                             A_fp=A_fp, A_fp_vis=A_fp_vis, vis_frac=A_fp_vis / A_fp, btn_block_frac=frac_blk,
                             A_fp_use=A_fp_use, N50=50 * A_fp_use, A_c=A_c, A_c_vis=A_c_vis, N67c=8 / 0.345 ** 2 * A_c_vis * (1 - frac_blk)))
# V4 现环（对照）
for env in ("VU",):
    ring = L.RectRing((0, 0, 0, 0), 0.2675, 0.45)
    cb = ring.contains(X, Y) & VIS
    fp = maximum_filter(cb.astype(np.uint8), size=K) > 0
    fp &= (ring0 := L.RectRing((0, 0, 0, 0), 0.24, 0.4775)).contains(X, Y)
    print(f"\nV4 现环 [0.2675,0.45]：中心带可见面积 {cb.sum()*DA:.4f} m²，外廓可见面积 {fp.sum()*DA:.4f} m² ⇒ 50/m² 对应 {50*fp.sum()*DA:.1f} 个")
print("\n== 环带方案（g=区域边到环外廓内沿的间隙，W=外廓带宽；centers=中心的切比雪夫距离范围）==")
print("env      g     W      centers           A_fp   A_fp_vis vis%  btn%  A_use   N(50/m²)  N(center-conv)")
for r in rows:
    print(f"{r['env']:8s} {r['g']:.3f} {r['W']:.4f} {str(r['centers']):18s} {r['A_fp']:.4f} {r['A_fp_vis']:.4f} {100*r['vis_frac']:5.1f} {100*r['btn_block_frac']:5.1f} {r['A_fp_use']:.4f} {r['N50']:6.2f}   {r['N67c']:6.2f}")
json.dump(rows, open(f"{S}/s2_rows.json", "w"), indent=1)
