# 纯几何复刻库（不起 sapien）：Unmask 族 xhard 干扰容器外环分析（V5 计划调研，只读）
# 判据逐条对齐：
#   utils/unmask_distractors.py::spawn_ring_distractor_bins / visible_in_camera / bin_corners / bin_geometry / _hits
#   utils/unmask_swap_xhard.py::sample_distractors / visible_on_camera / bin_footprint_radius / predict_swap_sweeps
#   utils/object_generation.py::spawn_random_bin / build_button / create_button_obb
#   utils/bin_collision.py::check_swap_sweep（直接 import 源码函数，纯 numpy）
import importlib.util
import math
import sys

import numpy as np

REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, f"{REPO}/{rel}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bc = _load("bc_mod", "src/robomme/robomme_env/utils/bin_collision.py")

CHS = 0.02                                   # PICK_CUBE_CONFIGS['panda']['cube_half_size']
HALF = (CHS * 2.5 + 0.005) * 0.5             # 0.0275 spawn_random_bin 采样判据半边
OBB_HALF = 0.03                              # 容器 actor 的 trimesh OBB XY 半边（G2 实测）
REACH = (CHS * 2.5 * 0.5 + 0.005) * math.sqrt(2.0)   # 0.042426 bin_geometry 任意 yaw 外接半边
HEIGHT = 0.004 + CHS * 2.5                   # 0.054 bin_geometry 高度
SWAP_R = HALF * math.sqrt(2.0)               # 0.038891 unmask_swap_xhard.bin_footprint_radius
BTN_HALF = 0.025 * 1.5 * 1.5                 # 0.05625 create_button_obb 半边（build_button scale=1.5）
BTN_BASE_HALF = 0.025 * 1.5                  # 0.0375 按钮底座物理半边

EYE = np.array([0.3, 0.0, 0.4])
TARGET = np.array([0.0, 0.0, -0.2])
FWD = (TARGET - EYE) / np.linalg.norm(TARGET - EYE)
RIGHT = np.cross(FWD, [0, 0, 1.0]); RIGHT /= np.linalg.norm(RIGHT)
UP = np.cross(RIGHT, FWD)
TAN = math.tan(math.pi / 4)
RES = 256


def project(pts):
    """世界点 (...,3) → 像素 (u, v)（与 h5 里 front_camera_intrinsic/extrinsic 一致：K=[[128,0,128],[0,128,128]]）。"""
    d = np.asarray(pts, float) - EYE
    depth = d @ FWD
    xr = (d @ RIGHT) / depth
    yu = (d @ UP) / depth
    u = 128 + 128 * xr / TAN
    v = 128 - 128 * yu / TAN
    return u, v, depth


def vis_center_exact(x, y, reach=REACH, height=HEIGHT, margin_px=0.0):
    """unmask_distractors.visible_in_camera(bin_corners(x,y,reach,height)) 的向量化复刻。"""
    x = np.asarray(x, float); y = np.asarray(y, float)
    ok = np.ones(np.broadcast(x, y).shape, bool)
    limit = 1.0 - 2.0 * margin_px / RES
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.0, height):
                p = np.stack(np.broadcast_arrays(x + sx * reach, y + sy * reach, np.full_like(x, z)), -1)
                d = p - EYE
                depth = d @ FWD
                ok &= depth > 1e-6
                ok &= np.abs((d @ RIGHT) / depth) / TAN <= limit
                ok &= np.abs((d @ UP) / depth) / TAN <= limit
    return ok


def vis_center_swap(x, y, radius=SWAP_R):
    """unmask_swap_xhard.visible_on_camera 的向量化复刻（线性近似）。"""
    x = np.asarray(x, float); y = np.asarray(y, float)
    far_x = x + radius
    return (far_x <= 0.43) & (np.abs(y) + radius <= 0.49 - 0.45 * far_x)


