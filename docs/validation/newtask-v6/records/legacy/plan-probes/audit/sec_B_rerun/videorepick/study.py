"""议题 1/2：现状与候选均匀性方案的离线蒙特卡洛（默认 10000 局，V5 xhard 口径：6 块、0.12 m、n_swaps 8～12）。

用法：uv run --no-sync python study.py <局数> <方块数> <dmin> <swap_lo> <swap_hi> <输出 json> [方案子集逗号分隔]
"""
import sys, os, json, time, collections
sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/plan-probes/videorepick")
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
import vr6_lib as L
import schemes as S

ARGS = None


def work(seed):
    n_cubes, dmin, slo, shi, names = ARGS
    t0 = time.time()
    r = L.reset_sample(seed, n_cubes=n_cubes, dmin=dmin, swaps=(slo, shi))
    if not r["ok"]:
        return dict(seed=seed, placed=False, trials=r["trials"])
    t1 = time.time()
    M = L.feasibility_matrix(r["cubes"], r["button"])
    t2 = time.time()
    P = np.array([c[:2] for c in r["cubes"]]); btn = np.array(r["button"])
    deg = M.sum(1).astype(int).tolist()
    out = dict(seed=seed, placed=True, trials=r["trials"], n_swaps=r["n_swaps"], target=r["target"], deg=deg,
               btn_dist=np.linalg.norm(P - btn, axis=1).round(4).tolist(), t_place=t1 - t0, t_feas=t2 - t1, res={})
    for name in names:
        fn = S.SCHEMES[name]
        rng = np.random.default_rng(seed)
        plan, fk = fn(r, M, rng)
        rec = dict(ok=plan is not None, fail_k=fk, tries=r.pop("_tries", None))
        if plan is not None:
            c = S.participation(plan, n_cubes)
            ini = np.bincount([p[0] for p in plan], minlength=n_cubes); par = np.bincount([p[1] for p in plan], minlength=n_cubes)
            pairs = collections.Counter(f"{min(a,b)}-{max(a,b)}" for a, b, *_ in plan)
            # 目标最终是否回到原槽位
            slot_of = list(range(n_cubes))
            for a, b, sa, sb, _ in plan:
                slot_of[a], slot_of[b] = sb, sa
            rec.update(part=c.tolist(), ini=ini.tolist(), par=par.tolist(), pairs=dict(pairs),
                       L=[round(p[4], 4) for p in plan], target_moves=int(c[r["target"]]),
                       target_home=slot_of[r["target"]] == r["target"],
                       maxrep=max(pairs.values()), backforth=sum(1 for i in range(1, len(plan)) if {plan[i][2], plan[i][3]} == {plan[i-1][2], plan[i-1][3]}))
        out["res"][name] = rec
    return out


if __name__ == "__main__":
    M_ = int(sys.argv[1]); n_cubes = int(sys.argv[2]); dmin = float(sys.argv[3]); slo, shi = int(sys.argv[4]), int(sys.argv[5])
    outp = sys.argv[6]
    names = sys.argv[7].split(",") if len(sys.argv) > 7 else list(S.SCHEMES)
    ARGS = (n_cubes, dmin, slo, shi, names)
    base = 7_100_000
    t = time.time()
    with Pool(10) as pool:
        R = list(pool.imap(work, range(base, base + M_), chunksize=16))
    json.dump(dict(args=dict(M=M_, n_cubes=n_cubes, dmin=dmin, swaps=[slo, shi], names=names, seed_base=base), eps=R),
              open(outp, "w"), ensure_ascii=False)
    print(f"完成 {M_} 局，用时 {time.time()-t:.0f}s → {outp}")
