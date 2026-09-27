"""P1 离线副本：PickXtimes xhard V5 规则（均匀、6 块两两中心距 ≥0.08、精确 OBB 作障碍、max_trials 1024），
比较方块区域半宽 0.2 与 0.25。纯几何复刻 _load_scene 的抽样顺序（replica.py 已逐位校验 V4）。
用法: offline_p1.py <N> <out_json>
另含自检：本脚本的 v5_layout 在「V4 参数」（corner_bias 0.5、trimesh 障碍、无中心距、256 次、半宽 0.2）下
与 replica.pick_layout 逐位一致。"""
import sys, json, math, itertools, time
from multiprocessing import Pool
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import torch
import replica as R

HS = R.HS
BASE = (-0.615, 0.0)   # 机械臂基座 xy（_load_agent）
SEED0 = 20_000_000


def v5_layout(seed, cube_half=0.2, corner_bias=0.0, obb_mode="exact", min_center_dist=0.08, max_trials=1024):
    g = torch.Generator(); g.manual_seed(seed)
    bxy, bobb = R.build_button(g)
    order = torch.randperm(3, generator=g).tolist()
    torch.randint(0, 3, (1,), generator=g).item()
    obbs = [bobb]
    d = R.spawn_disk(g, obbs, [], (-0.1, 0), 0.2, radius=2 * HS, min_gap=2 * HS)  # 圆盘区域与预算不变
    if d is None:
        return {"fail": "disk"}
    gx, gy, _ = d
    obbs.append(R.disk_obb((gx, gy), 2 * HS + 2 * HS - HS))
    placed, colored, dis, trials = [], [], [], []

    def rej(x, y):
        return min_center_dist is not None and any(math.hypot(x - px, y - py) < min_center_dist for (px, py) in placed)

    names = ["red", "blue", "green"]
    for k, ci in enumerate(order):
        r = R.spawn_cube(g, obbs, [], (-0.1, 0), cube_half, corner_bias=corner_bias, obb_mode=obb_mode,
                         extra_reject=rej, max_trials=max_trials)
        if r is None:
            return {"fail": f"cube{k}"}
        x, y, yaw, t = r
        colored.append((names[ci], x, y, yaw)); placed.append((x, y)); trials.append(t)
        obbs.append(R.cube_obb2d(x, y, yaw, obb_mode))
    tidx = torch.randint(0, 3, (1,), generator=g).item()
    for name in ["yellow", "cyan", "magenta"]:
        r = R.spawn_cube(g, obbs, [], (-0.1, 0), cube_half, corner_bias=0.0, obb_mode=obb_mode,
                         extra_reject=rej, max_trials=max_trials)
        if r is None:
            return {"fail": f"distractor_{name}"}
        x, y, yaw, t = r
        dis.append((name, x, y, yaw)); placed.append((x, y)); trials.append(t)
        obbs.append(R.cube_obb2d(x, y, yaw, obb_mode))
    return {"button": bxy, "goal": (gx, gy), "colored": colored, "target_idx": tidx,
            "distractors": dis, "order": order, "trials": trials}


