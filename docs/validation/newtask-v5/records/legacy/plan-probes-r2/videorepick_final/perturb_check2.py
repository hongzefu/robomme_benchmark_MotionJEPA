# 预排计划加安全余量：规划时把方块碰撞盒半边放大 m（check_swap_sweep 用放大形状），运行时用真实形状 + 目标位移 δ 复核
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import place, draw_selection
from sim_lib import SweepCache, nn_order
from robomme.robomme_env.utils.bin_collision import ObjectState, cube_shape_specs, cube_actor_pose

class InflCache(SweepCache):
    def __init__(self, cubes, hs):
        super().__init__(cubes)
        sh = cube_shape_specs(hs)
        self.states = [ObjectState(name=f"slot_{i}", p=cube_actor_pose((x, y), yaw, 0.02)[0], q=cube_actor_pose((x, y), yaw, 0.02)[1], shapes=sh) for i, (x, y, yaw) in enumerate(cubes)]

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
    seed, method, margins, radii = args
    r = place(seed, method)
    if not r["ok"]:
        return None
    target, _, init_all = draw_selection(r["g"]); n = r["n_swaps"]; seq = [init_all[i % 6] for i in range(n)]
    out = {}
    prng = np.random.default_rng(seed + 99)
    perts = []
    for rad in radii:
        ang = prng.uniform(0, 2 * np.pi); rr = rad * np.sqrt(prng.uniform()); dy = np.radians(prng.uniform(-0.5, 0.5))
        cubes = [list(c) for c in r["cubes"]]; cubes[target][0] += rr * np.cos(ang); cubes[target][1] += rr * np.sin(ang); cubes[target][2] += dy
        perts.append(SweepCache([tuple(c) for c in cubes]))
    for m in margins:
        pl = plan(InflCache(r["cubes"], 0.02 + m), target, n, seq, np.random.default_rng(seed))
        out[f"m{m}"] = {"plan": pl is not None, **({f"r{rad}": any(pc.rejected(sa, sb) for sa, sb in pl) for rad, pc in zip(radii, perts)} if pl else {})}
    return out

if __name__ == "__main__":
    M = int(sys.argv[1]); method = sys.argv[2]
    margins = [0.0, 0.005, 0.01, 0.015]; radii = [0.003, 0.012, 0.02]
    t0 = time.time()
    with Pool(20) as pool:
        res = [o for o in pool.map(work, [(7_000_000 + i, method, margins, radii) for i in range(M)], chunksize=4) if o]
    print(f"method={method} layouts={len(res)} t={time.time()-t0:.0f}s")
    for m in margins:
        pl = [o[f"m{m}"] for o in res if o[f"m{m}"]["plan"]]
        print(f"  余量 m={m*1000:.0f}mm: 复位期计划可行={100*len(pl)/len(res):.1f}%  " + "  ".join(f"δ≤{rad*1000:.0f}mm 运行时拒绝={100*np.mean([p[f'r{rad}'] for p in pl]):.2f}%" for rad in radii))
