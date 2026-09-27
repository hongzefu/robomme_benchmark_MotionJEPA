"""V6 探针 P4：干扰环带容量——仓库 V5 统一采样器（sample_distractor_layout，精确可见、OBB 避让、1024 次）
在给定内部布局上能放多少个干扰容器；VU/BU 用贴身环带 [0.2425,0.3289]，VUS/BUS 用 V4 环带 [0.2675,0.45]
（VUS/BUS 这里不加 H1 扫掠守卫，得到的是容量上界；外环交换可行率另见 P3 的 count 扫描）。
内部布局：VU 8 个容器 region ±0.2、min_gap 0.015（replica 的 spawn_random_bin 复刻）；BU 加按钮 OBB；VUS/BUS 用 replica。
输出：各 N 的一次放满率（1024 次/个），以及「饱和容量」（逐个放直到某个 1024 次都放不下）。
用法：p4_ring_capacity.py <task> <layouts> [procs]
"""
import json, multiprocessing as mp, sys, time
import numpy as np, torch
sys.path.insert(0, ".")
from mclib import *  # noqa
from replica import spawn_random_bin_replica, _bin_obb  # noqa
from robomme.robomme_env.utils.unmask_distractor_sampler import V5_DISTRACTOR_PRESETS, bin_visible, point_hits_obbs  # noqa
from robomme.robomme_env.utils.unmask_distractors import in_ring, bin_geometry  # noqa

NS = list(range(10, 31, 2))


def inner(task, seed):
    gen = torch.Generator(); gen.manual_seed(seed)
    if task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        lay = inner_layout(task, seed)
        return None if lay.get("spawn_fail") else obstacles(lay)
    obbs = []
    if task == "ButtonUnmask":
        off = (torch.rand(2, generator=gen) - 0.5) * 0.1
        c = np.array([-0.2 + float(off[0]), float(off[1])])
        obbs.append((c, np.eye(2), np.array([BTN_HALF, BTN_HALF])))
    out = []
    for i in range(8):
        r = spawn_random_bin_replica(gen, obbs, [0, 0], 0.2, CH * 0.75)
        if r is None:
            return None
        obbs.append(_bin_obb(*r, CH * 0.75)); out.append(r)
    obst = [o for o in obbs[: (1 if task == "ButtonUnmask" else 0)]]
    return obst + [bin_obb2d(x, y, yaw, CH, pad=CH * 0.75) for x, y, yaw in out]


def saturate(cfg, obst, seed):
    gen = ux.distractor_generator(seed)
    half, _r, _h = bin_geometry(CH)
    ring = cfg["ring_max_abs_xy"]; span = ring[1]
    reach = half + CH * 0.75
    obbs = list(obst); n = 0
    while True:
        placed = False
        for _ in range(1024):
            x = float(torch.rand(1, generator=gen).item() * 2 * span - span)
            y = float(torch.rand(1, generator=gen).item() * 2 * span - span)
            if not in_ring(x, y, ring) or not bin_visible(x, y, CH):
                continue
            if point_hits_obbs(np.array([x, y]), obbs, reach):
                continue
            yaw = float(torch.rand(1, generator=gen).item() * 90)
            obbs.append(bin_obb2d(x, y, yaw, CH, pad=CH * 0.75)); n += 1; placed = True
            break
        if not placed:
            return n


def one(args):
    task, seed = args
    obst = inner(task, seed)
    if obst is None:
        return None
    cfg = dict(V5_DISTRACTOR_PRESETS[task])
    res = {}
    for N in NS:
        c = dict(cfg); c["count"] = N; c["cube_count_range"] = [0, 0]
        try:
            sample_distractor_layout(c, obstacles=obst, generator=ux.distractor_generator(seed), cube_half_size=CH)
            res[N] = 1
        except DistractorPlacementError:
            res[N] = 0
    return {"seed": seed, "fill": res, "sat": saturate(cfg, obst, seed + 7)}


if __name__ == "__main__":
    task = sys.argv[1]; L = int(sys.argv[2]); procs = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    t0 = time.time()
    with mp.Pool(procs) as pool:
        res = [r for r in pool.imap_unordered(one, [(task, 9_500_000 + i) for i in range(L)], chunksize=5) if r]
    sat = np.array([r["sat"] for r in res])
    line = " ".join(f"N{N}={np.mean([r['fill'][N] for r in res]):.3f}" for N in NS)
    print(f"P4 task={task} layouts={len(res)} {line} sat_min={sat.min()} sat_p5={np.percentile(sat,5):.0f} sat_med={np.median(sat):.0f} sat_max={sat.max()} wall={time.time()-t0:.0f}s")
    json.dump(res, open(f"p4_{task}.json", "w"))