def largest_cluster(pts, thr):
    n = len(pts); parent = list(range(n))
    def f(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for a, b in itertools.combinations(range(n), 2):
        if math.dist(pts[a], pts[b]) < thr:
            parent[f(a)] = f(b)
    return max(Counter(f(i) for i in range(n)).values())


def run(args):
    hw, seed = args
    o = v5_layout(seed, cube_half=hw)
    if "fail" in o:
        return hw, {"fail": o["fail"]}
    pts = [(x, y) for (_, x, y, _) in o["colored"]] + [(x, y) for (_, x, y, _) in o["distractors"]]
    dmin = min(math.dist(a, b) for a, b in itertools.combinations(pts, 2))
    tgt = pts[o["target_idx"]]
    reach = [math.dist(p, BASE) for p in pts]
    return hw, {"trials": o["trials"], "dmin": dmin, "cl10": largest_cluster(pts, 0.10) >= 3,
                "cl08": largest_cluster(pts, 0.08) >= 2,
                "reach_max": max(reach), "reach_tgt": math.dist(tgt, BASE), "reach_all": reach}


def summarize(rows):
    ok = [r for r in rows if "fail" not in r]
    fails = Counter(r["fail"] for r in rows if "fail" in r)
    tr = np.array([r["trials"] for r in ok], dtype=float)
    dmin = np.array([r["dmin"] for r in ok])
    ra = np.concatenate([r["reach_all"] for r in ok])
    rt = np.array([r["reach_tgt"] for r in ok])
    rm = np.array([r["reach_max"] for r in ok])
    q = lambda a, p: round(float(np.quantile(a, p)), 4)
    return {
        "n": len(rows), "reset_ok": len(ok), "reset_ok_rate": round(len(ok) / len(rows), 4), "fails": dict(fails),
        "mean_trials_per_cube": round(float(tr.mean()), 2),
        "mean_trials_by_slot": [round(float(v), 2) for v in tr.mean(0)],
        "p99_trials_by_slot": [int(np.quantile(tr[:, i], 0.99)) for i in range(6)],
        "max_trials_seen": int(tr.max()),
        "min_pair_dist": {"min": q(dmin, 0), "p05": q(dmin, .05), "p25": q(dmin, .25), "median": q(dmin, .5),
                          "p75": q(dmin, .75), "p95": q(dmin, .95)},
        "min_pair_lt_0p08": float((dmin < 0.08).mean()),
        "min_pair_lt_0p09": round(float((dmin < 0.09).mean()), 4),
        "min_pair_lt_0p10": round(float((dmin < 0.10).mean()), 4),
        "cl10_ge3": round(float(np.mean([r["cl10"] for r in ok])), 4),
        "reach_cube_all": {"median": q(ra, .5), "p95": q(ra, .95), "max": q(ra, 1), "frac_gt_0p72": round(float((ra > 0.72).mean()), 4),
                           "frac_gt_0p75": round(float((ra > 0.75).mean()), 4)},
        "reach_target": {"median": q(rt, .5), "p95": q(rt, .95), "max": q(rt, 1), "frac_gt_0p72": round(float((rt > 0.72).mean()), 4),
                         "frac_gt_0p75": round(float((rt > 0.75).mean()), 4)},
        "episodes_any_cube_gt_0p75": round(float((rm > 0.75).mean()), 4),
    }


if __name__ == "__main__":
    if sys.argv[1] == "selfcheck":
        ok = 0
        for s in range(200):
            a = R.pick_layout(3_000_000 + s)
            b = v5_layout(3_000_000 + s, cube_half=0.2, corner_bias=0.5, obb_mode="trimesh", min_center_dist=None, max_trials=256)
            ok += ("fail" in a and "fail" in b and a["fail"] == b["fail"]) or (
                "fail" not in a and "fail" not in b and a["colored"] == b["colored"] and a["distractors"] == b["distractors"]
                and a["button"] == b["button"] and a["goal"] == b["goal"] and a["target_idx"] == b["target_idx"])
        print(f"V5_REPLICA_DEFAULT_EQ_V4={ok}/200")
        sys.exit(0)
    N = int(sys.argv[1]); OUT = sys.argv[2]
    t0 = time.time()
    jobs = [(hw, SEED0 + i) for hw in (0.2, 0.25) for i in range(N)]
    with Pool(24) as p:
        res = p.map(run, jobs, chunksize=25)
    out = {f"hw{hw}": summarize([r for (h, r) in res if h == hw]) for hw in (0.2, 0.25)}
    out["_meta"] = {"N": N, "seed0": SEED0, "rules": "corner_bias=0, min_center_dist=0.08 (6 块), exact OBB, max_trials=1024 (方块), 圆盘区域 0.2/256 不变",
                    "elapsed_s": round(time.time() - t0, 1)}
    json.dump(out, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False, indent=1))
