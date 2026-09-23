# G2 容量探索：纯几何蒙特卡洛（不起 sapien），判据逐条对齐源码
#   容器：object_generation.py::spawn_random_bin  + VideoUnmask/ButtonUnmask::_load_scene
#   方块：object_generation.py::spawn_random_cube + VideoRepick::_load_scene（hard_cubes 整片区域）
#   交换：statechange.py::swap_flat_two_lane（lane_offset=0.07，smoothstep + sin 钟形偏移）
import sys, json, time
import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from cube_obb_degen import obb2d_cube  # trimesh 复刻 get_actor_obb → _trimesh_box_to_obb2d

CHS = 0.02                      # PICK_CUBE_CONFIGS['panda']['cube_half_size']
BIN_HALF_SAMPLE = (CHS * 2.5 + 0.005) * 0.5   # spawn_random_bin 内的 bin_half_size = 0.0275
BIN_OBB_HALF = 0.03             # trimesh OBB 实测：容器 actor 的 XY 外廓半边 0.03（与 yaw 对齐）
BTN_HALF = 0.025 * 1.5 * 1.5    # build_button: max(base_half)*1.5, base_half=0.025*scale(1.5) ⇒ 0.05625


def rot(yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, -s], [s, c]])


# ───────────────────────── 容器 ─────────────────────────
def place_bins(rng, n, region_half, gap, max_trials, button):
    """返回放下的容器中心列表。等价于逐次 spawn_random_bin，失败即 break（源码 except RuntimeError: break）。"""
    lo, hi = -region_half + BIN_HALF_SAMPLE, region_half - BIN_HALF_SAMPLE
    obs_c, obs_R, obs_h = [], [], []
    if button:
        # build_button: center [-0.2,0] + (U-0.5)*[0.1,0.1]；avoid 里是预制 OBB，不加 pad
        c = np.array([-0.2, 0.0]) + (rng.random(2) - 0.5) * 0.1
        obs_c.append(c); obs_R.append(np.eye(2)); obs_h.append(np.array([BTN_HALF, BTN_HALF]))
    placed = []
    thr = BIN_HALF_SAMPLE + gap
    for _ in range(n):
        cand = rng.random((max_trials, 2)) * (hi - lo) + lo
        ok = np.ones(max_trials, bool)
        for c, R, h in zip(obs_c, obs_R, obs_h):
            loc = (cand - c) @ R          # = R^T (p-c)
            d = np.linalg.norm(np.maximum(np.abs(loc) - h, 0.0), axis=1)
            ok &= d >= thr
        idx = np.flatnonzero(ok)
        if idx.size == 0:
            break
        p = cand[idx[0]]
        yaw = np.deg2rad(rng.random() * 90.0)   # 通过拒绝后才抽 yaw
        placed.append(p)
        # 容器进 avoid 时是 actor，pad=min_gap
        obs_c.append(p); obs_R.append(rot(yaw)); obs_h.append(np.array([BIN_OBB_HALF + gap] * 2))
    return placed


def run_unmask(seeds=200):
    out = []
    for env in ["VideoUnmask", "ButtonUnmask"]:
        for region in [0.2, 0.25, 0.3]:
            for f in [2, 1.5, 1, 0.5]:
                for n in [10, 12, 15, 18, 20, 25]:
                    for mt in ([256, 4096] if region == 0.2 else [256]):
                        cnts = []
                        for s in range(seeds):
                            rng = np.random.default_rng(100000 * s + 7)
                            cnts.append(len(place_bins(rng, n, region, CHS * f, mt, env == "ButtonUnmask")))
                        cnts = np.array(cnts)
                        out.append(dict(env=env, region=region, factor=f, gap=CHS * f, n=n, max_trials=mt,
                                        mean=float(cnts.mean()), min=int(cnts.min()), max=int(cnts.max()),
                                        all_rate=float((cnts == n).mean()), seeds=seeds))
    return out


def saturation_bins(seeds=100):
    """饱和容量：请求 60 个、max_trials=256，看平均能放下多少。"""
    out = []
    for env in ["VideoUnmask", "ButtonUnmask"]:
        for region in [0.2, 0.25, 0.3]:
            for f in [2, 1.5, 1, 0.5]:
                c = [len(place_bins(np.random.default_rng(s + 555), 80, region, CHS * f, 256, env == "ButtonUnmask"))
                     for s in range(seeds)]
                out.append(dict(env=env, region=region, factor=f, sat_mean=float(np.mean(c)),
                                sat_min=int(np.min(c)), sat_max=int(np.max(c))))
    return out


