# 交换弯道路径是否压过按钮底座（D5 check_swap_sweep 只查方块之间，不含按钮）——离线统计
#   按钮底座物理半边 0.025×1.5=0.0375（轴对齐）；方块用外接圆 hs·√2（保守）与内切 hs（乐观）两档
#   路径：swap_flat_two_lane，smoothstep α、横向 0.07·sin(πα)，A 走 +n、B 走 −n，逐 1/50 采样
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import place, draw_selection, _head
from final_rule_sim import place_final, plan_final, HS
from perturb_check2 import InflCache
from sim_lib import nn_order
BH = 0.025 * 1.5
T = np.arange(51) / 50; AL = T * T * (3 - 2 * T); OFF = 0.07 * np.sin(np.pi * AL)

def box_dist(p, c):
    q = np.abs(p - c) - BH
    return np.hypot(np.maximum(q[:, 0], 0), np.maximum(q[:, 1], 0)) + np.minimum(np.maximum(q[:, 0], q[:, 1]), 0)

def cross(P, pairs_slots, btn):
    worst = np.inf
    for sa, sb in pairs_slots:
        a, b = P[sa], P[sb]; d = b - a; n = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
        pa = a + AL[:, None] * d + OFF[:, None] * n; pb = b - AL[:, None] * d - OFF[:, None] * n
        worst = min(worst, box_dist(pa, btn).min(), box_dist(pb, btn).min())
    return worst  # 方块中心到按钮底座的最小距离

def work(seed):
    out = {}
    btn = np.array(_head(seed)[3])
    r = place(seed, "v4"); t, i3, _ = draw_selection(r["g"]); P = np.array([c[:2] for c in r["cubes"]])
    occ = list(range(6)); so = list(range(6)); ps = []
    for k in range(r["n_swaps"]):
        a = i3[k % 3]; sa = so[a]; sb = nn_order(P, sa)[0][0]; b = occ[sb]; ps.append((sa, sb))
        occ[sa], occ[sb] = b, a; so[a], so[b] = sb, sa
    out["v4"] = cross(P, ps, btn)
    rf = place_final(seed); g = rf["g"]; n = rf["n_swaps"]; t, _, ia = draw_selection(g); u = torch.rand(n, generator=g).tolist()
    P = np.array([c[:2] for c in rf["cubes"]])
    for key, var in (("final", "B"), ("final_A", "A")):
        pairs, _, _ = plan_final(InflCache(rf["cubes"], HS + 0.005), [ia[k % 6] for k in range(n)], u, var)
        out[key] = None if pairs is None else cross(P, [(p[2], p[3]) for p in pairs], btn)
    return seed, out

if __name__ == "__main__":
    M = int(sys.argv[1]); R = {}
    with Pool(24) as pool:
        for s, o in pool.imap_unordered(work, [7_000_000 + i for i in range(M)], chunksize=4):
            R[s] = o
    for key in ("v4", "final", "final_A"):
        v = np.array([o[key] for o in R.values() if o[key] is not None])
        print(f"{key}: 局数={len(v)}  路径压到按钮底座(中心距底座<hs={HS})={100*np.mean(v<HS):.1f}%  (<hs·√2={HS*2**.5:.4f}，保守)={100*np.mean(v<HS*2**.5):.1f}%  中心进入底座={100*np.mean(v<0):.1f}%")
    for seed in (4900100, 4900400, 4900500, 4900700):
        print(seed, {k: (None if x is None else round(x, 4)) for k, x in work(seed)[1].items()})
