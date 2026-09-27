# 追加方案：无重复约束（最近 m 段用过的槽位对不再用）、目标移动次数分布、同一对最大重复次数、摆放尝试次数尾部
import sys, os, json, time, collections
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import place, draw_selection
from sim_lib import SweepCache, nn_order

def episode(cache, target, n, seq, rule, rng, k=1, feasible=False, noreuse=0):
    P = cache.P; N = len(P)
    occ = list(range(N)); slot_of = list(range(N))
    hist = []; mult = collections.Counter(); tslots = [slot_of[target]]; rej = None; infeas = 0; parts = set()
    for s in range(n):
        a = seq[s]; sa = slot_of[a]
        order, _ = nn_order(P, sa)
        cands = [c for c in order if not (feasible and cache.rejected(sa, c))]
        if noreuse:
            recent = set(hist[-noreuse:])
            c2 = [c for c in cands if (min(sa, c), max(sa, c)) not in recent]
            cands = c2 or cands
        if not cands:
            infeas += 1; cands = order
        if rule == "nn":
            sb = cands[0]
        else:
            pool = cands[:k]; sb = pool[int(rng.random() * len(pool))]
        b = occ[sb]; pair = (min(sa, sb), max(sa, sb))
        if cache.rejected(sa, sb) and rej is None:
            rej = s
        hist.append(pair); mult[pair] += 1; parts.update((a, b))
        occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa
        tslots.append(slot_of[target])
    tm = sum(1 for i in range(1, len(tslots)) if tslots[i] != tslots[i - 1])
    return dict(rej=rej is not None, infeas=infeas > 0, tmoves=tm, thome=tslots[-1] == tslots[0], tslots=len(set(tslots)),
                maxmult=max(mult.values()), distinct=len(mult), parts=len(parts), n=n)

SCH = {
    "S0_v4_3init_nn": dict(ini="v4", rule="nn"),
    "S1_all_nn": dict(ini="all", rule="nn"),
    "S7_all_nn_feas": dict(ini="all", rule="nn", feasible=True),
    "S9_all_2nn_feas": dict(ini="all", rule="knn", k=2, feasible=True),
    "S12_all_nn_feas_noreuse1": dict(ini="all", rule="nn", feasible=True, noreuse=1),
    "S13_all_nn_feas_noreuse2": dict(ini="all", rule="nn", feasible=True, noreuse=2),
    "S14_all_2nn_feas_noreuse1": dict(ini="all", rule="knn", k=2, feasible=True, noreuse=1),
    "S15_all_nn_noreuse1(no_feas)": dict(ini="all", rule="nn", noreuse=1),
}
METHODS = ["v4", "hc0.10", "hc0.12", "hc0.13", "hc0.14"]

def work(seed):
    out = {}
    for m in METHODS:
        r = place(seed, m)
        if not r["ok"]:
            out[m] = None; continue
        target, init3, init_all = draw_selection(r["g"])
        cache = SweepCache(r["cubes"]); n = r["n_swaps"]
        res = {"trials": r["trials"]}
        for name, cfg in SCH.items():
            seq = [init3[i % 3] for i in range(n)] if cfg["ini"] == "v4" else [init_all[i % 6] for i in range(n)]
            rng = np.random.default_rng(seed * 17 + list(SCH).index(name))
            res[name] = episode(cache, target, n, seq, cfg["rule"], rng, k=cfg.get("k", 1), feasible=cfg.get("feasible", False), noreuse=cfg.get("noreuse", 0))
        out[m] = res
    return seed, out

if __name__ == "__main__":
    M = int(sys.argv[1])
    seeds = [7_000_000 + i for i in range(M)]
    t0 = time.time(); R = {}
    with Pool(20) as pool:
        for s, o in pool.imap_unordered(work, seeds, chunksize=4):
            R[s] = o
    print(f"t={time.time()-t0:.0f}s")
    print("method  scheme                         ep_rej%  plan_infeas%  all6%  tgt_moves  P(tmoves<=1)%  P(tmoves<=2)%  tgt_home%  tgt_slots  maxmult  P(maxmult>=3)%  distinct_pairs")
    for m in METHODS:
        ok = [R[s][m] for s in R if R[s][m] is not None]
        tr = np.array([o["trials"] for o in ok])
        print(f"# {m}: placed {len(ok)}/{len(R)}  trials mean={tr.mean():.1f} p99={np.percentile(tr,99):.0f} max={tr.max()}")
        for name in SCH:
            E = [o[name] for o in ok]
            f = lambda k: np.mean([e[k] for e in E])
            print(f"{m:7s} {name:30s} {100*f('rej'):6.1f}   {100*f('infeas'):6.1f}     {100*np.mean([e['parts']==6 for e in E]):5.1f}  {f('tmoves'):5.2f}      {100*np.mean([e['tmoves']<=1 for e in E]):5.1f}          {100*np.mean([e['tmoves']<=2 for e in E]):5.1f}        {100*f('thome'):5.1f}     {f('tslots'):4.2f}      {f('maxmult'):4.2f}     {100*np.mean([e['maxmult']>=3 for e in E]):5.1f}        {f('distinct'):4.2f}")
    json.dump({str(k): v for k, v in R.items()}, open(os.path.join(os.path.dirname(__file__), f"extra_sim_{M}.json"), "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("全部完成")
