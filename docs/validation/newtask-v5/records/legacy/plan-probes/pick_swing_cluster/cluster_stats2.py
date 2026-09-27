"""第二批设置：分散判据、放大区域、max_trials 敏感性。用法: cluster_stats2.py <dir> <N> <out>"""
import sys, json, time
from multiprocessing import Pool
sys.path.insert(0, sys.argv[1])
import numpy as np
import cluster_stats as C
from replica_v5b import pick_layout_ext
N = int(sys.argv[2]); OUT = sys.argv[3]

SET = {
    "V4_actual(ref)": dict(),
    "V5B_distinctQuad(min0.08)": dict(obb_mode="exact", distinct_quadrant=True, min_center_dist=0.08),
    "V5B_distinctQuad(min0.08,trials1024)": dict(obb_mode="exact", distinct_quadrant=True, min_center_dist=0.08, max_trials=1024),
    "V5B3_colPairMin0.15(cb0.5all,min0.08)": dict(obb_mode="exact", colored_min_dist=0.15, min_center_dist=0.08),
    "V5B4_colPairMin0.12(cb0.5all,min0.08)": dict(obb_mode="exact", colored_min_dist=0.12, min_center_dist=0.08),
    "R25_V4rules(cube+distr half0.25)": dict(cube_half=0.25),
    "R25_distinctQuad(min0.08)": dict(obb_mode="exact", distinct_quadrant=True, min_center_dist=0.08, cube_half=0.25),
    "R25_colPairMin0.15(min0.08)": dict(obb_mode="exact", colored_min_dist=0.15, min_center_dist=0.08, cube_half=0.25),
    "R25_targetOnly(min0.08)": dict(obb_mode="exact", target_slot0=True, min_center_dist=0.08, cube_half=0.25),
    "R25_uniform(min0.08)": dict(obb_mode="exact", corner_bias=0.0, min_center_dist=0.08, cube_half=0.25),
    "R25_distinctQuad(min0.10)": dict(obb_mode="exact", distinct_quadrant=True, min_center_dist=0.10, cube_half=0.25),
}


def run(args):
    name, seed, kw = args
    out = pick_layout_ext(seed, **kw)
    if "fail" in out:
        return name, {"fail": out["fail"]}
    col = [(x, y) for (_, x, y, _) in out["colored"]]
    dis = [(x, y) for (_, x, y, _) in out["distractors"]]
    return name, {"colored": col, "distract": dis, "target": col[out["target_idx"]]}


if __name__ == "__main__":
    t0 = time.time()
    jobs = [(n, C.SEED0 + i, kw) for n, kw in SET.items() for i in range(N)]
    with Pool(12) as p:
        res = p.map(run, jobs, chunksize=20)
    out = {}
    for n, kw in SET.items():
        h = kw.get("cube_half", 0.2)
        box = (-0.1 - h + 0.02, -0.1 + h - 0.02, -h + 0.02, h - 0.02)
        out[n] = C.summarize([r for (nn, r) in res if nn == n], box, "pick")
    json.dump(out, open(OUT, "w"), indent=1)
    print("elapsed", round(time.time() - t0, 1))
