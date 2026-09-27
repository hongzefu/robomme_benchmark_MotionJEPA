"""M2b：外部交换的「发起者顺延」变体——第 k 窗按 perm 从 perm[k%N] 起顺序试发起者，
取第一个「搭档=最近邻、联合连续证明通过、全程在相机内（BUS 另要求不进按钮避让圆）」的；
全部 N 个都不行才算该窗不可行（需要整套外部布局重抽）。顺延是确定性的，不新增随机数。

判据等级：
  ev   = 精确证明通过 ∧ 全程可见 ∧（BUS）离按钮中心 ≥ 0.0795+0.0424；
  evc  = ev ∧ 外部 mover 与任一内部容器的外接圆间隙 ≥ 0.04（「不进内部区」的实用口径）。
用法：m2b_fallback.py <task> <ring> <count> <N> <crit:ev|evc> [lane=0.07] [procs=8]
"""
import collections
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from m2_outer_sim import BTN_AVOID, DS, TWO_R, path  # noqa: E402
from multi_sweep import check_multi_swap_sweep  # noqa: E402
from replica import bus_layout, inner_sequence, vus_layout  # noqa: E402
from ring_sampler import RADIUS, V4_RING, V4PAD_RING, sample_ring, state, tight_ring  # noqa: E402

from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402


def mm(A, B):
    return float(np.min(np.linalg.norm(A - B, axis=1)))


def eval_window(k, a, b, ipos, iyaw, o, p, opos, oyaw, lane, buttons):
    ia_xy, ib_xy, v_in = path(ipos[a], ipos[b], 0.07)
    oa_xy, ob_xy, v_out = path(opos[o], opos[p], lane)
    inner_static = [ipos[j] for j in range(len(ipos)) if j not in (a, b)]
    outer_static = [opos[j] for j in range(len(opos)) if j not in (o, p)]
    c_partner = mm(oa_xy, ob_xy) - TWO_R
    c_os = min([min(mm(oa_xy, q[None]), mm(ob_xy, q[None])) for q in outer_static] or [np.inf]) - TWO_R
    c_is = min([min(mm(oa_xy, q[None]), mm(ob_xy, q[None])) for q in inner_static] or [np.inf]) - TWO_R
    c_im = min(mm(oa_xy, ia_xy), mm(oa_xy, ib_xy), mm(ob_xy, ia_xy), mm(ob_xy, ib_xy)) - TWO_R
    c_ios = min([min(mm(ia_xy, q[None]), mm(ib_xy, q[None])) for q in outer_static] or [np.inf]) - TWO_R
    risk = (c_partner <= 2 * v_out * DS / 2 or c_os <= v_out * DS / 2 or c_is <= v_out * DS / 2
            or c_im <= (v_out + v_in) * DS / 2 or c_ios <= v_in * DS / 2)
    exact_ok = True
    if risk:
        sa, sb = state(f"bin_{a}", *ipos[a], iyaw[a]), state(f"bin_{b}", *ipos[b], iyaw[b])
        so, sp = state(f"distractor_bin_{o}", *opos[o], oyaw[o]), state(f"distractor_bin_{p}", *opos[p], oyaw[p])
        by = [state(f"bin_{j}", *ipos[j], iyaw[j]) for j in range(len(ipos)) if j not in (a, b)]
        by += [state(f"distractor_bin_{j}", *opos[j], oyaw[j]) for j in range(len(opos)) if j not in (o, p)]
        names = {f"distractor_bin_{j}" for j in range(len(opos))}
        _g, rej, _n = check_multi_swap_sweep([(sa, sb), (so, sp)], by, lane_offsets=[0.07, lane], sweep_index=k,
                                             only_involving=names, circle_r=RADIUS)
        exact_ok = rej is None
    visible = all(ux.visible_on_camera(x, y, RADIUS) for x, y in np.vstack([oa_xy, ob_xy]))
    btn = min([min(mm(oa_xy, np.asarray(bt)[None]), mm(ob_xy, np.asarray(bt)[None])) for bt in buttons] or [np.inf])
    return dict(exact_ok=exact_ok, visible=visible, btn_ok=btn >= BTN_AVOID + RADIUS, c_inner=min(c_is, c_im),
                chord=float(np.linalg.norm(opos[o] - opos[p])))


