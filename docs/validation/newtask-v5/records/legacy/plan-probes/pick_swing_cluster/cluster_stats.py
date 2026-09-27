"""PickXtimes / SwingXtimes 聚集统计：V4 实际过程 vs 均匀/偶然基线 vs V5 候选。

用法: cluster_stats.py <scratch_dir> <N> <out_json>
每个设置用 seed = 20_000_000 + i (i<N) 的同一批 seed；并行 12 进程（纯 CPU）。
"""
import sys, json, math, itertools, time
from multiprocessing import Pool
import numpy as np
sys.path.insert(0, sys.argv[1])
import replica as R

N = int(sys.argv[2]) if len(sys.argv) > 3 else 0; OUT = sys.argv[3] if len(sys.argv) > 3 else None
SEED0 = 20_000_000
HS = 0.02
# 可行域（方块中心）
PICK_BOX = (-0.28, 0.08, -0.18, 0.18)
SWING_BOX = (-0.33, 0.13, -0.23, 0.23)
CENTER = (-0.1, 0.0)


def quad(x, y):
    return (int(x >= CENTER[0]), int(y >= CENTER[1]))


def cell3(x, y, box):
    xl, xh, yl, yh = box
    i = min(2, max(0, int(3 * (x - xl) / (xh - xl))))
    j = min(2, max(0, int(3 * (y - yl) / (yh - yl))))
    return i, j


