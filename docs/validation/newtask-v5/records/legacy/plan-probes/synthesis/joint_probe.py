"""跨课题抽查：unmask_ring 推荐的贴边外环 + 密度个数（VUS 15 / BUS 16）× unmask_swap 推荐的外部最近邻交换（顺延回退）。
复用 unmask_swap 课题的 scratch 复刻（replica / ring_sampler / m2b_fallback.eval_window），只替换：
  * 环：VUS 切比雪夫中心带 [0.2539, 0.3403]；BUS 内矩形（含按钮）[-0.2625,0.17]×[-0.17,0.27] 外扩中心带 [0.0425, 0.1289]；
  * 放置间距：外接圆近似「统一 OBB 规则」（中心距 ≥ 2r + 0.003 ≈ 0.0878，≈ 正对 0.0875）；
  * 可见性：精确 8 角点针孔判据（替换线性近似，路径可见也用精确判据）；
  * 放置预算 1024。
用法：joint_probe.py <task> <count> <N> <crit ev|evc> [lane] [procs] [ringvariant A|C]
"""
import sys, json, time, collections, multiprocessing as mp
from pathlib import Path
import numpy as np, torch
SP = Path("/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap")
sys.path.insert(0, str(SP))
from robomme.robomme_env.utils import unmask_swap_xhard as ux
from robomme.robomme_env.utils.unmask_distractors import visible_in_camera, bin_corners
_exact = lambda x, y, r: visible_in_camera(bin_corners(float(x), float(y), 0.042426, 0.054))
ux.visible_on_camera = _exact  # 精确可见判据
import ring_sampler as rs
import m2b_fallback as fb
from replica import bus_layout, inner_sequence, vus_layout
from m2_outer_sim import BTN_AVOID

def ring_for(task, variant):
    if task == "VideoUnmaskSwap":
        a, b = (0.2539, 0.3403) if variant == "A" else (0.2789, 0.3653)
        return rs.Ring(f"vusA{variant}", (-a, a, -a, a), (-b, b, -b, b))
    x0, x1, y0, y1 = -0.2625, 0.17, -0.17, 0.27
    lo, hi = (0.0425, 0.1289) if variant == "A" else (0.0675, 0.1539)
    return rs.Ring(f"bus{variant}", (x0 - lo, x1 + lo, y0 - lo, y1 + lo), (x0 - hi, x1 + hi, y0 - hi, y1 + hi))

def run_episode(args):
    task, seed, count, crit, lane, variant = args
    lay = (vus_layout if task == "VideoUnmaskSwap" else bus_layout)(seed)
    if lay.get("spawn_fail"):
        return {"skip": True}
    ring = ring_for(task, variant)
    seq = inner_sequence(lay)
    sweeps = [(rs.state(f"bin_{a}", *pos[a], yaw[a]), rs.state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in seq]
    obstacles = [((b[0], b[1]), rs.RADIUS) for b in lay["bins"]] + [((bx, by), BTN_AVOID) for bx, by in lay["buttons"]]
    gen = ux.distractor_generator(seed)
    placements = rs.sample_ring(gen, ring=ring, count=count, obstacles=obstacles, sweeps=sweeps,
                                min_gap=0.003, max_trials=1024)
    if placements is None:
        return {"placement_fail": True}
    perm = torch.randperm(count, generator=gen).tolist()
    opos = [np.array(p[:2]) for p in placements]; oyaw = [p[2] for p in placements]
    tries, fails = [], collections.Counter()
    for k, (a, b, _d, ipos, iyaw) in enumerate(seq):
        chosen = None
        for j in range(count):
            o = perm[(k + j) % count]
            p = min((q for q in range(count) if q != o),
                    key=lambda q: (float(np.linalg.norm(np.asarray(opos[o], np.float32) - np.asarray(opos[q], np.float32))), q))
            r = fb.eval_window(k, a, b, ipos, iyaw, o, p, opos, oyaw, lane, lay["buttons"])
            ok = r["exact_ok"] and r["visible"] and r["btn_ok"] and (crit == "ev" or r["c_inner"] >= 0.04)
            if not ok:
                fails["exact" if not r["exact_ok"] else "vis" if not r["visible"] else "btn" if not r["btn_ok"] else "inner_clear"] += 1
            if ok:
                chosen = (o, p, j + 1); break
        if chosen is None:
            return {"feasible": False, "fails": dict(fails), "win": k}
        o, p, t = chosen; tries.append(t)
        opos[o], opos[p] = opos[p].copy(), opos[o].copy(); oyaw[o], oyaw[p] = oyaw[p], oyaw[o]
    return {"feasible": True, "tries": tries, "fails": dict(fails)}

if __name__ == "__main__":
    task, count, n, crit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    lane = float(sys.argv[5]) if len(sys.argv) > 5 else 0.07
    procs = int(sys.argv[6]) if len(sys.argv) > 6 else 8
    variant = sys.argv[7] if len(sys.argv) > 7 else "A"
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    t0 = time.time()
    with mp.get_context("fork").Pool(procs) as pool:
        res = [r for r in pool.imap_unordered(run_episode, [(task, base + i, count, crit, lane, variant) for i in range(n)], chunksize=2) if not r.get("skip")]
    eps = [r for r in res if "feasible" in r]; feas = [r for r in eps if r["feasible"]]
    tr = collections.Counter(t for r in feas for t in r["tries"]); fk = collections.Counter()
    for r in eps: fk.update(r["fails"])
    print("JOINT " + json.dumps({"task": task, "ring": variant, "count": count, "crit": crit, "lane": lane, "layouts": len(res),
          "placement_fail": sum(1 for r in res if r.get("placement_fail")), "episodes": len(eps),
          "ep_feasible_rate": round(len(feas) / len(eps), 4) if eps else None,
          "first_try_window_share": round(tr.get(1, 0) / max(1, sum(tr.values())), 3),
          "reject_reasons": dict(fk), "wall_s": round(time.time() - t0, 1)}, ensure_ascii=False), flush=True)
