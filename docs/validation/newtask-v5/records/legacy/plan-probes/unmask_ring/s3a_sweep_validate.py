# 快速扫掠近似 vs 源码 check_swap_sweep（精确区间二分）的一致性 + 精确判据耗时
import sys, time, math, json
import numpy as np
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
rng = np.random.default_rng(11)
agree = dis = 0; fast_only = exact_only = 0
t_exact = []; t_exact_far = []
rows = []
for lay_i in range(6):
    lay = L.inner_vus(rng) if lay_i % 2 == 0 else L.inner_bus(rng)
    bins = lay[0]
    sw = L.predict_sweeps(bins, L.swap_initiators(rng), 8)
    samp = L.sweep_samples(sw)
    # 挑靠近扫掠路径的候选（距某抽样中心 0.03~0.12）+ 若干远点
    cs = samp[0]
    k = 0
    while k < 14:
        base = cs[rng.integers(len(cs))]
        off = rng.normal(size=2); off /= np.linalg.norm(off)
        xy = base + off * rng.uniform(0.03, 0.12)
        yaw = rng.random() * 90
        t0 = time.time(); ex = L.sweep_hits(xy, yaw, sw); t_exact.append(time.time() - t0)
        fa = L.sweep_hits_fast(xy, yaw, samp)
        agree += ex == fa; dis += ex != fa; fast_only += fa and not ex; exact_only += ex and not fa
        rows.append(dict(xy=list(map(float, xy)), yaw=yaw, exact=bool(ex), fast=bool(fa), t=t_exact[-1]))
        k += 1
    print(f"layout {lay_i}: done, cumulative agree={agree} disagree={dis} (fast_only={fast_only}, exact_only={exact_only}); exact mean {np.mean(t_exact)*1000:.0f} ms max {np.max(t_exact)*1000:.0f} ms", flush=True)
json.dump(rows, open(f"{S}/s3a_rows.json", "w"))
