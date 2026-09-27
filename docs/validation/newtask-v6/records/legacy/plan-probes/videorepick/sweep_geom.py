"""议题 3：方块数 / 最小中心距 / 规划余量 / 按钮障碍的几何敏感性（摆放成功率、孤立槽位率、可行度、规划成功率上界）。

规划成功率上界 = 摆放成功 × 无孤立槽位（均衡贪心 S3 与现状 S0 在 n_swaps ≥ N 时都恰好在「有孤立槽位」时失败）。
用法：uv run --no-sync python sweep_geom.py <每配置局数> <输出 json>
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
import vr6_lib as L

CONFIGS = []
for N in (6, 7, 8, 9, 10):
    for d in (0.10, 0.11, 0.12):
        CONFIGS.append(dict(N=N, d=d, margin=0.005, button=True))
for N in (6, 7, 8):
    CONFIGS += [dict(N=N, d=0.12, margin=0.0, button=True), dict(N=N, d=0.12, margin=0.005, button=False),
                dict(N=N, d=0.12, margin=0.0, button=False)]
CONFIGS += [dict(N=N, d=0.12, margin=0.005, button=True, half=(0.2, 0.30)) for N in (6, 7, 8, 9)]
CONFIGS += [dict(N=N, d=0.12, margin=0.005, button=True, half=(0.25, 0.30), center=(-0.05, 0.0)) for N in (6, 7, 8, 9, 10)]


def work(job):
    ci, seed = job; c = CONFIGS[ci]
    box = L.region_box(c.get("center", (-0.1, 0.0)), c.get("half", (0.2, 0.25)))
    t0 = time.time()
    r = L.reset_sample(seed, n_cubes=c["N"], dmin=c["d"], box=box)
    if not r["ok"]:
        return ci, dict(placed=False, fail_at=r["fail_at"])
    M = L.feasibility_matrix(r["cubes"], r["button"], margin=c["margin"], button_obstacle=c["button"])
    deg = M.sum(1)
    P = np.array([x[:2] for x in r["cubes"]]); D = np.linalg.norm(P[:, None] - P[None], axis=-1) + np.eye(len(P)) * 9
    return ci, dict(placed=True, iso=bool((deg == 0).any()), n_iso=int((deg == 0).sum()), deg=float(deg.mean()),
                    edges=int(M.sum() // 2), minpair=float(D.min()), t=time.time() - t0)


if __name__ == "__main__":
    K = int(sys.argv[1]); jobs = [(ci, 7_200_000 + s) for ci in range(len(CONFIGS)) for s in range(K)]
    with Pool(30) as pool:
        R = pool.map(work, jobs, chunksize=8)
    agg = {}
    for ci, o in R:
        agg.setdefault(ci, []).append(o)
    rows = []
    print("| N | dmin | 余量 | 按钮障碍 | 区域 | 摆放成功 | 孤立槽位局 | 规划成功上界 | 槽位平均可行度 | 可行对数均值 | 耗时 ms |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for ci, c in enumerate(CONFIGS):
        os_ = agg[ci]; pl = [o for o in os_ if o["placed"]]
        place = len(pl) / K; iso = np.mean([o["iso"] for o in pl]) if pl else float("nan")
        up = place * (1 - iso) if pl else 0.0
        reg = f"c{c.get('center', (-0.1, 0.0))} h{c.get('half', (0.2, 0.25))}"
        row = dict(**{k: (list(v) if isinstance(v, tuple) else v) for k, v in c.items()}, place=place, iso=float(iso), upper=up,
                   deg=float(np.mean([o["deg"] for o in pl])) if pl else None, edges=float(np.mean([o["edges"] for o in pl])) if pl else None,
                   t_ms=float(np.mean([o["t"] for o in pl]) * 1e3) if pl else None)
        rows.append(row)
        print(f"| {c['N']} | {c['d']} | {c['margin']} | {c['button']} | {reg} | {place:.3f} | {iso:.3f} | {up:.3f} | {row['deg'] or 0:.2f} | {row['edges'] or 0:.2f} | {row['t_ms'] or 0:.0f} |")
    json.dump(rows, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
