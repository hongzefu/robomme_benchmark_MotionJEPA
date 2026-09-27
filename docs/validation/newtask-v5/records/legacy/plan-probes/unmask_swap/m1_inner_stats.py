"""M1：内部交换机制的统计与「内部扫掠 vs 内部旁观容器 / 干扰容器」碰撞率（纯几何，复刻已核对 20/20 逐值一致）。

用法：m1_inner_stats.py [N_SYNTH] [procs]
* 20 行 specs + V6/rollout 的 8 个运行期碰撞失败 seed：名义位姿预演，看能否复现运行期 BinCollisionError；
* 合成布局 N_SYNTH 个/环境（seed = 9_100_000 + i（VUS）/ 9_300_000 + i（BUS））：
  搭档距离、配对结构（用到的无序对两两不相交 ⇒ 固定配对）、立即撤销率、藏物方块到过的位置数、
  内部扫掠碰撞率（旁观 = 其余内部容器 + 仓库口径采样的 3 个干扰容器）。
判据：与仓库 check_swap_sweep 相同的对象对集合与 _prove_pair 证明；先用外接圆严格判据跳过已证明分离的对
（只跳过必然通过的对，判定不变），只为提速。
"""
import collections
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from replica import (bin_state, bus_layout, inner_sequence, layout_from_spec, load_spec_rows,  # noqa: E402
                     vus_layout)
from ring_sampler import RADIUS, V4_RING, _sweep_paths, sample_ring, state  # noqa: E402
from multi_sweep import movers_for_pair  # noqa: E402

from robomme.robomme_env.utils import bin_collision as bc  # noqa: E402
from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402

BTN = float(np.linalg.norm([0.05625, 0.05625]))
S = np.linspace(0, 1, 401)


def exact_sweep(sa, sb, bystanders, k):
    """与 check_swap_sweep 同对象对、同证明；外接圆严格分离的对跳过。"""
    pa, pb, v = _sweep_paths(sa, sb)
    ma, mb = movers_for_pair(sa, sb)
    checks = []
    dmm = float(np.min(np.linalg.norm(pa - pb, axis=1)))
    if not dmm - 2 * RADIUS > (2 * v) * (S[1] - S[0]) / 2:
        checks.append((ma, mb))
    for st in bystanders:
        xy = st.p[:2]
        for m, pth in ((ma, pa), (mb, pb)):
            d = float(np.min(np.linalg.norm(pth - xy, axis=1)))
            if not d - 2 * RADIUS > v * (S[1] - S[0]) / 2:
                checks.append((m, bc._Static(name=st.name, shapes=st.shapes, radii=st.radii, p=st.p.copy(), q=st.q.copy())))
    for left, right in checks:
        for ia in range(len(left.shapes)):
            for ib in range(len(right.shapes)):
                gap, rej = bc._prove_pair(left, right, ia, ib, stage="sweep", sweep_index=k)
                if rej is not None:
                    return rej
    return None


def sweep_eval(layout, distractors):
    first_fail = None
    for k, (a, b, _d, pos, yaw) in enumerate(inner_sequence(layout)):
        sa = bin_state(f"bin_{a}", *pos[a], yaw[a])
        sb = bin_state(f"bin_{b}", *pos[b], yaw[b])
        by = [bin_state(f"bin_{j}", *pos[j], yaw[j]) for j in range(len(pos)) if j not in (a, b)]
        by += [bin_state(f"distractor_bin_{j}", x, y, w) for j, (x, y, w) in enumerate(distractors)]
        rej = exact_sweep(sa, sb, by, k)
        if rej is not None:
            return (k, rej.reason, rej.object_a, rej.object_b, round(rej.s, 4) if rej.s is not None else None)
    return first_fail