def largest_cluster(pts, thr):
    n = len(pts); parent = list(range(n))
    def f(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for a, b in itertools.combinations(range(n), 2):
        if math.dist(pts[a], pts[b]) < thr:
            parent[f(a)] = f(b)
    from collections import Counter
    return max(Counter(f(i) for i in range(n)).values())


def metrics(colored, distract, box, target=None):
    allp = colored + distract
    m = {}
    q = [quad(*p) for p in colored]
    m["col_same_quad_ge2"] = len(set(q)) < 3
    m["col_same_quad_all3"] = len(set(q)) == 1
    m["col_distinct_quads"] = len(set(q))
    cells = [cell3(*p, box) for p in colored]
    corner_cells = [c for c in cells if c[0] != 1 and c[1] != 1]
    m["col_same_cornercell_ge2"] = len(corner_cells) != len(set(corner_cells))
    m["col_in_cornercell"] = len(corner_cells) / 3.0
    dcol = [math.dist(a, b) for a, b in itertools.combinations(colored, 2)]
    m["col_pair_lt_0p08"] = min(dcol) < 0.08
    m["col_maxpair_lt_0p15"] = max(dcol) < 0.15
    dall = [math.dist(a, b) for a, b in itertools.combinations(allp, 2)]
    m["all_min_pair"] = min(dall)
    m["all_min_lt_0p06"] = min(dall) < 0.06 - 1e-9
    m["all_min_lt_0p07"] = min(dall) < 0.07
    nn = [min(math.dist(p, o) for o in allp if o is not p) for p in allp]
    m["all_mean_nn"] = float(np.mean(nn))
    m["cl08_ge3"] = largest_cluster(allp, 0.08) >= 3
    m["cl08_ge4"] = largest_cluster(allp, 0.08) >= 4
    m["cl10_ge3"] = largest_cluster(allp, 0.10) >= 3
    # 整体离散度：6 块中心的 RMS 半径
    c = np.mean(np.array(allp), axis=0)
    m["all_rms_spread"] = float(np.sqrt(np.mean(np.sum((np.array(allp) - c) ** 2, axis=1))))
    if target is not None:
        xl, xh, yl, yh = box
        x, y = target
        m["tgt_dist_edge"] = min(x - xl, xh - x, y - yl, yh - y)
    return m


def run_pick(args):
    name, seed, kw = args
    kw = dict(kw)
    special = kw.pop("special", None)
    if special == "iid6":
        rng = np.random.default_rng(seed)
        xl, xh, yl, yh = PICK_BOX
        pts = [(rng.uniform(xl, xh), rng.uniform(yl, yh)) for _ in range(6)]
        return name, seed, {"colored": pts[:3], "distract": pts[3:], "target": pts[0]}
    if special == "poisson6":
        rng = np.random.default_rng(seed); xl, xh, yl, yh = PICK_BOX; pts = []
        while len(pts) < 6:
            p = (rng.uniform(xl, xh), rng.uniform(yl, yh))
            if all(math.dist(p, o) >= 0.06 for o in pts):
                pts.append(p)
        return name, seed, {"colored": pts[:3], "distract": pts[3:], "target": pts[0]}
    out = R.pick_layout(seed, **kw)
    if "fail" in out:
        return name, seed, {"fail": out["fail"]}
    col = [(x, y) for (_, x, y, _) in out["colored"]]
    dis = [(x, y) for (_, x, y, _) in out["distractors"]]
    tgt = col[0] if kw.get("target_slot0") else col[out["target_idx"]]
    return name, seed, {"colored": col, "distract": dis, "target": tgt, "goal": out["goal"], "button": out["button"]}


def run_swing(args):
    name, seed, kw = args
    kw = dict(kw); special = kw.pop("special", None)
    if special == "iid6":
        rng = np.random.default_rng(seed); xl, xh, yl, yh = SWING_BOX
        pts = [(rng.uniform(xl, xh), rng.uniform(yl, yh)) for _ in range(6)]
        return name, seed, {"colored": pts[:3], "distract": pts[3:], "target": pts[0]}
    out = R.swing_layout(seed, **kw)
    if "fail" in out:
        return name, seed, {"fail": out["fail"]}
    col = [(x, y) for (_, x, y, _) in out["colored"]]
    dis = [(x, y) for (_, x, y, _) in out["distractors"]]
    return name, seed, {"colored": col, "distract": dis, "target": col[out["target_idx"]], "disks": out["disks"], "button": out["button"]}


PICK_SETTINGS = {
    "P_V4_actual(cb0.5,trimeshOBB)": dict(corner_bias=0.5),
    "P_cb0(uniform,same rules,trimeshOBB)": dict(corner_bias=0.0),
    "P_cb1.0(trimeshOBB)": dict(corner_bias=1.0),
    "P_cb0.5_exactOBB": dict(corner_bias=0.5, obb_mode="exact"),
    "P_cb0_exactOBB": dict(corner_bias=0.0, obb_mode="exact"),
    "P_chance_iid6(no rules)": dict(special="iid6"),
    "P_poisson6(min0.06,no button/disk)": dict(special="poisson6"),
    "V5A_targetOnly(slot0 cb0.5,others0,exact,min0.08)": dict(corner_bias=0.5, obb_mode="exact", target_slot0=True, min_center_dist=0.08),
    "V5B_distinctQuad(cb0.5 all,exact,min0.08)": dict(corner_bias=0.5, obb_mode="exact", distinct_quadrant=True, min_center_dist=0.08),
    "V5C_uniform(cb0,exact,min0.08)": dict(corner_bias=0.0, obb_mode="exact", min_center_dist=0.08),
    "V5D_cb0.5all(exact,min0.08)": dict(corner_bias=0.5, obb_mode="exact", min_center_dist=0.08),
    "V5B2_distinctQuad(cb0.5,exact,min0.10)": dict(corner_bias=0.5, obb_mode="exact", distinct_quadrant=True, min_center_dist=0.10),
    "V5A2_targetOnly(cb0.5,exact,min0.10)": dict(corner_bias=0.5, obb_mode="exact", target_slot0=True, min_center_dist=0.10),
}
SWING_SETTINGS = {
    "S_V4_actual(trimeshOBB)": dict(),
    "S_exactOBB": dict(obb_mode="exact"),
    "S_chance_iid6(no rules)": dict(special="iid6"),
    "S_V5(exact,min0.08)": dict(obb_mode="exact", min_center_dist=0.08),
    "S_V5(exact,min0.10)": dict(obb_mode="exact", min_center_dist=0.10),
}


def hist(vals, lo, hi, bins=9):
    h, _ = np.histogram(vals, bins=bins, range=(lo, hi))
    return (h / max(1, len(vals))).round(3).tolist()


def summarize(results, box, env):
    ok = [r for r in results if "fail" not in r]
    fails = {}
    for r in results:
        if "fail" in r:
            fails[r["fail"]] = fails.get(r["fail"], 0) + 1
    ms = [metrics(r["colored"], r["distract"], box, r.get("target")) for r in ok]
    s = {"n": len(results), "ok": len(ok), "fail_rate": 1 - len(ok) / len(results), "fails": fails}
    for k in ms[0]:
        v = np.array([m[k] for m in ms], dtype=float)
        s[k] = round(float(v.mean()), 4)
        if k in ("all_min_pair", "tgt_dist_edge", "all_mean_nn", "all_rms_spread"):
            s[k + "_median"] = round(float(np.median(v)), 4)
    if "tgt_dist_edge" in ms[0]:
        s["tgt_edge_lt_0p02"] = round(float(np.mean([m["tgt_dist_edge"] < 0.02 for m in ms])), 4)
    xl, xh, yl, yh = box
    cx = [p[0] for r in ok for p in r["colored"]]; cy = [p[1] for r in ok for p in r["colored"]]
    dx = [p[0] for r in ok for p in r["distract"]]; dy = [p[1] for r in ok for p in r["distract"]]
    s["hist_col_x"] = hist(cx, xl, xh); s["hist_col_y"] = hist(cy, yl, yh)
    s["hist_dis_x"] = hist(dx, xl, xh); s["hist_dis_y"] = hist(dy, yl, yh)
    # 近机器人侧（x 低 1/3）与远侧（x 高 1/3）占比
    s["col_x_low_third"] = round(float(np.mean(np.array(cx) < xl + (xh - xl) / 3)), 4)
    s["col_x_high_third"] = round(float(np.mean(np.array(cx) > xh - (xh - xl) / 3)), 4)
    s["dis_absy_lt_0p1"] = round(float(np.mean(np.abs(np.array(dy)) < 0.1)), 4)
    s["col_absy_lt_0p1"] = round(float(np.mean(np.abs(np.array(cy)) < 0.1)), 4)
    return s


if __name__ == "__main__":
    # replica 的 V5 开关（distinct_quadrant / target_slot0）在 replica_v5 里打补丁实现
    import replica_v5  # noqa: F401  (monkeypatch R.pick_layout)
    t0 = time.time()
    jobs = [(n, SEED0 + i, kw) for n, kw in PICK_SETTINGS.items() for i in range(N)]
    sj = [(n, SEED0 + i, kw) for n, kw in SWING_SETTINGS.items() for i in range(N)]
    with Pool(12) as pool:
        pr = pool.map(run_pick, jobs, chunksize=20)
        sr = pool.map(run_swing, sj, chunksize=20)
    res = {"meta": {"N": N, "seed0": SEED0, "elapsed_s": None}, "pick": {}, "swing": {}}
    for n in PICK_SETTINGS:
        res["pick"][n] = summarize([r for (nn, _, r) in pr if nn == n], PICK_BOX, "pick")
    for n in SWING_SETTINGS:
        res["swing"][n] = summarize([r for (nn, _, r) in sr if nn == n], SWING_BOX, "swing")
    res["meta"]["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(res, open(OUT, "w"), indent=1, ensure_ascii=False)
    print("elapsed", res["meta"]["elapsed_s"])
