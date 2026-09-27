# 推荐方案的整体指标：hc<d> 摆放 + 全体发起者循环 + 复位期预排（2 近邻可行、余量 m、不重复上一对）
import sys, os, time, collections
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import place, draw_selection
from sim_lib import SweepCache, nn_order
from perturb_check2 import InflCache

def run(cache_plan, cache_true, target, n, seq, rng, k=2, noreuse=1):
    P = cache_plan.P; N = len(P); occ = list(range(N)); slot_of = list(range(N)); hist = []; mult = collections.Counter()
    tsl = [slot_of[target]]; parts = set(); L = []
    for s in range(n):
        a = seq[s]; sa = slot_of[a]; order, d = nn_order(P, sa)
        cands = [c for c in order if not cache_plan.rejected(sa, c)]
        c2 = [c for c in cands if (min(sa, c), max(sa, c)) not in set(hist[-noreuse:])] if noreuse else cands
        cands = c2 or cands
        if not cands:
            return None
        sb = cands[:k][int(rng.random() * len(cands[:k]))]; b = occ[sb]
        pr = (min(sa, sb), max(sa, sb)); hist.append(pr); mult[pr] += 1; parts.update((a, b)); L.append(d[sb])
        occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa; tsl.append(slot_of[target])
    return dict(parts=len(parts), home=tsl[-1] == tsl[0], tslots=len(set(tsl)), maxmult=max(mult.values()), distinct=len(mult),
                tmoves=sum(1 for i in range(1, len(tsl)) if tsl[i] != tsl[i - 1]), meanL=float(np.mean(L)), maxL=float(np.max(L)))

def work(args):
    seed, method, m, k = args
    r = place(seed, method)
    if not r["ok"]:
        return {"placed": False}
    target, _, init_all = draw_selection(r["g"]); n = r["n_swaps"]
    res = run(InflCache(r["cubes"], 0.02 + m), None, target, n, [init_all[i % 6] for i in range(n)], np.random.default_rng(seed), k=k)
    return {"placed": True, "plan": res is not None, **(res or {})}

if __name__ == "__main__":
    M = int(sys.argv[1])
    for method, m, k in [("hc0.12", 0.005, 2), ("hc0.13", 0.005, 2), ("hc0.12", 0.005, 3), ("hc0.12", 0.0, 2)]:
        t0 = time.time()
        with Pool(20) as pool:
            R = pool.map(work, [(7_000_000 + i, method, m, k) for i in range(M)], chunksize=4)
        pl = [x for x in R if x["placed"]]; ok = [x for x in pl if x["plan"]]
        f = lambda key: np.mean([x[key] for x in ok])
        print(f"{method} margin={m*1000:.0f}mm k={k}: placed={100*len(pl)/M:.1f}% plan_ok={100*len(ok)/len(pl):.1f}% (reset-level total={100*len(ok)/M:.1f}%) "
              f"all6={100*np.mean([x['parts']==6 for x in ok]):.1f}% tgt_home={100*f('home'):.1f}% tgt_slots={f('tslots'):.2f} tgt_moves={f('tmoves'):.2f} "
              f"maxmult={f('maxmult'):.2f} P(maxmult>=3)={100*np.mean([x['maxmult']>=3 for x in ok]):.1f}% distinct_pairs={f('distinct'):.2f} path_mean={f('meanL'):.3f} path_max={f('maxL'):.3f} t={time.time()-t0:.0f}s", flush=True)
