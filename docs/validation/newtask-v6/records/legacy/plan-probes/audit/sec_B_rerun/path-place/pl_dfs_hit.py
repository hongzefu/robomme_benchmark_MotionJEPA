"""V6 规划探针（PatternLock）：真实 find_path_0_to_8 单次尝试的节点数分布 → 各节点数门槛在 20000 / 50000 次预算下的命中率。

用法：pl_dfs_hit.py <R> <C> <n_attempts>
每次尝试与 _load_scene 同形：randperm(R*C)[:2] 取起终点，随机 8 邻接 DFS（不重访）。
"""
import sys, os, json, time, logging, collections
import torch
sys.path.insert(0, "src")
logging.disable(logging.CRITICAL)
from robomme.robomme_env.utils.adjacent import find_path_0_to_8
R, C, N = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
g = torch.Generator(); g.manual_seed(20260925)
cnt = collections.Counter(); t0 = time.time()
for _ in range(N):
    a, b = torch.randperm(R * C, generator=g)[:2].tolist()
    path, *_ = find_path_0_to_8(start=a, target=b, R=R, C=C, diagonals=True, generator=g)
    cnt[len(path)] += 1
dt = (time.time() - t0) / N
res = {"grid": f"{R}x{C}", "n_attempts": N, "sec_per_attempt": dt, "hist": dict(sorted(cnt.items())), "thresholds": {}}
for k in range(max(2, R * C - 16), R * C + 1):
    ge = sum(v for n, v in cnt.items() if n >= k) / N
    eq = cnt.get(k, 0) / N
    res["thresholds"][k] = dict(p_ge=ge, p_eq=eq,
                                hit_ge_20000=1 - (1 - ge) ** 20000, hit_ge_50000=1 - (1 - ge) ** 50000,
                                hit_eq_20000=1 - (1 - eq) ** 20000)
    print(f"{R}x{C} n>={k:2d}: p_single={ge:.6f} hit20k={res['thresholds'][k]['hit_ge_20000']:.4f} hit50k={res['thresholds'][k]['hit_ge_50000']:.4f} | n=={k}: p={eq:.6f} hit20k={res['thresholds'][k]['hit_eq_20000']:.4f}")
print(f"{R}x{C}: {dt*1000:.2f} ms/attempt, max nodes seen={max(cnt)}")
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"pl_dfs_hit_{R}x{C}.json"), "w"), indent=1)