# ───────────────────────── 方块（VideoRepick clutter） ─────────────────────────
def sat_intersect(c1, A1, h1, c2, A2, h2):
    """object_generation.py::_obb2d_intersect 的逐字复刻（含零向量轴的 _safe_unit 行为）。"""
    d = c2 - c1
    for a in [A1[:, 0], A1[:, 1], A2[:, 0], A2[:, 1]]:
        n = np.linalg.norm(a)
        a = a if n < 1e-12 else a / n
        r1 = abs(A1[:, 0] @ a) * h1[0] + abs(A1[:, 1] @ a) * h1[1]
        r2 = abs(A2[:, 0] @ a) * h2[0] + abs(A2[:, 1] @ a) * h2[1]
        if abs(d @ a) > r1 + r2:
            return False
    return True


def sat_batch(cands_c, cands_A, h_new, c_obs, A_obs, h_obs):
    """对一批候选（K 个）同时做 SAT，返回 hit(K,)。与 sat_intersect 逐字等价。"""
    K = cands_c.shape[0]
    d = cands_c - c_obs                                   # (K,2)
    axes = [np.broadcast_to(A_obs[:, 0], (K, 2)), np.broadcast_to(A_obs[:, 1], (K, 2)),
            cands_A[:, :, 0], cands_A[:, :, 1]]
    sep = np.zeros(K, bool)
    for a in axes:
        n = np.linalg.norm(a, axis=1, keepdims=True)
        a = np.where(n < 1e-12, a, a / np.maximum(n, 1e-300))
        r1 = np.abs(a @ A_obs[:, 0]) * h_obs[0] + np.abs(a @ A_obs[:, 1]) * h_obs[1]
        r2 = (np.abs(np.einsum("ki,ki->k", cands_A[:, :, 0], a)) * h_new
              + np.abs(np.einsum("ki,ki->k", cands_A[:, :, 1], a)) * h_new)
        sep |= np.abs(np.einsum("ki,ki->k", d, a)) > r1 + r2
    return ~sep


def place_cubes(rng, n, max_trials=256, degenerate_obb=True, center=(-0.1, 0.0), half=(0.2, 0.25)):
    """VideoRepick::_load_scene hard 分支判据：avoid=[按钮OBB]+已放方块(actor,pad=0)；
    新方块 OBB 半边 = hs + min_gap(=hs)=0.04，随机 yaw∈[0,2π)，每次尝试都抽 yaw；
    失败抛 SceneGenerationError ⇒ reset 失败（口径 14：全部放下才算成功）。"""
    cx, cy = center
    xl, xh = cx - half[0] + CHS, cx + half[0] - CHS
    yl, yh = cy - half[1] + CHS, cy + half[1] - CHS
    bc = np.array([-0.2, 0.0]) + (rng.random(2) - 0.5) * 0.1
    obs = [(bc, np.eye(2), np.array([BTN_HALF, BTN_HALF]))]
    placed = []  # (xy, yaw)
    for _ in range(n):
        u = rng.random((max_trials, 3))
        cand = np.stack([xl + u[:, 0] * (xh - xl), yl + u[:, 1] * (yh - yl)], 1)
        yaw = u[:, 2] * 2 * np.pi
        c, s = np.cos(yaw), np.sin(yaw)
        A = np.stack([np.stack([c, s], 1), np.stack([-s, c], 1)], 2)   # 列为轴
        hit = np.zeros(max_trials, bool)
        for (co, Ao, ho) in obs:
            hit |= sat_batch(cand, A, CHS + CHS, co, Ao, ho)
        idx = np.flatnonzero(~hit)
        if idx.size == 0:
            break
        k = idx[0]
        p, y = cand[k], yaw[k]
        placed.append((p, y))
        if degenerate_obb:
            co, Ao, ho = obb2d_cube(p[0], p[1], y)      # 真实 trimesh 路径（约一半退化成线段）
        else:
            co, Ao, ho = p, rot(y), np.array([CHS, CHS])  # 理想整方块 OBB（对照）
        obs.append((co, Ao, ho))
    return placed, bc


def obb_of(p, yaw, h):
    return p, rot(yaw), np.array([h, h])


