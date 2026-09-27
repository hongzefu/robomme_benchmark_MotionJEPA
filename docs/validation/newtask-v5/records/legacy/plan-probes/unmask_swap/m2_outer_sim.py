"""M2：外部干扰容器「每个内部交换窗口同时做一次最近邻交换」的可行性测量（纯几何）。

设计（被测对象，镜像内部规则）：
* 外部发起者：rot3 = 专用流在全部放置之后追加一次 randperm(count)[:3]，第 k 窗用第 k%3 个（与内部 a,b,c 循环同构）；
  rand = 每窗追加一次 randint(count)。
* 外部搭档：当前 XY 最近的另一个干扰容器（严格小于、并列取序号小者），与内部同一度量。
* 轨迹：与内部同一 swap_flat_two_lane（lane_offset 默认 0.07、smoothstep、同一窗口 64+33k）。
* 放置：ring_sampler.sample_ring（与仓库 sample_distractors 同判据：环内、相机可见、外接圆避让 0.04、
  对内部预演扫掠做静态候选检查）。

每个外部窗口统计（s 取 401 点，外接圆 r=0.0424 的中心距判据；判安全时再加相邻采样点间最大相对位移的一半作余量，
因此「圆判安全」是严格证明；圆判有风险的窗口再用仓库 _prove_pair 做同参数 s 的联合连续证明）：
  - 外部 mover 与：同对搭档 / 其他外部静止容器 / 内部静止容器 / 内部 mover 的最小外接圆间隙；
  - 是否出相机（visible_on_camera）、是否进入环的内边界、BUS 与按钮中心最近距离；
  - 联合精确证明（只查涉及干扰容器的对象对）是否通过。

用法：m2_outer_sim.py <task> <ring:v4|tight> <count> <rule:rot3|rand> <N> [lane_outer=0.07] [procs=10]
"""
from __future__ import annotations

import collections
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from multi_sweep import check_multi_swap_sweep  # noqa: E402
from replica import bus_layout, inner_sequence, vus_layout  # noqa: E402
from ring_sampler import RADIUS, V4_RING, V4PAD_RING, sample_ring, state, tight_ring  # noqa: E402

from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402

S = np.linspace(0.0, 1.0, 401)
DS = S[1] - S[0]
TWO_R = 2 * RADIUS
BTN_AVOID = float(np.linalg.norm([0.05625, 0.05625]))  # 按钮避让圆（与放置同口径）0.0795
BTN_CONTACT = 0.0375 * np.sqrt(2) + RADIUS  # 按钮底座外接圆 + 容器外接圆 0.0955


def path(xy_a, xy_b, lane):
    a, b = np.asarray(xy_a, float), np.asarray(xy_b, float)
    d = b - a
    n = np.array([-d[1], d[0]])
    nn = np.linalg.norm(n)
    n = n / nn if nn > 1e-9 else np.zeros(2)
    s = S[:, None]
    off = lane * np.sin(np.pi * s)
    return a + d * s + n * off, b - d * s - n * off, float(np.linalg.norm(d)) + lane * np.pi


