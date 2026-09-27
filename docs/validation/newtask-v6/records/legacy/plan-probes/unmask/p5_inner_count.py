"""V6 探针 P5：内环容器数 4→5/6 的几何影响（假想锚点，VUS 式整体旋转 U[0,180°)、每锚点框半宽 0.07、min_gap 0.02）。
锚点：
  n4 = 现 region4 [[-0.05,-0.1],[-0.05,0.1],[0.1,0.1],[0.1,-0.1]]
  n5 = 正五边形，中心 (0.025,0)，外接半径 0.15
  n6 = 2×3 网格 x∈{-0.05,0.10}，y∈{-0.15,0,0.15}
  n6h = 正六边形，中心 (0.025,0)，外接半径 0.17
统计：放置失败率、最近邻距离、可行槽对图密度（仓库精确判定）、每个槽至少有 1 个可行搭档的比例、G 连通比例、
容器中心到相机可见边界（精确 8 角点，bins_visible_many）是否全可见。
用法：p5_inner_count.py <layouts> [procs]
"""
import json, math, multiprocessing as mp, sys, time
import numpy as np, torch
sys.path.insert(0, ".")
from mclib import *  # noqa
from replica import spawn_random_bin_replica, _bin_obb  # noqa

def poly(n, r, c=(0.025, 0.0)):
    return [[c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n)] for i in range(n)]

ANCHORS = {
    "n4": [[-0.05, -0.1], [-0.05, 0.1], [0.1, 0.1], [0.1, -0.1]],
    "n5": poly(5, 0.15),
    "n6": [[-0.05, -0.15], [-0.05, 0.0], [-0.05, 0.15], [0.1, 0.15], [0.1, 0.0], [0.1, -0.15]],
    "n6h": poly(6, 0.17),
}


def connected(n, edges):
    seen = {0}; stack = [0]
    while stack:
        u = stack.pop()
        for a, b in edges:
            for x, y in ((a, b), (b, a)):
                if x == u and y not in seen:
                    seen.add(y); stack.append(y)
    return len(seen) == n


def one(args):
    name, seed = args
    gen = torch.Generator(); gen.manual_seed(seed)
    pts = torch.tensor(ANCHORS[name], dtype=torch.float32)
    ang = torch.rand(1, generator=gen) * 180
    c, s = torch.cos(ang), torch.sin(ang)
    rot = torch.tensor([[c, -s], [s, c]]).squeeze()
    reg = torch.matmul(pts, rot.T).tolist()
    bins, obbs = [], []
    for r in reg:
        out = spawn_random_bin_replica(gen, obbs, r, 0.07, CH)
        if out is None:
            return {"seed": seed, "fail": True}
        bins.append(out); obbs.append(_bin_obb(*out, CH))
    S = inner_states(bins)
    n = len(bins)
    pairs = [(a, b) for a in range(n) for b in range(a + 1, n)]
    G = {p: inner_pair_ok(S, *p) for p in pairs}
    xy = np.array([b[:2] for b in bins])
    D = np.linalg.norm(xy[:, None] - xy[None], axis=-1) + np.eye(n) * 9
    edges = [p for p in pairs if G[p]]
    nn_ok = np.mean([G[tuple(sorted((i, int(np.argmin(D[i])))))] for i in range(n)])
    vis = bool(ux.bins_visible_many(xy, CH).all())
    return {"seed": seed, "fail": False, "dens": len(edges) / len(pairs), "deg_ok": all(any(i in e for e in edges) for i in range(n)),
            "conn": connected(n, edges), "nn_d": float(D.min(axis=1).mean()), "nn_feas": float(nn_ok), "vis": vis,
            "maxr": float(np.abs(xy).max())}


if __name__ == "__main__":
    L = int(sys.argv[1]); procs = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    for name in ANCHORS:
        with mp.Pool(procs) as pool:
            res = list(pool.imap_unordered(one, [(name, 9_700_000 + i) for i in range(L)], chunksize=10))
        ok = [r for r in res if not r["fail"]]
        f = lambda k: np.mean([r[k] for r in ok])
        print(f"P5 {name} layouts={L} place_fail={1 - len(ok) / L:.3f} G_density={f('dens'):.3f} every_slot_has_partner={f('deg_ok'):.3f} "
              f"G_connected={f('conn'):.3f} nn_dist_mean={f('nn_d'):.3f} nn_pair_feasible={f('nn_feas'):.3f} all_visible={f('vis'):.3f} max_abs_xy={max(r['maxr'] for r in ok):.3f}")
