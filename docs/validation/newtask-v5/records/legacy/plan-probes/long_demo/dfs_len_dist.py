"""PatternLock 路径搜索（真实 find_path_0_to_8, diagonals=True）单次尝试的节点数分布，按网格尺寸比较。

逐字复刻 PatternLock._load_scene 的一次尝试：torch.randperm(R*C)[:2] 取起终点 → find_path_0_to_8(R, C, diagonals=True)。
每个网格用 20 个种子 × 1000 次连续尝试 = 20000 次（与 V4 计划 2.19 的 20000 次口径相同）。
"""
import sys, json, collections, torch, logging
sys.path.insert(0, "src")
logging.disable(logging.CRITICAL)
from robomme.robomme_env.utils.adjacent import find_path_0_to_8
out = {}
for R, C in [(5, 5), (5, 6), (6, 5), (6, 6), (6, 7), (7, 7)]:
    cnt = collections.Counter()
    for s in range(20):
        g = torch.Generator(); g.manual_seed(1000 + s)
        for _ in range(1000):
            a, b = torch.randperm(R * C, generator=g)[:2].tolist()
            path, *_ = find_path_0_to_8(start=a, target=b, R=R, C=C, diagonals=True, generator=g)
            cnt[len(path)] += 1
    tot = sum(cnt.values())
    out[f"{R}x{C}"] = dict(sorted(cnt.items()))
    tail = {n: cnt[n] for n in sorted(cnt) if n >= R * C - 10}
    print(f"{R}x{C}: max_nodes={R*C} mean={sum(k*v for k,v in cnt.items())/tot:.2f} tail(n>=N-10)={tail}")
json.dump(out, open("/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/long_demo/dfs_len_dist.json", "w"), indent=1)
