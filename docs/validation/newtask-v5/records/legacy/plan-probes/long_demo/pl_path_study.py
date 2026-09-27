"""PatternLock 方案对比：逐字复刻 _load_scene 的抽签循环（真实 find_path_0_to_8），再用离线螺旋模型算演示帧数。

用法：pl_path_study.py <R> <C> <spacing> <lo> <hi> <n_seeds> [mode] [time_scale]
  mode=dfs（默认，现行简单路径 DFS）| walk（允许重复访问的 8 邻接随机游走，禁立即回头，段数 L∈[lo,hi]）
  time_scale：每段帧数乘以该系数后取 ceil（模拟"放慢演示"方案），默认 1.0
种子：5500000 + 100*k（与 V4 PatternLock 公式同形），k=0..n_seeds-1
输出：命中率、尝试次数、节点数分布、演示帧数分布、落在 [750,1050] 的比例
"""
import sys, os, json, math, logging, collections
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")
logging.disable(logging.CRITICAL)
from robomme.robomme_env.utils.adjacent import find_path_0_to_8, grid_adjacency
from screw_model import make_planner, path_frames, FALLBACKS
R, C, sp, lo, hi, N = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
mode = sys.argv[7] if len(sys.argv) > 7 else "dfs"
ts = float(sys.argv[8]) if len(sys.argv) > 8 else 1.0
p = make_planner()
adj = grid_adjacency(R, C, diagonals=True)
rows = []
for k in range(N):
    seed = 5500000 + 100 * k
    g = torch.Generator(); g.manual_seed(seed)
    hit = False
    if mode == "dfs":
        for attempt in range(1000):
            a, b = torch.randperm(R * C, generator=g)[:2].tolist()
            path, *_ = find_path_0_to_8(start=a, target=b, R=R, C=C, diagonals=True, generator=g)
            if lo <= len(path) <= hi:
                hit = True; break
    else:
        # 允许重访的随机游走：起点均匀，逐步从 8 邻居里均匀取（禁止立即回头）
        attempt = 0
        L = int(torch.randint(lo, hi + 1, (1,), generator=g).item())
        path = [int(torch.randint(0, R * C, (1,), generator=g).item())]
        for _ in range(L):
            cand = [m for m in adj[path[-1]] if len(path) < 2 or m != path[-2]]
            path.append(cand[int(torch.randint(0, len(cand), (1,), generator=g).item())])
        hit = True
    n0 = len(FALLBACKS)
    first, segs = path_frames(p, path, R, C, spacing=sp)
    fb = len(FALLBACKS) - n0
    fail = sum(s is None for s in segs) + (first is None)
    segs2 = [math.ceil((s or 0) * ts) for s in segs]
    demo = sum(segs2)
    rows.append(dict(seed=seed, hit=hit, attempts=attempt + 1, nodes=len(path), segs=len(segs), demo=demo,
                     exec=sum(s or 0 for s in segs), screw_fail=fail, fallbacks=fb, revisits=len(path) - len(set(path))))
d = np.array([r["demo"] for r in rows]); e = np.array([r["exec"] for r in rows])
att = np.array([r["attempts"] for r in rows])
inr = np.mean((d >= 750) & (d <= 1050))
res = dict(config=f"{R}x{C}@{sp} {mode} [{lo},{hi}] ts={ts}", n=N, hit_rate=float(np.mean([r['hit'] for r in rows])),
           attempts_median=float(np.median(att)), attempts_max=int(att.max()),
           nodes_hist=dict(sorted(collections.Counter(r["nodes"] for r in rows).items())),
           demo_mean=round(float(d.mean()), 1), demo_min=int(d.min()), demo_p5=int(np.percentile(d, 5)),
           demo_p95=int(np.percentile(d, 95)), demo_max=int(d.max()),
           sec_mean=round(float(d.mean()) / 30, 2), sec_min=round(d.min() / 30, 2), sec_max=round(d.max() / 30, 2),
           frac_in_750_1050=round(float(inr), 3), frac_below_750=round(float(np.mean(d < 750)), 3), frac_above_1050=round(float(np.mean(d > 1050)), 3),
           exec_max=int(e.max()), exec_frac_over_1301=round(float(np.mean(e > 1301)), 3),
           frames_per_seg_mean=round(float(np.sum(d) / sum(r["segs"] for r in rows)), 2),
           screw_fail_paths=int(sum(r["screw_fail"] > 0 for r in rows)),
           fallback_paths=int(sum(r["fallbacks"] > 0 for r in rows)), fallback_segments=int(sum(r["fallbacks"] for r in rows)),
           fallback_kinds=dict(__import__("collections").Counter(k for k, _ in FALLBACKS)),
           revisit_paths=int(sum(r["revisits"] > 0 for r in rows)))
print("RESULT " + json.dumps(res), flush=True)
tag = f"{R}x{C}_{sp}_{mode}_{lo}_{hi}_ts{ts}"
json.dump(dict(summary=res, rows=rows), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"pl_study_{tag}.json"), "w"), indent=0)
