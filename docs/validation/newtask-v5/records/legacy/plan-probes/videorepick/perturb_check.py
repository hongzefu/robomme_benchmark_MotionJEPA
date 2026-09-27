# 复位期预排交换计划（名义槽位）在「演示抓放后目标位移 δ」下是否仍通过 D5：估计运行时残余拒绝率
import sys, os, json, time, collections
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import place, draw_selection
from sim_lib import SweepCache, nn_order

def plan(cache, target, n, seq, rng, k=2, noreuse=1):
    P = cache.P; N = len(P); occ = list(range(N)); slot_of = list(range(N)); hist = []; pairs = []
    for s in range(n):
        a = seq[s]; sa = slot_of[a]; order, _ = nn_order(P, sa)
        cands = [c for c in order if not cache.rejected(sa, c)]
        c2 = [c for c in cands if (min(sa, c), max(sa, c)) not in set(hist[-noreuse:])] if noreuse else cands
        cands = c2 or cands
        if not cands:
            return None
        sb = cands[:k][int(rng.random() * len(cands[:k]))]
        pairs.append((sa, sb)); hist.append((min(sa, sb), max(sa, sb)))
        b = occ[sb]; occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa
    return pairs

def work(args):
    seed, method, radii = args
    r = place(seed, method)
    if not r["ok"]:
        return seed, None
    target, init3, init_all = draw_selection(r["g"])
    cache = SweepCache(r["cubes"]); n = r["n_swaps"]
    rng = np.random.default_rng(seed)
    pl = plan(cache, target, n, [init_all[i % 6] for i in range(n)], rng)
    if pl is None:
        return seed, {"plan": False}
    out = {"plan": True}
    prng = np.random.default_rng(seed + 99)
    for rad in radii:
        cubes = [list(c) for c in r["cubes"]]
        ang = prng.uniform(0, 2 * np.pi); rr = rad * np.sqrt(prng.uniform())
        cubes[target][0] += rr * np.cos(ang); cubes[target][1] += rr * np.sin(ang)
        cubes[target][2] += np.radians(prng.uniform(-0.5, 0.5))
        c2 = SweepCache([tuple(c) for c in cubes])
        out[str(rad)] = any(c2.rejected(sa, sb) for sa, sb in pl)
    return seed, out

if __name__ == "__main__":
    M = int(sys.argv[1]); method = sys.argv[2]
    radii = [0.003, 0.012, 0.02]
    t0 = time.time(); res = []
    with Pool(20) as pool:
        for s, o in pool.imap_unordered(work, [(7_000_000 + i, method, radii) for i in range(M)], chunksize=4):
            res.append(o)
    ok = [o for o in res if o is not None]; pl = [o for o in ok if o["plan"]]
    print(f"method={method} layouts={len(ok)}/{M} plan_ok={len(pl)} ({100*len(pl)/len(ok):.1f}%) t={time.time()-t0:.0f}s")
    for rad in radii:
        print(f"  目标位移半径≤{rad*1000:.0f}mm: 预排计划在运行时被 D5 拒绝的比例 = {100*np.mean([o[str(rad)] for o in pl]):.2f}%")
