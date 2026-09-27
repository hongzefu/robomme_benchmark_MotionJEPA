"""P3b：外环可行槽对为何这么稀——第 0 窗全部 45 个槽对的拒绝原因分布（按 evaluate_outer_candidate 的检查顺序
vis→btn→inner_clear→exact 记第一个失败项），以及放宽约束后的密度/「零可行搭档槽」比例：
  base   = V5 配置原样
  novis  = 去掉路径全程可见（camera_visible=False）
  noclr  = 内环圆净距 0.04 → 0（只靠精确联合证明）
  both   = 两者都去
用法：p3b_reasons.py <task> <N> [procs]"""
import collections, dataclasses, json, multiprocessing as mp, sys
import numpy as np
sys.path.insert(0, ".")
from mclib import *  # noqa
from p3_outer_mc import v5_inner_windows  # noqa

def one(args):
    task, seed = args
    lay = inner_layout(task, seed)
    if lay.get("spawn_fail"): return None
    wins = v5_inner_windows(lay)
    if ux.prejudge_inner_windows(wins) is not None: return None
    base = ux.parse_distractor_swap_cfg(ux.v5_distractor_swap_cfg(task))
    variants = {"base": base, "novis": dataclasses.replace(base, camera_visible=False),
                "noclr": dataclasses.replace(base, min_inner_circle_clearance_m=0.0),
                "both": dataclasses.replace(base, camera_visible=False, min_inner_circle_clearance_m=0.0)}
    guard = ux.InnerSweepGuard(wins); pad = ux.padded_bin_shapes(CH, base.plan_pad_m)
    try:
        layout = sample_distractor_layout(ux.v5_distractor_cfg(task), obstacles=obstacles(lay), generator=ux.distractor_generator(seed),
                                          cube_half_size=CH, extra_reject=lambda i, x, y, yaw, _p: guard.first_rejection(
                                              ux.distractor_bin_state(i, x, y, yaw, CH, pad)) is not None)
    except DistractorPlacementError:
        return None
    outer = [ux.distractor_bin_state(i, x, y, yaw, CH, pad) for i, (x, y, yaw) in enumerate(layout.bins)]
    xy = np.array([s.p[:2] for s in outer]); D = np.linalg.norm(xy[:, None] - xy[None], axis=-1) + np.eye(10) * 9
    pairs = [(a, b) for a in range(10) for b in range(a + 1, 10)]
    out = {}
    for name, cfg in variants.items():
        reasons = collections.Counter(); nn_reasons = collections.Counter(); deg = np.zeros(10)
        for a, b in pairs:
            ok, r, _ = ux.evaluate_outer_candidate(0, wins[0], a, b, outer, cfg=cfg, cube_half_size=CH,
                                                   buttons_xy=[np.asarray(v) for v in lay["buttons"]])
            key = "ok" if ok else r
            reasons[key] += 1
            if int(np.argmin(D[a])) == b or int(np.argmin(D[b])) == a:
                nn_reasons[key] += 1
            if ok: deg[a] += 1; deg[b] += 1
        out[name] = {"reasons": dict(reasons), "nn": dict(nn_reasons), "zero_deg": float(np.mean(deg == 0))}
    return out

if __name__ == "__main__":
    task = sys.argv[1]; N = int(sys.argv[2]); procs = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    with mp.Pool(procs) as pool:
        res = [r for r in pool.imap_unordered(one, [(task, base + i) for i in range(N)], chunksize=4) if r]
    for name in ("base", "novis", "noclr", "both"):
        tot = collections.Counter(); nn = collections.Counter()
        for r in res: tot.update(r[name]["reasons"]); nn.update(r[name]["nn"])
        s = sum(tot.values()); sn = sum(nn.values())
        print(f"P3B {task} {name} 局={len(res)} 全部槽对：" + " ".join(f"{k}={v/s:.3f}" for k, v in sorted(tot.items())) +
              " | 最近邻对：" + " ".join(f"{k}={v/sn:.3f}" for k, v in sorted(nn.items())) +
              f" | 零可行搭档槽占比 {np.mean([r[name]['zero_deg'] for r in res]):.3f}")