def swap_risk(rng, placed, n_swaps, lane_offset=0.07, margin=0.005, n_alpha=41):
    """按 VideoRepick 语义顺序模拟 n_swaps 次交换：发起者 = [目标, 其余随机两块]，第 k 次用 init[k%3]；
    搭档 = 交换开始时 XY 最近邻（严格小于，生成顺序优先）；结束时两块互换位置与朝向。
    指标 (a) 两车道矩形近似：沿 AB 方向 [-hs, L+hs]、法向 [-(off+hs), off+hs] 的矩形 vs 旁观块 OBB(hs+margin)；
    指标 (b) 按 smoothstep+sin 钟形轨迹逐帧采样，移动块用起始 yaw 的 OBB(hs) vs 旁观块 OBB(hs+margin)。"""
    m = len(placed)
    pos = np.array([p for p, _ in placed]).copy()
    yaw = np.array([y for _, y in placed]).copy()
    target = rng.integers(m)
    rest = [i for i in range(m) if i != target]
    init = [target] + list(rng.permutation(rest)[:2])
    hits_a = hits_b = 0
    for k in range(n_swaps):
        a = init[k % 3]
        d = np.linalg.norm(pos - pos[a], axis=1); d[a] = np.inf
        b = int(np.argmin(d))  # argmin 取首个最小 = 生成顺序优先
        A0, B0 = pos[a].copy(), pos[b].copy()
        v = B0 - A0; L = np.linalg.norm(v); u = v / L; nrm = np.array([-u[1], u[0]])
        by = [i for i in range(m) if i not in (a, b)]
        # (a) 矩形
        rc = A0 + u * (L / 2)
        RA = np.stack([u, nrm], 1)
        rh = np.array([L / 2 + CHS, lane_offset + CHS])
        ha = any(sat_intersect(rc, RA, rh, *obb_of(pos[i], yaw[i], CHS + margin)) for i in by)
        # (b) 钟形轨迹采样
        hb = False
        for t in np.linspace(0, 1, n_alpha):
            al = t * t * (3 - 2 * t); off = lane_offset * np.sin(np.pi * al)
            pa = A0 + v * al + nrm * off; pb = B0 - v * al - nrm * off
            for i in by:
                oc = obb_of(pos[i], yaw[i], CHS + margin)
                if sat_intersect(pa, rot(yaw[a]), np.array([CHS, CHS]), *oc) or \
                   sat_intersect(pb, rot(yaw[b]), np.array([CHS, CHS]), *oc):
                    hb = True; break
            if hb:
                break
        hits_a += ha; hits_b += hb
        ep_a = ha if k == 0 else None
        # 交换结束：互换位置与朝向
        pos[a], pos[b] = B0, A0
        yaw[a], yaw[b] = yaw[b], yaw[a]
        if k == 0:
            first = (ha, hb)
    return hits_a, hits_b, first


def run_repick(seeds=200):
    out = []
    for degen in [True, False]:
        for n in [4, 6, 8, 10, 12, 15, 20]:
            cnts, sw = [], []
            for s in range(seeds):
                rng = np.random.default_rng(900000 + 1000 * s + n)
                placed, _ = place_cubes(rng, n, degenerate_obb=degen)
                cnts.append(len(placed))
                if len(placed) == n and degen:
                    ns = int(rng.integers(8, 13))
                    ha, hb, first = swap_risk(rng, placed, ns)
                    sw.append((ha, hb, ns, first[0], first[1]))
            cnts = np.array(cnts)
            row = dict(obb="trimesh真实(约半数退化)" if degen else "理想整方块", n=n,
                       mean=float(cnts.mean()), min=int(cnts.min()), max=int(cnts.max()),
                       all_rate=float((cnts == n).mean()), seeds=seeds)
            if sw:
                sw = np.array(sw, float)
                row.update(
                    swap_layouts=len(sw),
                    per_swap_a=float(sw[:, 0].sum() / sw[:, 2].sum()),
                    per_swap_b=float(sw[:, 1].sum() / sw[:, 2].sum()),
                    ep_any_a=float((sw[:, 0] > 0).mean()),
                    ep_any_b=float((sw[:, 1] > 0).mean()),
                    first3_a=None,
                )
            out.append(row)
    return out