def run_episode(args):
    task, seed, ring_name, count, crit, lane = args
    lay = (vus_layout if task == "VideoUnmaskSwap" else bus_layout)(seed)
    if lay.get("spawn_fail"):
        return {"skip": True}
    ring = {"v4": V4_RING, "v4pad": V4PAD_RING}.get(ring_name) or tight_ring(task)
    vis_radius = RADIUS + lane if ring_name == "v4pad" else None
    seq = inner_sequence(lay)
    sweeps = [(state(f"bin_{a}", *pos[a], yaw[a]), state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in seq]
    obstacles = [((b[0], b[1]), RADIUS) for b in lay["bins"]] + [((bx, by), BTN_AVOID) for bx, by in lay["buttons"]]
    gen = ux.distractor_generator(seed)
    placements = sample_ring(gen, ring=ring, count=count, obstacles=obstacles, sweeps=sweeps, vis_radius=vis_radius)
    if placements is None:
        return {"placement_fail": True}
    perm = torch.randperm(count, generator=gen).tolist()  # 追加在全部放置之后
    opos = [np.array(p[:2]) for p in placements]
    oyaw = [p[2] for p in placements]
    tries, pairs, feasible, moved = [], [], True, set()
    for k, (a, b, _d, ipos, iyaw) in enumerate(seq):
        chosen = None
        for j in range(count):
            o = perm[(k + j) % count]
            p = min((q for q in range(count) if q != o),
                    key=lambda q: (float(np.linalg.norm(np.asarray(opos[o], np.float32) - np.asarray(opos[q], np.float32))), q))
            r = eval_window(k, a, b, ipos, iyaw, o, p, opos, oyaw, lane, lay["buttons"])
            ok = r["exact_ok"] and r["visible"] and r["btn_ok"] and (crit == "ev" or r["c_inner"] >= 0.04)
            if ok:
                chosen = (o, p, j + 1, r["chord"])
                break
        if chosen is None:
            feasible = False
            break
        o, p, t, ch = chosen
        tries.append(t)
        pairs.append((min(o, p), max(o, p)))
        moved |= {o, p}
        opos[o], opos[p] = opos[p].copy(), opos[o].copy()
        oyaw[o], oyaw[p] = oyaw[p], oyaw[o]
    return {"feasible": feasible, "tries": tries, "pairs": pairs, "moved": len(moved), "n_swaps": lay["n_swaps"]}


if __name__ == "__main__":
    task, ring_name, count, n, crit = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    lane = float(sys.argv[6]) if len(sys.argv) > 6 else 0.07
    procs = int(sys.argv[7]) if len(sys.argv) > 7 else 8
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    jobs = [(task, base + i, ring_name, count, crit, lane) for i in range(n)]
    t0 = time.time()
    with mp.get_context("fork").Pool(procs) as pool:
        res = [r for r in pool.imap_unordered(run_episode, jobs, chunksize=2) if not r.get("skip")]
    eps = [r for r in res if "feasible" in r]
    feas = [r for r in eps if r["feasible"]]
    tries = collections.Counter(t for r in feas for t in r["tries"])
    undo = sum(1 for r in feas for k in range(1, len(r["pairs"])) if r["pairs"][k] == r["pairs"][k - 1])
    nsw = sum(len(r["pairs"]) for r in feas)
    out = {"task": task, "ring": ring_name, "count": count, "crit": crit, "lane": lane, "layouts": len(res),
           "placement_fail": sum(1 for r in res if r.get("placement_fail")), "episodes": len(eps),
           "ep_feasible": len(feas), "ep_feasible_rate": len(feas) / len(eps) if eps else None,
           "tries_hist(feasible eps)": dict(sorted(tries.items())),
           "distinct_moved_distractors_mean": float(np.mean([r["moved"] for r in feas])) if feas else None,
           "outer_immediate_undo_rate": undo / nsw if nsw else None, "wall_s": time.time() - t0}
    print("RESULT_FB " + json.dumps(out, ensure_ascii=False), flush=True)
