"""P5 问题 1：离线联合可行性（最终规则）。内环布局 = 已验证副本 replica.py（逐值对拍见 verify_replica.py）。

用法：offline_joint.py <task> <N> [procs=12] [prefilter=1]
输出：每局一行 EP {...}（写 jsonl），末尾 SUMMARY {...}
"""
import collections
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np  # noqa: E402

import swap10lib as L  # noqa: E402
from replica import bus_layout, initiators, vus_layout  # noqa: E402
from robomme.robomme_env.utils.unmask_swap_xhard import distractor_generator  # noqa: E402

BTN_HALF = 0.025 * 1.5 * 1.5  # create_button_obb 的轴对齐半边（与 replica 同口径）


def inputs_from_replica(lay):
    states = [L.state(f"bin_{i}", x, y, yaw) for i, (x, y, yaw) in enumerate(lay["bins"])]
    positions = [np.array([x, y], dtype=np.float32) for x, y, _ in lay["bins"]]
    seq = L.predict_inner(states, positions, initiators(lay))
    obbs = [(np.asarray(b, float), np.eye(2), np.array([BTN_HALF, BTN_HALF])) for b in lay["buttons"]]
    obbs += [L.bin_obb(s.p[0], s.p[1], s.q, L.CFG["min_gap"]) for s in states]
    return seq, obbs


def run(args):
    task, seed = args
    t0 = time.perf_counter()
    for k in L.STATS:
        L.STATS[k] = 0 if isinstance(L.STATS[k], int) else 0.0
    lay = (vus_layout if task == "VideoUnmaskSwap" else bus_layout)(seed)
    if lay.get("spawn_fail"):
        return dict(seed=seed, status="inner_spawn_fail", t=time.perf_counter() - t0)
    seq, obbs = inputs_from_replica(lay)
    try:
        res = L.plan_episode(distractor_generator(seed), obbs, seq, lay["buttons"])
    except L.SceneReject as exc:
        return dict(seed=seed, status=exc.kind, msg=str(exc), n_swaps=len(seq), t=time.perf_counter() - t0, **dict(L.STATS))
    return dict(seed=seed, status="ok", n_swaps=len(seq), n_attempts=res["n_attempts"],
                attempts=res["attempts"], pairs=res["plan"]["pairs"], near_tie=res["plan"]["near_tie"],
                placements=res["layout"]["placements"], cube_bins=res["layout"]["cube_bins"],
                cube_colors=res["layout"]["cube_colors"], t=time.perf_counter() - t0, **dict(L.STATS))


def summarize(task, rows):
    n = len(rows)
    st = collections.Counter(r["status"] for r in rows)
    ok = [r for r in rows if r["status"] == "ok"]
    judged = [r for r in rows if r["status"] in ("ok", "exhausted", "placement")]  # 过了内环预判、进入外环规划的局
    first = sum(1 for r in ok if r["n_attempts"] == 1)
    all_att = [a for r in ok for a in r["attempts"]]
    tries = collections.Counter(t for r in ok for t in r["attempts"][-1]["tries"])
    fails = collections.Counter()
    for r in ok:
        for a in r["attempts"]:
            fails.update(a["fails"])
    undo = sum(1 for r in ok for k in range(1, len(r["pairs"]))
               if set(r["pairs"][k]) == set(r["pairs"][k - 1]))
    nwin = sum(len(r["pairs"]) for r in ok)
    moved = [len({i for pr in r["pairs"] for i in pr}) for r in ok]
    colors = collections.Counter(c for r in ok for c in r["cube_colors"])
    t = np.array([r["t"] for r in rows])
    return {
        "task": task, "layouts": n, "status": dict(st),
        "inner_inner_reject_rate": round(st.get("inner_inner", 0) / n, 4),
        "inner_spawn_fail_rate": round(st.get("inner_spawn_fail", 0) / n, 4),
        "entered_outer_planning": len(judged),
        "first_layout_feasible_rate(of_entered)": round(first / len(judged), 4) if judged else None,
        "final_ok_rate(of_entered)": round(len(ok) / len(judged), 4) if judged else None,
        "exhaust16_rate(of_entered)": round(st.get("exhausted", 0) / len(judged), 4) if judged else None,
        "placement_fail(of_entered)": st.get("placement", 0),
        "mean_redraws(ok)": round(float(np.mean([r["n_attempts"] - 1 for r in ok])), 4) if ok else None,
        "max_attempts(ok)": max((r["n_attempts"] for r in ok), default=None),
        "attempt_hist": dict(sorted(collections.Counter(r["n_attempts"] for r in ok).items())),
        "first_candidate_window_share(final_plan)": round(tries.get(1, 0) / max(1, sum(tries.values())), 4),
        "tries_hist(final_plan)": dict(sorted(tries.items())),
        "reject_reasons(all_candidates)": dict(fails),
        "failed_attempts_total": sum(1 for a in all_att if not a["ok"]),
        "outer_immediate_undo_rate": round(undo / nwin, 4) if nwin else None,
        "distinct_moved_distractors_mean": round(float(np.mean(moved)), 2) if moved else None,
        "near_tie_windows(<5mm)": sum(r["near_tie"] for r in ok), "windows": nwin,
        "cube_color_counts": dict(colors),
        "plan_s": {"mean": round(float(t.mean()), 3), "p50": round(float(np.percentile(t, 50)), 3),
                   "p95": round(float(np.percentile(t, 95)), 3), "max": round(float(t.max()), 3)},
        "h1_calls_mean": round(float(np.mean([r.get("h1_calls", 0) for r in rows])), 1),
        "joint_calls_mean": round(float(np.mean([r.get("joint_calls", 0) for r in rows])), 1),
        "prefilter": L.PREFILTER,
    }


if __name__ == "__main__":
    task, n = sys.argv[1], int(sys.argv[2])
    procs = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    tag = sys.argv[4] if len(sys.argv) > 4 else "main"
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    out = HERE / f"offline_{task}_{tag}.jsonl"
    t0 = time.time()
    rows = []
    with mp.get_context("fork").Pool(procs) as pool, open(out, "w") as fh:
        for r in pool.imap_unordered(run, [(task, base + i) for i in range(n)], chunksize=1):
            rows.append(r)
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            if len(rows) % 50 == 0:
                print(f"进度 {task} {len(rows)}/{n} {time.time() - t0:.0f}s", flush=True)
    rows.sort(key=lambda r: r["seed"])
    s = summarize(task, rows)
    s["wall_s"] = round(time.time() - t0, 1)
    print("SUMMARY " + json.dumps(s, ensure_ascii=False), flush=True)
