"""离线模型里 screw 失败（真实系统会退到 RRT*）的目标位置统计：5x6@0.1 与 6x6@0.08、5x5@0.1 各 300 条抽签路径。"""
import sys, os, json, collections, logging, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "src")
logging.disable(logging.CRITICAL)
import screw_model as sm
from robomme.robomme_env.utils.adjacent import find_path_0_to_8
p = sm.make_planner()
for R, C, sp, lo, hi in [(5, 5, 0.1, 20, 24), (5, 6, 0.1, 25, 28), (6, 6, 0.08, 30, 33)]:
    sm.FALLBACKS.clear(); where = collections.Counter(); first_node = 0; segs = 0
    for k in range(300):
        g = torch.Generator(); g.manual_seed(5500000 + 100 * k)
        for _ in range(1000):
            a, b = torch.randperm(R * C, generator=g)[:2].tolist()
            path, *_ = find_path_0_to_8(start=a, target=b, R=R, C=C, diagonals=True, generator=g)
            if lo <= len(path) <= hi: break
        n0 = len(sm.FALLBACKS)
        sm.path_frames(p, path, R, C, spacing=sp)
        segs += len(path) - 1
        for kind, xy in sm.FALLBACKS[n0:]:
            if kind == "rrt_proxy": where[xy] += 1
    print(f"{R}x{C}@{sp}: segments={segs} rrt_proxy={sum(where.values())} ({sum(where.values())/segs*100:.2f}% of segments) top targets={where.most_common(6)}", flush=True)