def repick_first3(seeds=200):
    """题面口径：每个成功布局随机取 3 个发起者，与其（初始布局）XY 最近邻配对，只看这 3 对的扫掠（不做顺序演化）。"""
    out = []
    for n in [4, 6, 8, 10, 12, 15, 20]:
        pa = pb = tot = 0; ep_a = ep_b = 0; layouts = 0
        for s in range(seeds):
            rng = np.random.default_rng(700000 + 1000 * s + n)
            placed, _ = place_cubes(rng, n)
            if len(placed) != n:
                continue
            layouts += 1
            pos = np.array([p for p, _ in placed]); yaw = np.array([y for _, y in placed])
            ea = eb = False
            for a in rng.permutation(n)[:3]:
                # 单对：复用 swap_risk 的判据，只跑 1 次交换且发起者固定为 a
                d = np.linalg.norm(pos - pos[a], axis=1); d[a] = np.inf; b = int(np.argmin(d))
                sub_rng = np.random.default_rng(0)
                # 构造一个 init[0]=a 的单次模拟
                ha, hb = _single(pos, yaw, a, b)
                pa += ha; pb += hb; tot += 1; ea |= ha; eb |= hb
            ep_a += ea; ep_b += eb
        out.append(dict(n=n, layouts=layouts, pair_a=pa / max(tot, 1), pair_b=pb / max(tot, 1),
                        any3_a=ep_a / max(layouts, 1), any3_b=ep_b / max(layouts, 1)))
    return out


def _single(pos, yaw, a, b, lane_offset=0.07, margin=0.005, n_alpha=41):
    m = len(pos)
    A0, B0 = pos[a], pos[b]
    v = B0 - A0; L = np.linalg.norm(v); u = v / L; nrm = np.array([-u[1], u[0]])
    by = [i for i in range(m) if i not in (a, b)]
    rc = A0 + u * (L / 2); RA = np.stack([u, nrm], 1); rh = np.array([L / 2 + CHS, lane_offset + CHS])
    ha = any(sat_intersect(rc, RA, rh, *obb_of(pos[i], yaw[i], CHS + margin)) for i in by)
    hb = False
    for t in np.linspace(0, 1, n_alpha):
        al = t * t * (3 - 2 * t); off = lane_offset * np.sin(np.pi * al)
        pa_ = A0 + v * al + nrm * off; pb_ = B0 - v * al - nrm * off
        for i in by:
            oc = obb_of(pos[i], yaw[i], CHS + margin)
            if sat_intersect(pa_, rot(yaw[a]), np.array([CHS, CHS]), *oc) or \
               sat_intersect(pb_, rot(yaw[b]), np.array([CHS, CHS]), *oc):
                hb = True; break
        if hb:
            break
    return ha, hb


def min_gap_stats(seeds=100, n=15):
    """真实退化 OBB 下，已放方块之间实际外廓（整方块）最小间距分布——看是否出现 <0（穿模）或远小于 0.02。"""
    gaps = []
    for s in range(seeds):
        placed, _ = place_cubes(np.random.default_rng(424242 + s), n)
        best = np.inf
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                # 两整方块是否相交 / 近似间距：用 SAT 二分找最小可膨胀量
                lo, hi = -CHS, 0.05
                ci, yi = placed[i]; cj, yj = placed[j]
                if sat_intersect(ci, rot(yi), np.array([CHS, CHS]), cj, rot(yj), np.array([CHS, CHS])):
                    best = min(best, -1.0); continue
                lo = 0.0
                for _ in range(20):
                    mid = (lo + hi) / 2
                    if sat_intersect(ci, rot(yi), np.array([CHS + mid, CHS + mid]), cj, rot(yj), np.array([CHS, CHS])):
                        hi = mid
                    else:
                        lo = mid
                best = min(best, lo)
        gaps.append(best)
    g = np.array(gaps)
    return dict(n=n, seeds=seeds, overlap_layouts=int((g < 0).sum()), min_gap_min=float(g[g >= 0].min()),
                min_gap_median=float(np.median(g[g >= 0])), below_0p01=float((g < 0.01).mean()),
                below_0p02=float((g < 0.0199).mean()))


if __name__ == "__main__":
    t0 = time.time()
    res = {}
    res["unmask"] = run_unmask(200); print("unmask done", time.time() - t0, flush=True)
    res["saturation"] = saturation_bins(100); print("sat done", time.time() - t0, flush=True)
    res["repick"] = run_repick(200); print("repick done", time.time() - t0, flush=True)
    res["repick_first3"] = repick_first3(200); print("first3 done", time.time() - t0, flush=True)
    res["gap15"] = min_gap_stats(100, 15); print("gap done", time.time() - t0, flush=True)
    res["gap10"] = min_gap_stats(100, 10)
    out = __file__.rsplit("/", 1)[0] + "/g2_results.json"
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print("全部完成", out, time.time() - t0)
