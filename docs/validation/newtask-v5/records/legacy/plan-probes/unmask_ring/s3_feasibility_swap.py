# 步 3b：VideoUnmaskSwap / ButtonUnmaskSwap 外环放置可行性（每配置 500 局；含预演扫掠拒绝的快速近似）
import sys, json, math, time
import numpy as np
from multiprocessing import Pool
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L

NTRIAL = 500
VUS_IN = (-0.2114, 0.2114, -0.2114, 0.2114)
BUS_IN = (-0.07, 0.17, -0.17, 0.27)
BUSB_IN = (-0.2625, 0.17, -0.17, 0.27)
RINGS = {
    "VUS": {
        "A g.015 W.1414": (VUS_IN, 0.0425, 0.1289),
        "C g.040 W.1414": (VUS_IN, 0.0675, 0.1539),
        "B g.015 W.085": (VUS_IN, 0.0425, 0.0725),
        "V4 [0.2675,0.45]": ((0, 0, 0, 0), 0.2675, 0.45),
    },
    "BUS": {
        "A g.015 W.1414 (no-btn rect)": (BUS_IN, 0.0425, 0.1289),
        "A g.015 W.1414 (+btn rect)": (BUSB_IN, 0.0425, 0.1289),
        "C g.040 W.1414 (+btn rect)": (BUSB_IN, 0.0675, 0.1539),
        "V4 [0.2675,0.45]": ((0, 0, 0, 0), 0.2675, 0.45),
    },
}
NS = [4, 6, 8, 10, 12, 14, 16, 18]


def one(args):
    env, seed = args
    rng = np.random.default_rng(seed)
    if env == "VUS":
        lay = L.inner_vus(rng); nsw = int(rng.integers(8, 13))
    else:
        lay = L.inner_bus(rng); nsw = int(rng.integers(6, 9))
    if lay is None:
        return None
    btns = [] if env == "VUS" else list(lay[1])
    bins = lay[0]
    init = L.swap_initiators(rng)
    sweeps = L.predict_sweeps(bins, init, nsw)
    samp = L.sweep_samples(sweeps)
    gap = L.CHS * 0.75
    obbs_u = [(p, L.footprint_axes(math.degrees(y)), np.array([L.OBB_HALF + gap] * 2)) for p, y in bins]
    obbs_u += [(np.asarray(b), np.eye(2), np.array([L.BTN_HALF] * 2)) for b in btns]
    circles = [(p, L.SWAP_R) for p, _ in bins] + [(np.asarray(b), L.BTN_HALF * math.sqrt(2)) for b in btns]
    out = {}
    for rname, (inner, a, b) in RINGS[env].items():
        ring = L.RectRing(inner, a, b)
        # 扫掠占掉的环带比例（环带内、精确可见的随机点，随机 yaw）
        r3 = np.random.default_rng(seed + 17)
        x0, x1, y0, y1 = ring.bbox()
        pts = r3.uniform([x0, y0], [x1, y1], (4000, 2))
        m = ring.contains(pts[:, 0], pts[:, 1]) & L.vis_center_exact(pts[:, 0], pts[:, 1])
        pts = pts[m][:300]
        hit = [L.sweep_hits_fast(p, r3.random() * 90, samp) for p in pts]
        near = [L.coarse_near(p, sweeps) for p in pts[:100]]
        out[(rname, "sweep_frac")] = float(np.mean(hit)) if len(hit) else float("nan")
        out[(rname, "near_frac")] = float(np.mean(near)) if len(near) else float("nan")
        for rule in ("unified", "v4swap"):
            for n in NS:
                r2 = np.random.default_rng(seed * 1000 + n)
                cnt = [0]
                if rule == "unified":
                    placed, nf = L.place_ring_generic(r2, ring, n, obbs_u, max_trials=512, samp=samp, sweeps=sweeps,
                                                      count_near=cnt if n in (8, 16) else None)
                else:
                    placed, nf = L.place_ring_generic(r2, ring, n, [], max_trials=512, vis=L.vis_center_swap,
                                                      samp=samp, sweeps=sweeps, circles=circles, circle_gap=0.04,
                                                      count_near=cnt if n in (8, 16) else None)
                out[(rname, rule, n)] = (nf == 0, len(placed), cnt[0])
            r2 = np.random.default_rng(seed * 1000 + 999)
            if rule == "unified":
                placed, nf = L.place_ring_generic(r2, ring, 40, obbs_u, max_trials=1024, samp=samp)
            else:
                placed, nf = L.place_ring_generic(r2, ring, 40, [], max_trials=1024, vis=L.vis_center_swap, samp=samp,
                                                  circles=circles, circle_gap=0.04)
            out[(rname, rule, "sat")] = len(placed)
    return out


if __name__ == "__main__":
    ENVS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["VUS", "BUS"]
    res = {}
    t0 = time.time()
    with Pool(8) as pool:
        for env in ENVS:
            outs = pool.map(one, [(env, 200000 + s) for s in range(NTRIAL)])
            bad = sum(o is None for o in outs)
            outs = [o for o in outs if o is not None]
            print(f"\n=== {env}: 内层失败 {bad}/{NTRIAL}，有效 {len(outs)}（{time.time()-t0:.0f}s）===", flush=True)
            for rname in RINGS[env]:
                sf = np.array([o[(rname, 'sweep_frac')] for o in outs]); nf_ = np.array([o[(rname, 'near_frac')] for o in outs])
                print(f"  [{rname}] 扫掠占环带比例 mean {np.nanmean(sf)*100:.1f}% p95 {np.nanpercentile(sf,95)*100:.1f}%；"
                      f"需区间二分（包围球粗筛不过）的候选比例 mean {np.nanmean(nf_)*100:.1f}%")
                for rule in ("unified", "v4swap"):
                    sat = np.array([o[(rname, rule, 'sat')] for o in outs])
                    line = []
                    for n in NS:
                        ok = np.array([o[(rname, rule, n)][0] for o in outs]); got = np.array([o[(rname, rule, n)][1] for o in outs])
                        line.append(f"N={n}:{100*ok.mean():.1f}%")
                        res[f"{env}|{rname}|{rule}|{n}"] = dict(all_rate=float(ok.mean()), got_min=int(got.min()), got_mean=float(got.mean()))
                    nearc = {n: float(np.mean([o[(rname, rule, n)][2] for o in outs])) for n in (8, 16)}
                    print(f"    {rule:8s} 饱和 mean {sat.mean():.1f} min {sat.min()} p5 {np.percentile(sat,5):.0f}; 近扫掠候选数(每局) N=8:{nearc[8]:.1f} N=16:{nearc[16]:.1f}")
                    print("      " + "  ".join(line), flush=True)
                    res[f"{env}|{rname}|{rule}|sat"] = dict(mean=float(sat.mean()), min=int(sat.min()), p5=float(np.percentile(sat, 5)))
                res[f"{env}|{rname}|sweep_frac"] = float(np.nanmean(sf)); res[f"{env}|{rname}|near_frac"] = float(np.nanmean(nf_))
    json.dump(res, open(f"{S}/s3_swap_{'_'.join(ENVS)}.json", "w"), indent=1)
    print("total", time.time() - t0)