def run_episode(args):
    task, seed, ring_name, count, rule, lane_outer = args
    t0 = time.perf_counter()
    lay = (vus_layout if task == "VideoUnmaskSwap" else bus_layout)(seed)
    if len(lay["bins"]) < 4:
        return {"skip": True}
    ring = {"v4": V4_RING, "v4pad": V4PAD_RING}.get(ring_name) or tight_ring(task)
    vis_radius = RADIUS + lane_outer if ring_name == "v4pad" else None
    seq = inner_sequence(lay)
    sweeps = [(state(f"bin_{a}", *pos[a], yaw[a]), state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in seq]
    obstacles = [((b[0], b[1]), RADIUS) for b in lay["bins"]] + [((bx, by), BTN_AVOID) for bx, by in lay["buttons"]]
    gen = ux.distractor_generator(seed)
    placements = sample_ring(gen, ring=ring, count=count, obstacles=obstacles, sweeps=sweeps, vis_radius=vis_radius)
    if placements is None:
        return {"placement_fail": True, "t": time.perf_counter() - t0}
    # 外部发起者：追加在全部放置之后（N5）
    if rule == "rot3":
        init3 = torch.randperm(count, generator=gen)[:3].tolist()
        outer_inits = [init3[k % 3] for k in range(lay["n_swaps"])]
    elif rule == "perm":  # randperm(count) 一次，按全体干扰容器轮转
        perm = torch.randperm(count, generator=gen).tolist()
        outer_inits = [perm[k % count] for k in range(lay["n_swaps"])]
    else:
        outer_inits = [int(torch.randint(count, (1,), generator=gen).item()) for _ in range(lay["n_swaps"])]
    opos = [np.array(p[:2]) for p in placements]
    oyaw = [p[2] for p in placements]
    win = []
    for k, (a, b, _d, ipos, iyaw) in enumerate(seq):
        o = outer_inits[k]
        p, best = None, np.inf
        dl = []
        for j, q in enumerate(opos):
            if j == o:
                continue
            dist = float(np.linalg.norm(np.asarray(opos[o], np.float32) - np.asarray(q, np.float32)))
            dl.append(dist)
            if dist < best:
                p, best = j, dist
        dl.sort()
        ia_xy, ib_xy, v_in = path(ipos[a], ipos[b], 0.07)
        oa_xy, ob_xy, v_out = path(opos[o], opos[p], lane_outer)
        inner_static = [ipos[j] for j in range(len(ipos)) if j not in (a, b)]
        outer_static = [opos[j] for j in range(len(opos)) if j not in (o, p)]
        rec = {"chord": best, "nn_margin": (dl[1] - dl[0]) if len(dl) > 1 else np.inf}
        # 最小外接圆间隙（中心距 − 2r），各类别
        mm = lambda A, B: float(np.min(np.linalg.norm(A - B, axis=1)))  # noqa: E731
        rec["c_partner"] = mm(oa_xy, ob_xy) - TWO_R
        rec["c_outer_static"] = min([min(mm(oa_xy, q[None]), mm(ob_xy, q[None])) for q in outer_static] or [np.inf]) - TWO_R
        rec["c_inner_static"] = min([min(mm(oa_xy, q[None]), mm(ob_xy, q[None])) for q in inner_static] or [np.inf]) - TWO_R
        rec["c_inner_mover"] = min(mm(oa_xy, ia_xy), mm(oa_xy, ib_xy), mm(ob_xy, ia_xy), mm(ob_xy, ib_xy)) - TWO_R
        # 内部 mover 对外部静止容器（V4 已在放置时按原 yaw 静态检查过；外部换位后 yaw 会随之换，这里按圆复核）
        rec["c_innermover_outerstatic"] = min([min(mm(ia_xy, q[None]), mm(ib_xy, q[None])) for q in outer_static] or [np.inf]) - TWO_R
        margin_mm = (v_out + v_out) * DS / 2
        margin_mo = (v_out + v_in) * DS / 2
        margin_ms = v_out * DS / 2
        margin_is = v_in * DS / 2
        risk = (rec["c_partner"] <= margin_mm or rec["c_outer_static"] <= margin_ms or rec["c_inner_static"] <= margin_ms
                or rec["c_inner_mover"] <= margin_mo or rec["c_innermover_outerstatic"] <= margin_is)
        rec["circle_risk"] = bool(risk)
        vis = all(ux.visible_on_camera(x, y, RADIUS) for x, y in np.vstack([oa_xy, ob_xy]))
        rec["visible"] = bool(vis)
        rec["intrude"] = bool(any(ring.inside_inner(x, y) for x, y in np.vstack([oa_xy, ob_xy])))
        rec["min_maxnorm"] = float(np.min(np.max(np.abs(np.vstack([oa_xy, ob_xy])), axis=1)))
        if lay["buttons"]:
            rec["btn_min"] = min(mm(oa_xy, np.asarray(bt)[None]) for bt in lay["buttons"])
            rec["btn_min"] = min(rec["btn_min"], min(mm(ob_xy, np.asarray(bt)[None]) for bt in lay["buttons"]))
        exact_ok, exact_kind = True, None
        if risk:
            sa, sb = state(f"bin_{a}", *ipos[a], iyaw[a]), state(f"bin_{b}", *ipos[b], iyaw[b])
            so, sp = state(f"distractor_bin_{o}", *opos[o], oyaw[o]), state(f"distractor_bin_{p}", *opos[p], oyaw[p])
            by = [state(f"bin_{j}", *ipos[j], iyaw[j]) for j in range(len(ipos)) if j not in (a, b)]
            by += [state(f"distractor_bin_{j}", *opos[j], oyaw[j]) for j in range(len(opos)) if j not in (o, p)]
            names = {f"distractor_bin_{j}" for j in range(len(opos))}
            _g, rej, _n = check_multi_swap_sweep([(sa, sb), (so, sp)], by, lane_offsets=[0.07, lane_outer],
                                                 sweep_index=k, only_involving=names)
            if rej is not None:
                exact_ok = False
                pair = {rej.object_a, rej.object_b}
                inner_m = {f"bin_{a}", f"bin_{b}"}
                outer_m = {f"distractor_bin_{o}", f"distractor_bin_{p}"}
                if pair <= outer_m:
                    exact_kind = "outer_pair_self"
                elif pair & outer_m and pair & inner_m:
                    exact_kind = "outer_mover_vs_inner_mover"
                elif pair & outer_m and any(n.startswith("bin_") for n in pair):
                    exact_kind = "outer_mover_vs_inner_static"
                elif pair & outer_m:
                    exact_kind = "outer_mover_vs_outer_static"
                elif pair & inner_m:
                    exact_kind = "inner_mover_vs_outer_static"
                else:
                    exact_kind = "other:" + ",".join(sorted(pair))
        rec["exact_ok"] = exact_ok
        rec["exact_kind"] = exact_kind
        rec["pair"] = (min(o, p), max(o, p))
        win.append(rec)
        opos[o], opos[p] = opos[p].copy(), opos[o].copy()
        oyaw[o], oyaw[p] = oyaw[p], oyaw[o]
    return {"win": win, "t": time.perf_counter() - t0, "n_swaps": lay["n_swaps"]}


def summarize(task, ring_name, count, rule, lane, results, wall):
    eps = [r for r in results if not r.get("skip")]
    pf = sum(1 for r in eps if r.get("placement_fail"))
    ok_eps = [r for r in eps if "win" in r]
    wins = [w for r in ok_eps for w in r["win"]]
    n_ep = len(ok_eps)
    ep_exact = sum(all(w["exact_ok"] for w in r["win"]) for r in ok_eps)
    ep_full = sum(all(w["exact_ok"] and w["visible"] and not w["intrude"] for w in r["win"]) for r in ok_eps)
    ep_exact_vis = sum(all(w["exact_ok"] and w["visible"] for w in r["win"]) for r in ok_eps)
    cin = np.array([min(w["c_inner_static"], w["c_inner_mover"]) for w in wins]) if wins else np.array([np.nan])
    if task == "ButtonUnmaskSwap":
        ep_full_btn = sum(all(w["exact_ok"] and w["visible"] and not w["intrude"] and w["btn_min"] >= BTN_AVOID + RADIUS
                              for w in r["win"]) for r in ok_eps)
    else:
        ep_full_btn = ep_full
    kinds = collections.Counter(w["exact_kind"] for w in wins if not w["exact_ok"])
    chord = np.array([w["chord"] for w in wins]) if wins else np.array([np.nan])
    allc = np.array([min(w["c_partner"], w["c_outer_static"], w["c_inner_static"], w["c_inner_mover"]) for w in wins]) if wins else np.array([np.nan])
    distinct = collections.Counter(len({w["pair"] for w in r["win"]}) for r in ok_eps)
    undo = sum(1 for r in ok_eps for k in range(1, len(r["win"])) if r["win"][k]["pair"] == r["win"][k - 1]["pair"])
    out = {
        "task": task, "ring": ring_name, "count": count, "rule": rule, "lane_outer": lane, "layouts": len(eps),
        "placement_fail": pf, "episodes": n_ep, "windows": len(wins),
        "ep_exact_ok": ep_exact, "ep_exact_rate": ep_exact / n_ep if n_ep else None,
        "ep_exact_visible_ok": ep_exact_vis, "ep_exact_visible_rate": ep_exact_vis / n_ep if n_ep else None,
        "ep_full_ok(exact+visible+no_intrude)": ep_full, "ep_full_rate": ep_full / n_ep if n_ep else None,
        "ep_full_btn_ok": ep_full_btn,
        "win_exact_fail": sum(not w["exact_ok"] for w in wins), "win_fail_kinds": dict(kinds),
        "win_circle_risk": sum(w["circle_risk"] for w in wins),
        "win_not_visible": sum(not w["visible"] for w in wins), "win_intrude": sum(w["intrude"] for w in wins),
        "win_inner_circle_clear_lt0": int(np.sum(cin < 0)), "win_inner_circle_clear_lt0.04": int(np.sum(cin < 0.04)),
        "win_clear_lt0.02": int(np.sum(allc < 0.02)), "win_clear_lt0.04": int(np.sum(allc < 0.04)),
        "chord_m": {"p5": float(np.percentile(chord, 5)), "median": float(np.median(chord)), "p95": float(np.percentile(chord, 95)), "max": float(np.max(chord))},
        "win_nn_margin_lt_1mm": sum(w["nn_margin"] < 0.001 for w in wins),
        "min_maxnorm_p5": float(np.percentile([w["min_maxnorm"] for w in wins], 5)) if wins else None,
        "distinct_outer_pairs_per_ep": dict(sorted(distinct.items())), "outer_immediate_undo": undo,
        "sec_per_episode_mean": float(np.mean([r["t"] for r in eps if "t" in r])), "wall_s": wall,
    }
    if task == "ButtonUnmaskSwap" and wins:
        b = np.array([w["btn_min"] for w in wins])
        out["btn_min_center_dist"] = {"min": float(b.min()), "p5": float(np.percentile(b, 5))}
        out["win_btn_lt_avoid(0.122)"] = int(np.sum(b < BTN_AVOID + RADIUS))
        out["win_btn_lt_contact(0.0955)"] = int(np.sum(b < BTN_CONTACT))
    return out


if __name__ == "__main__":
    task, ring_name, count, rule, n = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
    lane = float(sys.argv[6]) if len(sys.argv) > 6 else 0.07
    procs = int(sys.argv[7]) if len(sys.argv) > 7 else 10
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    jobs = [(task, base + i, ring_name, count, rule, lane) for i in range(n)]
    t0 = time.time()
    with mp.get_context("fork").Pool(procs) as pool:
        results = list(pool.imap_unordered(run_episode, jobs, chunksize=2))
    summary = summarize(task, ring_name, count, rule, lane, results, time.time() - t0)
    print("RESULT " + json.dumps(summary, ensure_ascii=False), flush=True)
