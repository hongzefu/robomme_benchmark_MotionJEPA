# 对比两种「全体发起者」序列：A 全体循环 [t,p1..p5]*；B 目标穿插（k%3==0 为目标，其余位置轮流 p1..p5），B 在 n≥8 时同样覆盖全部 6 块
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import place, draw_selection
from perturb_check2 import InflCache
from final_design_sim import run

def seq_interleave(init_all, n):
    t, others = init_all[0], init_all[1:]; out = []; j = 0
    for k in range(n):
        if k % 3 == 0:
            out.append(t)
        else:
            out.append(others[j % 5]); j += 1
    return out

def work(args):
    seed, mode = args
    r = place(seed, "hc0.12")
    target, _, init_all = draw_selection(r["g"]); n = r["n_swaps"]
    seq = [init_all[i % 6] for i in range(n)] if mode == "cycle" else seq_interleave(init_all, n)
    res = run(InflCache(r["cubes"], 0.025), None, target, n, seq, np.random.default_rng(seed), k=2)
    inits = len(set(seq))
    return {"plan": res is not None, "inits": inits, **(res or {})}

if __name__ == "__main__":
    M = int(sys.argv[1])
    for mode in ["cycle", "interleave"]:
        with Pool(20) as pool:
            R = pool.map(work, [(7_000_000 + i, mode) for i in range(M)], chunksize=4)
        ok = [x for x in R if x["plan"]]; f = lambda k: np.mean([x[k] for x in ok])
        print(f"{mode}: plan_ok={100*len(ok)/M:.1f}% initiators_all6={100*np.mean([x['inits']==6 for x in R]):.1f}% all6_part={100*np.mean([x['parts']==6 for x in ok]):.1f}% "
              f"tgt_moves={f('tmoves'):.2f} P(tmoves<=2)={100*np.mean([x['tmoves']<=2 for x in ok]):.1f}% tgt_home={100*f('home'):.1f}% tgt_slots={f('tslots'):.2f} maxmult={f('maxmult'):.2f} distinct={f('distinct'):.2f}")