def rot(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def dist_to_obbs(p, obbs):
    """p (K,2) 到每个 OBB 的最近点距离的最小值 (K,)。_hits / spawn_random_bin 同一判据。"""
    p = np.atleast_2d(p)
    best = np.full(p.shape[0], np.inf)
    for c, A, h in obbs:
        loc = (p - c) @ A          # A^T (p-c)
        d = np.linalg.norm(np.maximum(np.abs(loc) - h, 0.0), axis=1)
        best = np.minimum(best, d)
    return best


# ─────────────────── 区域内容器（VideoUnmask / ButtonUnmask xhard：N=8，factor 0.75） ───────────────────
def inner_unmask(rng, n=8, region_half=0.2, gap=CHS * 0.75, max_trials=256, button=False):
    """返回 (bins[(xy,yaw_rad)], button_center 或 None, obbs)；放不满返回 None（xhard 抛 SceneGenerationError）。"""
    obbs = []
    bcen = None
    if button:
        bcen = np.array([-0.2, 0.0]) + (rng.random(2) - 0.5) * 0.1
        obbs.append((bcen, np.eye(2), np.array([BTN_HALF, BTN_HALF])))
    lo, hi = -region_half + HALF, region_half - HALF
    bins = []
    thr = HALF + gap
    for _ in range(n):
        cand = rng.random((max_trials, 2)) * (hi - lo) + lo
        ok = dist_to_obbs(cand, obbs) >= thr if obbs else np.ones(max_trials, bool)
        idx = np.flatnonzero(ok)
        if idx.size == 0:
            return None
        p = cand[idx[0]]
        yaw = math.radians(rng.random() * 90.0)
        bins.append((p, yaw))
        obbs.append((p, rot(yaw), np.array([OBB_HALF + gap] * 2)))
    return bins, bcen, obbs


# ─────────────────── 两个 Swap 环境的区域内 4 个容器 ───────────────────
VUS_REGION4 = np.array([[-0.05, -0.1], [-0.05, 0.1], [0.1, 0.1], [0.1, -0.1]])


def inner_vus(rng, max_trials=256):
    """VideoUnmaskSwap xhard：region4 绕原点旋转 angle~U[0,180) 弧度，逐锚点 spawn_random_bin(half 0.07, gap 0.02)。"""
    angle = rng.random() * 180.0
    R = rot(angle)
    anchors = VUS_REGION4 @ R.T
    obbs, bins = [], []
    gap = CHS * 1.0
    thr = HALF + gap
    for a in anchors:
        lo, hi = a - 0.07 + HALF, a + 0.07 - HALF
        cand = rng.random((max_trials, 2)) * (hi - lo) + lo
        ok = dist_to_obbs(cand, obbs) >= thr if obbs else np.ones(max_trials, bool)
        idx = np.flatnonzero(ok)
        if idx.size == 0:
            return None
        p = cand[idx[0]]
        yaw = math.radians(rng.random() * 90.0)
        bins.append((p, yaw))
        obbs.append((p, rot(yaw), np.array([OBB_HALF + gap] * 2)))
    return bins, None, obbs, angle


def inner_bus(rng, max_trials=256):
    """ButtonUnmaskSwap xhard：两按钮（中心 [-0.2,∓0.1] + (U-0.5)*0.05），four_point 锚点 + y 偏移 U*0.1（不旋转）。"""
    b1 = np.array([-0.2, -0.1]) + (rng.random(2) - 0.5) * 0.05
    b2 = np.array([-0.2, 0.1]) + (rng.random(2) - 0.5) * 0.05
    o1, o2 = rng.random() * 0.1, rng.random() * 0.1
    rng.random(6)   # 三角/直线的 6 个 x 偏移照常消费（R8），与布局无关
    anchors = np.array([[0, -0.1 + o1], [0, 0.1 + o1], [0.1, 0.1 + o2], [0.1, -0.1 + o2]])
    obbs = [(b1, np.eye(2), np.array([BTN_HALF] * 2))]   # avoid=[button_obb_1]（源码只把第一个按钮放进 avoid）
    bins = []
    gap = CHS * 1.0
    thr = HALF + gap
    for a in anchors:
        lo, hi = a - 0.07 + HALF, a + 0.07 - HALF
        cand = rng.random((max_trials, 2)) * (hi - lo) + lo
        ok = dist_to_obbs(cand, obbs) >= thr
        idx = np.flatnonzero(ok)
        if idx.size == 0:
            return None
        p = cand[idx[0]]
        yaw = math.radians(rng.random() * 90.0)
        bins.append((p, yaw))
        obbs.append((p, rot(yaw), np.array([OBB_HALF + gap] * 2)))
    return bins, (b1, b2), obbs, (o1, o2)


def swap_initiators(rng):
    t = list(rng.permutation(3)[:2])
    rem = [i for i in range(4) if i not in t]
    third = rem[rng.integers(len(rem))]
    return [int(t[0]), int(t[1]), int(third)]


def predict_sweeps(bins, initiators, n_swaps):
    """utils/unmask_swap_xhard.predict_swap_sweeps 的无 actor 版（同一语义：发起者循环、XY 最近邻严格小于、段后互换）。"""
    shapes = bc.bin_shape_specs(CHS)
    states = []
    for i, (p, yaw) in enumerate(bins):
        pp, qq = bc.bin_actor_pose(p, math.degrees(yaw), CHS)
        states.append(bc.ObjectState(name=f"bin_{i}", p=pp, q=qq, shapes=shapes))
    pos = [np.asarray(p, float).copy() for p, _ in bins]
    sweeps = []
    for k in range(n_swaps):
        a = initiators[k % 3]
        b, best = None, float("inf")
        for j, q in enumerate(pos):
            if j == a:
                continue
            d = float(np.linalg.norm(pos[a] - q))
            if d < best:
                b, best = j, d
        sweeps.append((states[a], states[b]))
        sa, sb = states[a], states[b]
        states[a] = bc.ObjectState(name=sa.name, p=sb.p.copy(), q=sb.q.copy(), shapes=sa.shapes)
        states[b] = bc.ObjectState(name=sb.name, p=sa.p.copy(), q=sa.q.copy(), shapes=sb.shapes)
        pos[a], pos[b] = pos[b].copy(), pos[a].copy()
    return sweeps


def sweep_hits(xy, yaw_deg, sweeps):
    shapes = bc.bin_shape_specs(CHS)
    p, q = bc.bin_actor_pose(xy, yaw_deg, CHS)
    cand = bc.ObjectState(name="d", p=p, q=q, shapes=shapes)
    for k, (a, b) in enumerate(sweeps):
        if bc.check_swap_sweep(a, b, [cand], sweep_index=k, stage="distractor")[1] is not None:
            return True
    return False


# ─────────────────── 环带定义 ───────────────────
class RectRing:
    """中心落在「内矩形按切比雪夫距离外扩 [d_in, d_out]」的矩形环带里。
    inner = (xmin, xmax, ymin, ymax)。V4 的 max(|x|,|y|)∈[a,b] 等价于 inner=(0,0,0,0)、d=[a,b]。"""

    def __init__(self, inner, d_in, d_out):
        self.inner = tuple(float(v) for v in inner)
        self.d_in, self.d_out = float(d_in), float(d_out)

    def cheb(self, x, y):
        x0, x1, y0, y1 = self.inner
        dx = np.maximum(np.maximum(x0 - x, x - x1), 0.0)
        dy = np.maximum(np.maximum(y0 - y, y - y1), 0.0)
        return np.maximum(dx, dy)

    def contains(self, x, y):
        c = self.cheb(np.asarray(x, float), np.asarray(y, float))
        return (c >= self.d_in) & (c <= self.d_out)

    def bbox(self):
        x0, x1, y0, y1 = self.inner
        return (x0 - self.d_out, x1 + self.d_out, y0 - self.d_out, y1 + self.d_out)


def grid(bbox, step=0.002):
    x0, x1, y0, y1 = bbox
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    return X, Y, step * step


# ─────────────────── 外环放置复刻 ───────────────────
def place_ring_unmask(rng, ring, n, obbs_inner, gap=CHS * 0.75, max_trials=256, vis=vis_center_exact,
                      stop_on_fail=True):
    """spawn_ring_distractor_bins 的复刻（环带谓词换成 ring.contains；拒绝采样在 ring.bbox() 上均匀抽）。
    返回 (placed[(xy,yaw)], trials_used_list, fail_index 或 None)。"""
    x0, x1, y0, y1 = ring.bbox()
    obbs = list(obbs_inner)
    thr = HALF + gap
    placed, used = [], []
    for i in range(n):
        u = rng.random((max_trials, 2))
        cand = np.stack([x0 + u[:, 0] * (x1 - x0), y0 + u[:, 1] * (y1 - y0)], 1)
        ok = ring.contains(cand[:, 0], cand[:, 1])
        ok &= vis(cand[:, 0], cand[:, 1])
        ok &= dist_to_obbs(cand, obbs) >= thr
        idx = np.flatnonzero(ok)
        if idx.size == 0:
            if stop_on_fail:
                return placed, used, i
            continue
        p = cand[idx[0]]
        used.append(int(idx[0]) + 1)
        yaw = math.radians(rng.random() * 90.0)
        placed.append((p, yaw))
        obbs.append((p, rot(yaw), np.array([OBB_HALF + gap] * 2)))
    return placed, used, None


def place_ring_swap(rng, ring, n, circles, sweeps, min_gap=0.04, max_trials=512, vis=vis_center_swap,
                    stop_on_fail=True, count_sweep_rejects=None):
    """sample_distractors 的复刻（每次尝试抽 x,y,yaw；外接圆避让 + 预演扫掠拒绝）。"""
    x0, x1, y0, y1 = ring.bbox()
    occ = [(np.asarray(c, float), float(r)) for c, r in circles]
    placed, used = [], []
    for i in range(n):
        chosen = None
        for t in range(max_trials):
            u = rng.random(3)
            x = x0 + u[0] * (x1 - x0); y = y0 + u[1] * (y1 - y0); yaw = u[2] * 90.0
            if not ring.contains(x, y):
                continue
            if not vis(x, y):
                continue
            here = np.array([x, y])
            if any(np.linalg.norm(here - c) < r + SWAP_R + min_gap for c, r in occ):
                continue
            if sweeps and sweep_hits([x, y], yaw, sweeps):
                if count_sweep_rejects is not None:
                    count_sweep_rejects[0] += 1
                continue
            chosen = (here, math.radians(yaw)); used.append(t + 1)
            break
        if chosen is None:
            if stop_on_fail:
                return placed, used, i
            continue
        placed.append(chosen)
        occ.append((chosen[0], SWAP_R))
    return placed, used, None


# ─────────────────── 扫掠的快速近似（抽样 SAT，XY 平面；容器同高 ⇒ XY 重叠即三维相交） ───────────────────
NS = 121


def sweep_samples(sweeps, ns=NS):
    """把每段交换的两个移动容器在 s∈[0,1] 上抽 ns 个位姿：返回 (centers (M,2), axes (M,2,2))。
    路径与四元数混合逐字按 bin_collision._Mover.pose_at / _quat_at。"""
    cs, As = [], []
    ss = np.linspace(0, 1, ns)
    for a, b in sweeps:
        axy, bxy = a.p[:2], b.p[:2]
        delta, normal = bc._lane_endpoints(axy, bxy)
        for xy0, sign, q0, q1 in ((axy, 1.0, a.q, b.q), (bxy, -1.0, b.q, a.q)):
            for s in ss:
                off = bc.LANE_OFFSET * math.sin(math.pi * s)
                xy = xy0 + sign * (delta * s + normal * off)
                q = bc._quat_at(q0, q1, s)
                R = bc.quat_to_matrix(q)
                u = R[:2, 0] / np.linalg.norm(R[:2, 0]); v = np.array([-u[1], u[0]])
                cs.append(xy); As.append(np.stack([u, v], 1))
    return np.array(cs), np.array(As)


def sq_overlap(c1, A1, h1, c2, A2, h2, eps=1e-6):
    """批量正方形 SAT（c1:(M,2),A1:(M,2,2)；c2:(2,),A2:(2,2)）；gap ≤ eps 视为相交（与 _classify 同向保守）。"""
    d = c2[None, :] - c1
    sep = np.zeros(c1.shape[0], bool)
    axes = [A1[:, :, 0], A1[:, :, 1], np.broadcast_to(A2[:, 0], c1.shape), np.broadcast_to(A2[:, 1], c1.shape)]
    for ax in axes:
        r1 = np.abs(np.einsum("mi,mi->m", A1[:, :, 0], ax)) * h1 + np.abs(np.einsum("mi,mi->m", A1[:, :, 1], ax)) * h1
        r2 = np.abs(ax @ A2[:, 0]) * h2 + np.abs(ax @ A2[:, 1]) * h2
        sep |= np.abs(np.einsum("mi,mi->m", d, ax)) > r1 + r2 + eps
    return ~sep


def footprint_axes(yaw_deg):
    _, q = bc.bin_actor_pose([0, 0], yaw_deg, CHS)
    R = bc.quat_to_matrix(q)
    u = R[:2, 0] / np.linalg.norm(R[:2, 0]); v = np.array([-u[1], u[0]])
    return np.stack([u, v], 1)


def sweep_hits_fast(xy, yaw_deg, samp, h=OBB_HALF):
    cs, As = samp
    if cs.shape[0] == 0:
        return False
    xy = np.asarray(xy, float)
    near = np.linalg.norm(cs - xy, axis=1) < 2 * h * math.sqrt(2) + 1e-3
    if not near.any():
        return False
    return bool(sq_overlap(cs[near], As[near], h, xy, footprint_axes(yaw_deg), h).any())


def coarse_near(xy, sweeps, r_static=None):
    """复刻 check_swap_sweep 的包围球粗筛：True ⇒ 该候选至少对一段扫掠要进区间二分（耗时 ~1 s 量级）。"""
    shapes = bc.bin_shape_specs(CHS)
    if r_static is None:
        r_static = max(s.vertex_radius() for s in shapes)
    p = np.array([xy[0], xy[1], bc.bin_actor_pose([0, 0], 0, CHS)[0][2]])
    for a, b in sweeps:
        delta, normal = bc._lane_endpoints(a.p[:2], b.p[:2])
        for xy0, sign in ((a.p[:2], 1.0), (b.p[:2], -1.0)):
            mid = xy0 + sign * (delta * 0.5 + normal * bc.LANE_OFFSET)
            c = np.array([mid[0], mid[1], a.p[2]])
            r = 0.5 * float(np.linalg.norm(delta)) + bc.LANE_OFFSET + r_static
            if float(np.linalg.norm(c - p)) - r - r_static <= bc.EPS_M:
                return True
    return False


def place_ring_generic(rng, ring, n, obbs_fixed, *, gap=CHS * 0.75, max_trials=256, vis=vis_center_exact,
                       samp=None, sweeps=None, circles=None, circle_gap=None, yaw_each_trial=False,
                       count_near=None):
    """统一版外环放置：拒绝采样 ring.bbox() → 环带 → 可见 → 避让（OBB 规则或外接圆规则）→ 扫掠（快速近似）。
    circles 不为 None 时用 sample_distractors 的外接圆规则（circle_gap=min_gap），否则用 spawn_ring 的 OBB 规则。
    返回 (placed, n_fail)；不在失败处停止（逐个继续），调用方据 n_fail==0 判「全部放下」。"""
    x0, x1, y0, y1 = ring.bbox()
    obbs = list(obbs_fixed)
    occ = None if circles is None else [(np.asarray(c, float), float(r)) for c, r in circles]
    thr = HALF + gap
    placed, n_fail = [], 0
    for i in range(n):
        u = rng.random((max_trials, 3))
        cand = np.stack([x0 + u[:, 0] * (x1 - x0), y0 + u[:, 1] * (y1 - y0)], 1)
        ok = ring.contains(cand[:, 0], cand[:, 1]) & vis(cand[:, 0], cand[:, 1])
        if occ is None:
            if obbs:
                ok &= dist_to_obbs(cand, obbs) >= thr
        else:
            for c, r in occ:
                ok &= np.linalg.norm(cand - c, axis=1) >= r + SWAP_R + circle_gap
        chosen = None
        for j in np.flatnonzero(ok):
            yaw_deg = u[j, 2] * 90.0
            if samp is not None:
                if count_near is not None and sweeps is not None and coarse_near(cand[j], sweeps):
                    count_near[0] += 1
                if sweep_hits_fast(cand[j], yaw_deg, samp):
                    continue
            chosen = (cand[j], math.radians(yaw_deg))
            break
        if chosen is None:
            n_fail += 1
            continue
        placed.append(chosen)
        if occ is None:
            obbs.append((chosen[0], footprint_axes(math.degrees(chosen[1])), np.array([OBB_HALF + gap] * 2)))
        else:
            occ.append((chosen[0], SWAP_R))
    return placed, n_fail
