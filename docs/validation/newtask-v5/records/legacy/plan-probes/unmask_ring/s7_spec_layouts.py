# 步 7：用 specs.jsonl 里 V4 冻结的 10 条内层布局/环境逐条复核推荐方案（每条布局 100 条干扰流 ⇒ 每环境 1000 次）
import sys, json, math
import numpy as np
from multiprocessing import Pool
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
rows = [json.loads(l) for l in open("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/configs/newtask-v4/v4-01/specs.jsonl")][1:]
PLAN = {
    "VideoUnmask": (L.RectRing((-0.2, 0.2, -0.2, 0.2), 0.0425, 0.1289), 15, 1024),
    "ButtonUnmask": (L.RectRing((-0.2, 0.2, -0.2, 0.2), 0.0425, 0.1289), 14, 1024),
    "VideoUnmaskSwap": (L.RectRing((-0.2114, 0.2114, -0.2114, 0.2114), 0.0425, 0.1289), 16, 512),
    "ButtonUnmaskSwap": (L.RectRing((-0.2625, 0.17, -0.17, 0.27), 0.0425, 0.1289), 16, 512),
}
gap = L.CHS * 0.75


def job(args):
    task, ep = args
    r = [x for x in rows if x["task"] == task and x["episode"] == ep][0]["spec"]
    bins = [(np.array(v[:2]), math.radians(v[2])) for v in r["layout"]["bins"].values()]
    obbs = [(p, L.footprint_axes(math.degrees(y)), np.array([L.OBB_HALF + gap] * 2)) for p, y in bins]
    samp = sweeps = None
    if task == "ButtonUnmask":
        obbs.append((np.array(r["layout"]["button_xy"]), np.eye(2), np.array([L.BTN_HALF] * 2)))
    if task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        o = r["objects"]
        init = list(o["swap_initiator_indices"]) + [o["swap_initiator_third"]]
        sweeps = L.predict_sweeps(bins, init, int(o["n_swaps"]))
        samp = L.sweep_samples(sweeps)
    ring, n, mt = PLAN[task]
    res = []
    for k in range(100):
        rng = np.random.default_rng(ep * 7919 + k)
        fixed = list(obbs)
        if task == "ButtonUnmaskSwap":   # 规格未记按钮位置 ⇒ 每条流随机抽按钮（与源码同分布）
            for base in ([-0.2, -0.1], [-0.2, 0.1]):
                fixed.append((np.array(base) + (rng.random(2) - 0.5) * 0.05, np.eye(2), np.array([L.BTN_HALF] * 2)))
        placed, nf = L.place_ring_generic(rng, ring, n, fixed, max_trials=mt, samp=samp)
        res.append((nf == 0, len(placed)))
    return task, ep, res


if __name__ == "__main__":
    jobs = [(t, x["episode"]) for t in PLAN for x in rows if x["task"] == t]
    with Pool(8) as pool:
        out = pool.map(job, jobs)
    for t in PLAN:
        per = [(ep, np.mean([a for a, _ in res]), min(b for _, b in res)) for tt, ep, res in out if tt == t]
        allok = np.mean([a for tt, ep, res in out if tt == t for a, _ in res])
        print(f"{t}: N={PLAN[t][1]} 全部放下率 {100*allok:.1f}%（10 条冻结布局 × 100 流）；逐布局: " +
              ", ".join(f"ep{ep}:{100*m:.0f}%" for ep, m, _ in per) + f"；最少放下 {min(c for _, _, c in per)}")
