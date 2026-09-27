# 主蒙特卡洛：均匀性指标 + 各交换方案的覆盖/追踪/D5 扫掠拒绝率（真实 check_swap_sweep）
import sys, os, json, time, itertools
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import place, draw_selection, XL, XH, YL, YH
from sim_lib import SweepCache, run_episode, nn_graph_components

METHODS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["v4", "hc0.10", "hc0.12", "hc0.14", "bc4", "bc8", "grid6of8", "CSR"]
SCHEMES = {
    "S0_v4_3init_nn": ("v4init", "nn"),
    "S1_all_cycle_nn": ("allcyc", "nn"),
    "S2_all_cycle_2nn": ("allcyc", ("knn", 2)),
    "S3_all_cycle_3nn": ("allcyc", ("knn", 3)),
    "S4_all_cycle_randpartner": ("allcyc", "rand"),
    "S5_random_pair": ("randpair", None),
    "S6_iid_init_nn": ("iid", "nn"),
    "S7_all_cycle_nn_feasible": ("allcyc", "nn_feasible"),
    "S8_v4_3init_nn_feasible": ("v4init", "nn_feasible"),
    "S9_all_cycle_2nn_feasible": ("allcyc", ("knn_feasible", 2)),
    "S10_all_cycle_3nn_feasible": ("allcyc", ("knn_feasible", 3)),
    "S11_all_cycle_any_feasible": ("allcyc", ("knn_feasible", 0)),
}
GX, GY = np.meshgrid(np.linspace(XL, XH, 37), np.linspace(YL, YH, 47))
GRID = np.stack([GX.ravel(), GY.ravel()], 1)
AREA = (XH - XL) * (YH - YL)


def uni_metrics(P):
    D = np.linalg.norm(P[:, None] - P[None], axis=-1) + np.eye(len(P)) * 9
    nn = D.min(1)
    trip = any(D[i, j] <= 0.10 and D[i, k] <= 0.10 and D[j, k] <= 0.10 for i, j, k in itertools.combinations(range(len(P)), 3))
    # 2(x)×3(y) 等分格的最大计数
    cx = np.clip(((P[:, 0] - XL) / (XH - XL) * 2).astype(int), 0, 1); cy = np.clip(((P[:, 1] - YL) / (YH - YL) * 3).astype(int), 0, 2)
    counts = np.bincount(cx * 3 + cy, minlength=6)
    cover = np.linalg.norm(GRID[:, None] - P[None], axis=-1).min(1).max()
    ny = int((P[:, 1] < 0).sum())
    return dict(nn_mean=float(nn.mean()), min_pair=float(nn.min()), ce_R=float(nn.mean() / (0.5 * np.sqrt(AREA / len(P)))),
                clump3=bool(trip), max_cell=int(counts.max()), empty_cells=int((counts == 0).sum()), cover_radius=float(cover),
                side_min=int(min(ny, len(P) - ny)), far_half=int((P[:, 0] > REG_MID).sum()))

REG_MID = -0.1


def work(seed):
    out = {}
    for m in METHODS:
        r = place(seed, m)
        if not r["ok"]:
            out[m] = dict(ok=False, trials=r["trials"])
            continue
        cubes = r["cubes"]; P = np.array([[c[0], c[1]] for c in cubes])
        target, init3, init_all = draw_selection(r["g"])
        rec = dict(ok=True, trials=r["trials"], P=P.tolist(), uni=uni_metrics(P), nn_comp=nn_graph_components(P))
        cache = SweepCache(cubes)
        rec["init_ok"] = bool(cache.initial_ok()[0])
        sch = {}
        for name, (ini, prule) in SCHEMES.items():
            rng = np.random.default_rng(seed * 131 + list(SCHEMES).index(name))
            n = r["n_swaps"]
            if ini == "v4init":
                seq = [init3[k % 3] for k in range(n)]
            elif ini == "allcyc":
                seq = [init_all[k % 6] for k in range(n)]
            else:
                seq = ini
            sch[name] = run_episode(cubes, target, n, seq, prule, rng, cache=cache)
        rec["schemes"] = sch
        rec["pair_rej"] = {f"{k[0]}-{k[1]}": v[0] for k, v in cache.cache.items()}
        out[m] = rec
    return seed, out


if __name__ == "__main__":
    M = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    seeds = [7_000_000 + i for i in range(M)]
    t0 = time.time()
    res = {}
    with Pool(20) as pool:
        for k, (s, o) in enumerate(pool.imap_unordered(work, seeds, chunksize=4)):
            res[s] = o
            if (k + 1) % 250 == 0:
                print(f"progress {k+1}/{M} t={time.time()-t0:.0f}s", flush=True)
    outp = os.path.join(os.path.dirname(__file__), f"big_sim_{M}.json")
    json.dump({str(k): v for k, v in res.items()}, open(outp, "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("全部完成", outp, f"t={time.time()-t0:.0f}s", flush=True)
