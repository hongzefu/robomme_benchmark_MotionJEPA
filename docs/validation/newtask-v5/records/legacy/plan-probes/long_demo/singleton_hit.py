"""口径 14 核验：每个候选节点数 n 单独作为 [n,n] 时，1000 次预算内命中概率。
(1) 由 20000 次单次尝试分布解析估计 P=1-(1-p)^1000；(2) 真实抽签循环实测（每值 40 个种子）。"""
import sys, json, logging, torch
sys.path.insert(0, "src"); logging.disable(logging.CRITICAL)
from robomme.robomme_env.utils.adjacent import find_path_0_to_8
D = json.load(open("/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/long_demo/dfs_len_dist.json"))
def loop_hit(R, C, n, seeds=40):
    hits = 0; att = []
    for k in range(seeds):
        g = torch.Generator(); g.manual_seed(7700000 + 100 * k)
        for a in range(1000):
            s, t = torch.randperm(R * C, generator=g)[:2].tolist()
            path, *_ = find_path_0_to_8(start=s, target=t, R=R, C=C, diagonals=True, generator=g)
            if len(path) == n:
                hits += 1; att.append(a + 1); break
    return hits, (sorted(att)[len(att) // 2] if att else None)
for key, R, C, vals in [("5x5", 5, 5, [23, 24, 25]), ("5x6", 5, 6, [27, 28, 29, 30]), ("6x6", 6, 6, [31, 32, 33, 34, 35]), ("7x7", 7, 7, [40, 42, 43, 44])]:
    dist = {int(k): v for k, v in D[key].items()}; tot = sum(dist.values())
    for n in vals:
        p = dist.get(n, 0) / tot
        est = 1 - (1 - p) ** 1000
        h, med = loop_hit(R, C, n)
        print(f"{key} n={n}: p_single={p:.5f} P_hit_1000(analytic)={est:.3f} loop_hits={h}/40 median_attempts={med}", flush=True)
