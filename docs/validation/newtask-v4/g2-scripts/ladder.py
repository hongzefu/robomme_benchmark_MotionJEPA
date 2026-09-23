# 阶梯表：区域不动（中心[0,0]、半边0.2），扫 min_gap_factor；公共随机数下"前 N 个全部放下" ⇔ 饱和放置个数 ≥ N
import sys, json, numpy as np
sys.path.insert(0, __file__.rsplit("/",1)[0])
import g2_mc
from g2_mc import CHS, BIN_HALF_SAMPLE, BIN_OBB_HALF, BTN_HALF, rot

def place_bins_yaw(rng, n, region_half, gap, max_trials, button):
    """与 g2_mc.place_bins 同一判据，额外返回 yaw 与按钮中心以便量真实边距。"""
    lo, hi = -region_half + BIN_HALF_SAMPLE, region_half - BIN_HALF_SAMPLE
    obs = []; btn = None
    if button:
        btn = np.array([-0.2, 0.0]) + (rng.random(2) - 0.5) * 0.1
        obs.append((btn, np.eye(2), np.array([BTN_HALF]*2)))
    placed = []; thr = BIN_HALF_SAMPLE + gap
    for _ in range(n):
        cand = rng.random((max_trials, 2)) * (hi - lo) + lo
        ok = np.ones(max_trials, bool)
        for c, R, h in obs:
            d = np.linalg.norm(np.maximum(np.abs((cand - c) @ R) - h, 0.0), axis=1); ok &= d >= thr
        idx = np.flatnonzero(ok)
        if idx.size == 0: break
        p = cand[idx[0]]; yaw = np.deg2rad(rng.random() * 90.0)
        placed.append((p, yaw)); obs.append((p, rot(yaw), np.array([BIN_OBB_HALF + gap]*2)))
    return placed, btn

def corners(p, yaw, h):
    R = rot(yaw); return np.array([p + R @ np.array([sx*h, sy*h]) for sx, sy in [(1,1),(1,-1),(-1,-1),(-1,1)]])

def seg_pt(a, b, q):
    t = np.clip(np.dot(q-a, b-a) / np.dot(b-a, b-a), 0, 1); return np.linalg.norm(a + t*(b-a) - q)

def poly_dist(P, Q):
    """两个凸四边形的最小距离；相交返回负数标记（-1）。"""
    if g2_mc.sat_intersect(P.mean(0), None, None, None, None, None) if False else False: pass
    # SAT 判相交
    for poly in (P, Q):
        for i in range(4):
            e = poly[(i+1)%4] - poly[i]; a = np.array([-e[1], e[0]])
            pp, qq = P @ a, Q @ a
            if pp.max() < qq.min() or qq.max() < pp.min(): break
        else: continue
        break
    else:
        return -1.0
    return min(min(seg_pt(Q[j], Q[(j+1)%4], P[i]) for i in range(4) for j in range(4)),
               min(seg_pt(P[j], P[(j+1)%4], Q[i]) for i in range(4) for j in range(4)))

res = {}
for env in ["VideoUnmask", "ButtonUnmask"]:
    for f in [2, 1.5, 1.25, 1, 0.75, 0.5, 0.25, 0]:
        gap = CHS * f; counts = []; mins = []
        for s in range(200):
            placed, btn = place_bins_yaw(np.random.default_rng(100000*s + 7), 200, 0.2, gap, 256, env == "ButtonUnmask")
            counts.append(len(placed))
            if s < 60:  # 量真实外廓（半边 0.03）最小边距
                C = [corners(p, y, BIN_OBB_HALF) for p, y in placed]
                m = min(poly_dist(C[i], C[j]) for i in range(len(C)) for j in range(i+1, len(C)))
                mins.append(m)
        counts = np.array(counts)
        ladder = {}
        N = 4
        while True:
            r = float((counts >= N).mean()); ladder[N] = r
            if r == 0: break
            N += 1
        n99 = max([n for n, r in ladder.items() if r >= 0.99], default=None)
        n95 = max([n for n, r in ladder.items() if r >= 0.95], default=None)
        lb = BIN_HALF_SAMPLE + 2*gap - BIN_OBB_HALF*np.sqrt(2)
        mins = np.array(mins)
        res[f"{env}|{f}"] = dict(env=env, factor=f, gap=gap, ladder=ladder, n99=n99, n95=n95,
                                 sat_mean=float(counts.mean()), sat_min=int(counts.min()), sat_max=int(counts.max()),
                                 edge_lb=float(lb), edge_emp_min=float(mins.min()), edge_emp_median=float(np.median(mins)),
                                 overlap_layouts=int((mins < 0).sum()))
        x = res[f"{env}|{f}"]
        print(env, f, "n99", n99, "n95", n95, "sat", x["sat_mean"], "lb", round(lb,4), "emp_min", round(x["edge_emp_min"],4), "med", round(x["edge_emp_median"],4), "overlap", x["overlap_layouts"], flush=True)
json.dump(res, open(__file__.rsplit("/",1)[0] + "/ladder_results.json", "w"), ensure_ascii=False, indent=1)
print("全部完成")
