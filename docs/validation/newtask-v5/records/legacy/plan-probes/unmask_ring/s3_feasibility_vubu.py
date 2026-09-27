# 步 3a：VideoUnmask / ButtonUnmask 外环放置可行性（每配置 600 局；内层 8 容器按 G2 判据先放，失败局剔除并计数）
import sys, json, math, time
import numpy as np
from multiprocessing import Pool
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L

NTRIAL = 500
RINGS = {
    # 名称: (inner rect, d_in, d_out) —— d 是中心到区域边的切比雪夫距离
    "A g.015 W.1414 [0.2425,0.3289]": ((-0.2, 0.2, -0.2, 0.2), 0.0425, 0.1289),
    "B g.015 W.085 [0.2425,0.2725]": ((-0.2, 0.2, -0.2, 0.2), 0.0425, 0.0725),
    "C g.040 W.1414 [0.2675,0.3539]": ((-0.2, 0.2, -0.2, 0.2), 0.0675, 0.1539),
    "D g.000 W.1414 [0.2275,0.3139]": ((-0.2, 0.2, -0.2, 0.2), 0.0275, 0.1139),
    "V4 [0.2675,0.45]": ((0, 0, 0, 0), 0.2675, 0.45),
}
NS = {"VU": [8, 9, 10, 12, 14, 15, 16, 18, 20, 24], "BU": [8, 9, 10, 12, 14, 15, 16, 18, 20, 24]}


def one(args):
    env, seed = args
    rng = np.random.default_rng(seed)
    lay = L.inner_unmask(rng, button=(env == "BU"))
    if lay is None:
        return None
    bins, bcen, obbs = lay
    out = {}
    for rname, (inner, a, b) in RINGS.items():
        ring = L.RectRing(inner, a, b)
        for mt in (256, 1024):
            for n in NS[env]:
                r2 = np.random.default_rng(seed * 1000 + n + 7 * mt)
                placed, nf = L.place_ring_generic(r2, ring, n, obbs, max_trials=mt)
                out[(rname, mt, n)] = (nf == 0, len(placed))
        # 饱和容量：请求 80、每个 4096 次尝试
        r2 = np.random.default_rng(seed * 1000 + 999)
        placed, nf = L.place_ring_generic(r2, ring, (70 if rname.startswith("V4") else 45), obbs, max_trials=2048)
        out[(rname, 'sat', 80)] = (False, len(placed))
    return out


if __name__ == "__main__":
    res = {}
    t0 = time.time()
    with Pool(8) as pool:
        for env in ("VU", "BU"):
            outs = pool.map(one, [(env, 100000 + s) for s in range(NTRIAL)])
            inner_fail = sum(o is None for o in outs)
            outs = [o for o in outs if o is not None]
            print(f"\n=== {env}: 内层 8 容器放置失败 {inner_fail}/{NTRIAL}，有效 {len(outs)} 局（{time.time()-t0:.0f}s）===")
            for rname in RINGS:
                sat = np.array([o[(rname, 'sat', 80)][1] for o in outs])
                print(f"  [{rname}] 饱和容量（请求 45/V4 环 70、2048 次/个）: mean {sat.mean():.1f} min {sat.min()} p5 {np.percentile(sat,5):.0f} max {sat.max()}")
                for mt in (256, 1024):
                    line = []
                    for n in NS[env]:
                        ok = np.array([o[(rname, mt, n)][0] for o in outs])
                        got = np.array([o[(rname, mt, n)][1] for o in outs])
                        line.append(f"N={n}:{100*ok.mean():.1f}%({got.min()}-{got.max()})")
                        res[f"{env}|{rname}|{mt}|{n}"] = dict(all_rate=float(ok.mean()), got_min=int(got.min()), got_mean=float(got.mean()))
                    print(f"    max_trials={mt}: " + "  ".join(line))
                res[f"{env}|{rname}|sat"] = dict(mean=float(sat.mean()), min=int(sat.min()), max=int(sat.max()))
    json.dump(res, open(f"{S}/s3_vubu.json", "w"), indent=1)
    print("total", time.time() - t0)
