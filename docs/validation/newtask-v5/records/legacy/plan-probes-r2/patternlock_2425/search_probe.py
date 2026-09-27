"""P3 搜索层：逐字复刻 PatternLock._load_scene 的路径抽签循环（torch.Generator(seed) → randperm(25)[:2] → 真实 find_path_0_to_8），
对目标区间 [24,24]、[25,25]、[24,25] 各跑 N 次独立试验（每次一个 seed），预算 20000，记命中所需尝试次数与墙钟。"""
import sys, json, time, logging
import torch
logging.disable(logging.CRITICAL)
from robomme.robomme_env.utils.adjacent import find_path_0_to_8
import robomme.robomme_env.utils.adjacent as adj_mod
print("adjacent 源:", adj_mod.__file__, flush=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
BUDGET = 20000
R = C = 5
out = {}
for name, lo, hi, base in [("n24", 24, 24, 6500000), ("n25", 25, 25, 6600000), ("n24_25", 24, 25, 6700000)] if len(sys.argv) > 2 else [("n24", 24, 24, 5500000), ("n25", 25, 25, 5600000), ("n24_25", 24, 25, 5700000)]:
    recs = []
    for k in range(N):
        seed = base + k
        g = torch.Generator(); g.manual_seed(seed)
        t0 = time.perf_counter(); hit = None; last_len = None
        for attempt in range(BUDGET):
            s, t = torch.randperm(R * C, generator=g)[:2].tolist()
            path, *_ = find_path_0_to_8(start=s, target=t, R=R, C=C, diagonals=True, generator=g)
            last_len = len(path)
            if lo <= last_len <= hi:
                hit = attempt + 1; break
        dt = time.perf_counter() - t0
        recs.append(dict(seed=seed, hit_attempt=hit, wall_s=round(dt, 4), final_len=last_len))
        if k % 20 == 0:
            print(f"{name} k={k} seed={seed} hit={hit} wall={dt:.2f}s", flush=True)
    out[name] = recs
    json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "search_probe.json", "w"), indent=0)
print("SEARCH_DONE", flush=True)