def distractors_fast(lay):
    sweeps = [(state(f"bin_{a}", *pos[a], yaw[a]), state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in inner_sequence(lay)]
    obstacles = [((b[0], b[1]), RADIUS) for b in lay["bins"]] + [((bx, by), BTN) for bx, by in lay["buttons"]]
    return sample_ring(ux.distractor_generator(lay["seed"]), ring=V4_RING, count=3, obstacles=obstacles, sweeps=sweeps)


def one(args):
    task, seed = args
    lay = (vus_layout if task == "VideoUnmaskSwap" else bus_layout)(seed)
    if len(lay["bins"]) < 4:
        return None
    seq = inner_sequence(lay)
    t0 = time.perf_counter()
    dis = distractors_fast(lay)
    t_dis = time.perf_counter() - t0
    t0 = time.perf_counter()
    fail = sweep_eval(lay, dis)
    t_sw = time.perf_counter() - t0
    return dict(task=task, seed=seed, n_swaps=lay["n_swaps"], selected=lay["selected"],
                pairs=[(a, b) for a, b, *_ in seq], dists=[d for _a, _b, d, *_ in seq], fail=fail,
                t_dis=t_dis, t_sw=t_sw, bins=lay["bins"])


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    procs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    print("== 运行期碰撞失败 seed 的名义预演 ==", flush=True)
    known = [("VideoUnmaskSwap", 4500300, None, "rollout: sweep#1 bin_2 vs bin_1 s=0.5625"),
             ("VideoUnmaskSwap", 7500004, 8, "V6: sweep#2 bin_3 vs bin_2 s=0.625"),
             ("ButtonUnmaskSwap", 7700001, 6, "V6: sweep#0 bin_3 vs bin_0 s=0.297"),
             ("ButtonUnmaskSwap", 7700100, 6, "V6: sweep#0 bin_0 vs bin_1 s=0.625"),
             ("ButtonUnmaskSwap", 7700102, 6, "V6: sweep#1 bin_0 vs bin_2 s=0.5"),
             ("ButtonUnmaskSwap", 7700201, 7, "V6: sweep#0 bin_3 vs bin_1 s=0.375"),
             ("ButtonUnmaskSwap", 7700401, 8, "V6: sweep#0 bin_2 vs bin_3 s=0.4375"),
             ("ButtonUnmaskSwap", 7700504, 8, "V6: sweep#0 bin_2 vs bin_0 s=0.5")]
    for task, seed, pin, runtime in known:
        lay = (vus_layout if task == "VideoUnmaskSwap" else bus_layout)(seed)
        if pin is not None:
            lay["n_swaps"] = pin
        dis = distractors_fast(lay)
        fail = sweep_eval(lay, dis)
        print(f"{task} seed={seed} [{runtime}] predicted_first_fail={fail} pairs={[(a, b) for a, b, *_ in inner_sequence(lay)]}", flush=True)
    spec_fail = []
    for row in load_spec_rows():
        if row["task"] not in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
            continue
        lay = layout_from_spec(row)
        fail = sweep_eval(lay, lay["distractors"])
        if fail:
            spec_fail.append((row["task"], row["episode"], row["seed"], fail))
    print(f"SPEC_ROWS_PREDICTED_INNER_COLLISION={len(spec_fail)}/20 {spec_fail}", flush=True)

    jobs = [("VideoUnmaskSwap", 9_100_000 + i) for i in range(N)] + [("ButtonUnmaskSwap", 9_300_000 + i) for i in range(N)]
    with mp.get_context("fork").Pool(procs) as pool:
        res = [r for r in pool.imap_unordered(one, jobs, chunksize=2) if r is not None]
    for task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        rs = [r for r in res if r["task"] == task]
        d = np.array([x for r in rs for x in r["dists"]])
        nsw = collections.Counter(r["n_swaps"] for r in rs)
        distinct = collections.Counter(len({tuple(sorted(p)) for p in r["pairs"]}) for r in rs)
        fixed = sum(1 for r in rs if (lambda used: len([x for p in used for x in p]) == len({x for p in used for x in p}))({tuple(sorted(p)) for p in r["pairs"]}))
        undo = sum(1 for r in rs for k in range(1, len(r["pairs"])) if sorted(r["pairs"][k]) == sorted(r["pairs"][k - 1]))
        tot = sum(len(r["pairs"]) for r in rs)
        visited = collections.Counter()
        never_init = collections.Counter()
        for r in rs:
            where = list(range(4))
            slots = {j: {j} for j in range(4)}
            for a, b in r["pairs"]:
                where[a], where[b] = where[b], where[a]
                slots[a].add(where[a]); slots[b].add(where[b])
            for j in r["selected"]:
                visited[len(slots[j])] += 1
        fails = [r for r in rs if r["fail"]]
        kinds = collections.Counter("distractor" if "distractor" in r["fail"][3] else ("mover_pair" if r["fail"][3] in {f"bin_{x}" for x in r["pairs"][r["fail"][0]]} and r["fail"][2] in {f"bin_{x}" for x in r["pairs"][r["fail"][0]]} else "inner_bystander") for r in fails)
        first_idx = collections.Counter(r["fail"][0] for r in fails)
        print(f"\n{task}: layouts={len(rs)} n_swaps={dict(sorted(nsw.items()))}")
        print(f"  partner_dist_m min={d.min():.4f} p5={np.percentile(d, 5):.4f} median={np.median(d):.4f} p95={np.percentile(d, 95):.4f} max={d.max():.4f}")
        print(f"  distinct_unordered_pairs_per_episode={dict(sorted(distinct.items()))}")
        print(f"  used_pairs_pairwise_disjoint(fixed matching)={fixed}/{len(rs)}={fixed/len(rs):.3f}  immediate_undo={undo}/{tot}={undo/tot:.3f}")
        print(f"  hidden_cube_distinct_slots_visited={dict(sorted(visited.items()))} (3 cubes x episodes)")
        print(f"  INNER_SWEEP_COLLISION episodes={len(fails)}/{len(rs)}={len(fails)/len(rs):.3f} kinds={dict(kinds)} first_fail_window={dict(sorted(first_idx.items()))}")
        print(f"  wall: sample_distractors(fast)={np.mean([r['t_dis'] for r in rs]):.2f}s/ep  inner sweep eval(fast)={np.mean([r['t_sw'] for r in rs]):.2f}s/ep", flush=True)
