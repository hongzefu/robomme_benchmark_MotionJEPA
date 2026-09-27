"""第三批：只调 min_gap（不修 OBB）能否消除近距对；SwingXtimes min_gap 0.04。用法: <dir> <N> <out>"""
import sys, json, time
from multiprocessing import Pool
sys.path.insert(0, sys.argv[1])
import cluster_stats as C
import replica as R
N = int(sys.argv[2]); OUT = sys.argv[3]
SET = {
    "P_minGap0.04_trimesh(cb0.5)": ("pick", dict(corner_bias=0.5, colored_min_gap=0.04, distractor_min_gap=0.04)),
    "P_minGap0.04_exact(cb0.5)": ("pick", dict(corner_bias=0.5, colored_min_gap=0.04, distractor_min_gap=0.04, obb_mode="exact")),
    "S_minGap0.04_trimesh": ("swing", dict(colored_min_gap=0.04, distractor_min_gap=0.04)),
}
def run(a):
    n, s = a; env, kw = SET[n]
    o = R.pick_layout(s, **kw) if env == "pick" else R.swing_layout(s, **kw)
    if "fail" in o: return n, {"fail": o["fail"]}
    col = [(x, y) for (_, x, y, _) in o["colored"]]; dis = [(x, y) for (_, x, y, _) in o["distractors"]]
    return n, {"colored": col, "distract": dis, "target": col[o["target_idx"]]}
if __name__ == "__main__":
    t0 = time.time()
    with Pool(12) as p:
        res = p.map(run, [(n, C.SEED0 + i) for n in SET for i in range(N)], chunksize=20)
    out = {n: C.summarize([r for (nn, r) in res if nn == n], C.PICK_BOX if SET[n][0] == "pick" else C.SWING_BOX, SET[n][0]) for n in SET}
    json.dump(out, open(OUT, "w"), indent=1)
    keys = ["ok", "fail_rate", "col_same_cornercell_ge2", "all_min_pair_median", "all_min_lt_0p06", "all_min_lt_0p07", "cl08_ge3", "cl10_ge3", "all_mean_nn"]
    for n, s in out.items():
        print(n, s["fails"], "  ".join(f"{k}={s[k]}" for k in keys))
    print("elapsed", round(time.time() - t0, 1))
