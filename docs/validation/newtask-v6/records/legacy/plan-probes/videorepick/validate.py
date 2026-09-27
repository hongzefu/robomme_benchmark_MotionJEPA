# 验证复刻：① v5-01 三局 VideoRepick 的位姿与 swap_pairs 与 rng_trace 逐次一致；② seed 7000000..7002399 的规划失败率应复现 s3g 的 39.96%（959/2400）
import sys, os, json, glob
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from multiprocessing import Pool
import vr6_lib as L

def one(seed):
    r = L.reset_sample(seed)
    if not r["ok"]:
        return seed, "place_fail"
    M = L.feasibility_matrix(r["cubes"], r["button"])
    seq = L.initiator_seq_current(r["target"], r["perm"], 6, r["n_swaps"])
    plan, k = L.plan_current(r["cubes"], M, seq, r["u"])
    return seed, ("plan_fail" if plan is None else "ok")

if __name__ == "__main__":
    for d in sorted(glob.glob("artifacts/newtask-v5/v5-01/rollout/run1/episodes/VideoRepick_episode_*")):
        tr = json.load(open(d + "/rng_trace.json")); c = {x["path"]: x["drawn"] for x in tr["calls"]}
        seed = int(glob.glob(d + "/hdf5_files/*.h5")[0].split("seed")[1].split(".")[0])
        r = L.reset_sample(seed)
        xy_ok = all(np.allclose(r["cubes"][i][:2], c[f"layout.cubes.{i}.xy_yaw"][:2], atol=1e-6) and abs(r["cubes"][i][2] - c[f"layout.cubes.{i}.xy_yaw"][2]) < 1e-9 for i in range(6))
        M = L.feasibility_matrix(r["cubes"], r["button"])
        seq = L.initiator_seq_current(r["target"], r["perm"], 6, r["n_swaps"])
        plan, _ = L.plan_current(r["cubes"], M, seq, r["u"])
        mine = [(f"bin_{p['initiator']}", f"bin_{p['partner']}") for p in plan]
        real = [(c[f"actions.swap_pairs.{k}"]["initiator"], c[f"actions.swap_pairs.{k}"]["partner"]) for k in range(r["n_swaps"])]
        print(f"seed {seed}: 位姿一致={xy_ok} n_swaps={r['n_swaps']}/{c['objects.n_swaps']} 目标={r['target']}/{c['objects.target']} swap_pairs一致={mine == real}")
    with Pool(30) as p:
        res = dict(p.map(one, range(7_000_000, 7_002_400), chunksize=8))
    from collections import Counter
    cnt = Counter(res.values()); print("2400 局：", dict(cnt), f"规划失败率 {cnt['plan_fail']/2400:.4f}")
