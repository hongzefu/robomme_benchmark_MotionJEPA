# P4：VideoRepick 最终规则离线蒙特卡洛（纯 CPU 副本，不起 sapien 场景）
#   三列：V4（现状）／k2（规划期参考：目标每 3 次一轮 + 2 个最近可行 + 不重复上一对）／FINAL（用户最终规则）
#   FINAL：0.12 m 中心距（spawn_random_cube 拒绝循环内判据，每 trial 仍 3 个 rand）+ 已放方块精确 OBB
#          + seq=[目标]+randperm(5)、第 k 次发起者 seq[k%6] + 追加 u=torch.rand(n_swaps)
#          + reset 规划：名义槽位按距离排序，check_swap_sweep（方块半边 +5 mm）过滤，前 3 个可行里取 u[k]；
#            3 个最近都不可行则在任一可行里取；没有任何可行 → 候选级拒绝
#   变体 FINAL_A（敏感性）：只在「3 个最近」里取可行者，全不可行才退到任一可行
import sys, os, time, json, itertools, collections
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
from placements import _head, create_button_obb, BTN_OBB_HALF, XL, XH, YL, YH, HS, draw_selection, place
from robomme.robomme_env.utils.object_generation import _build_new_cube_obb2d, _obb2d_intersect
from v4rep import cube_obb2d_like_actor
from sim_lib import SweepCache, nn_order, run_episode
from perturb_check2 import InflCache

DMIN = 0.12


def exact_obb(x, y, yaw, hs=HS):
    c, s = np.cos(yaw), np.sin(yaw)
    return (np.array([x, y]), np.array([[c, -s], [s, c]]), np.array([hs, hs]))


def place_final(seed, obstacle="exact", max_trials=256, n=6):
    """与 spawn_random_cube 同随机流：每 trial 3 个 rand；先 OBB 判据、再中心距判据（均不抽随机数）。"""
    g, num_repeats, n_swaps, btn = _head(seed)
    obb = [create_button_obb(center_xy=btn, half_size=BTN_OBB_HALF)]
    placed, trials = [], 0
    for i in range(n):
        got = None
        for t in range(max_trials):
            trials += 1
            u1 = torch.rand(1, generator=g).item(); u2 = torch.rand(1, generator=g).item()
            x = float(XL + u1 * (XH - XL)); y = float(YL + u2 * (YH - YL))
            yaw = float(torch.rand(1, generator=g).item() * 2 * np.pi)
            cn, An, hn = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=HS)
            if any(_obb2d_intersect(c, A, h, cn, An, hn) for (c, A, h) in obb):
                continue
            if placed and min(np.hypot(x - p[0], y - p[1]) for p in placed) < DMIN:
                continue
            got = (x, y, yaw); break
        if got is None:
            return dict(ok=False, fail_at=i, trials=trials)
        placed.append(got)
        obb.append(exact_obb(*got) if obstacle == "exact" else cube_obb2d_like_actor(*got))
    return dict(ok=True, cubes=placed, n_swaps=n_swaps, num_repeats=num_repeats, button=btn, trials=trials, g=g)


def plan_final(cache, seq, u, variant="B"):
    P = cache.P; N = len(P); occ = list(range(N)); slot_of = list(range(N)); pairs = []; fallback = 0
    for k, a in enumerate(seq):
        sa = slot_of[a]; order, d = nn_order(P, sa)
        feas = [c for c in order if not cache.rejected(sa, c)]
        if not feas:
            return None, k, fallback
        near3_feas = [c for c in order[:3] if c in feas]
        if near3_feas:
            pool = feas[:3] if variant == "B" else near3_feas
        else:
            pool = feas; fallback += 1
        sb = pool[int(u[k] * len(pool))]
        b = occ[sb]
        pairs.append((a, b, sa, sb, float(d[sb])))
        occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa
    return pairs, None, fallback


def ep_metrics(pairs, target, P, true_cache):
    mult = collections.Counter((min(sa, sb), max(sa, sb)) for _, _, sa, sb, _ in pairs)
    parts = set(); tm = 0
    for a, b, *_ in pairs:
        parts.update((a, b)); tm += (target in (a, b))
    L = [p[4] for p in pairs]
    return dict(all6=len(parts) == 6, tmoves=tm, maxmult=max(mult.values()), distinct=len(mult),
                meanL=float(np.mean(L)), maxL=float(np.max(L)),
                d5_nominal=sum(true_cache.rejected(sa, sb) for _, _, sa, sb, _ in pairs))


def uni(P):
    cx = np.clip(((P[:, 0] - XL) / (XH - XL) * 2).astype(int), 0, 1); cy = np.clip(((P[:, 1] - YL) / (YH - YL) * 3).astype(int), 0, 2)
    D = np.linalg.norm(P[:, None] - P[None], axis=-1) + np.eye(len(P)) * 9
    return dict(cell3=int(np.bincount(cx * 3 + cy, minlength=6).max()) >= 3, min_pair=float(D.min()))


def perturb_rej(cubes, target, pairs, seed, rad):
    prng = np.random.default_rng(seed + 99)
    ang = prng.uniform(0, 2 * np.pi); rr = rad * np.sqrt(prng.uniform()); dy = np.radians(prng.uniform(-0.5, 0.5))
    cs = [list(c) for c in cubes]; cs[target][0] += rr * np.cos(ang); cs[target][1] += rr * np.sin(ang); cs[target][2] += dy
    pc = SweepCache([tuple(c) for c in cs])
    return any(pc.rejected(sa, sb) for _, _, sa, sb, _ in pairs)


def work(seed):
    out = {"seed": seed}
    # ── V4 列 ──
    r = place(seed, "v4")
    if r["ok"]:
        target, init3, _ = draw_selection(r["g"]); n = r["n_swaps"]; P = np.array([c[:2] for c in r["cubes"]])
        tc = SweepCache(r["cubes"])
        e = run_episode(r["cubes"], target, n, [init3[k % 3] for k in range(n)], "nn", np.random.default_rng(0), cache=tc)
        # 复算 maxmult / 目标被换次数（run_episode 无这两项）
        occ = list(range(6)); slot_of = list(range(6)); mult = collections.Counter(); tm = 0
        for k in range(n):
            a = init3[k % 3]; sa = slot_of[a]; sb = nn_order(P, sa)[0][0]; b = occ[sb]
            mult[(min(sa, sb), max(sa, sb))] += 1; tm += (target in (a, b))
            occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa
        out["v4"] = dict(placed=True, plan=True, all6=e["participants"] == 6, tmoves=tm, maxmult=max(mult.values()),
                         distinct=e["distinct_pairs"], meanL=e["mean_len"], maxL=e["max_len"], d5_nominal=e["n_rej"],
                         ep_rej=e["any_rej"], **uni(P))
    else:
        out["v4"] = dict(placed=False)
    # ── FINAL（及变体 A）──
    rf = place_final(seed, "exact")
    rd = place_final(seed, "actor")  # 退化 OBB 对照：0.12 m 下应逐位相同
    out["exact_eq_actor"] = rf["ok"] == rd["ok"] and (not rf["ok"] or (rf["cubes"] == rd["cubes"] and rf["trials"] == rd["trials"]))
    if not rf["ok"]:
        out["final"] = out["final_A"] = dict(placed=False); return out
    g = rf["g"]; n = rf["n_swaps"]
    target, _, init_all = draw_selection(g)
    u = torch.rand(n, generator=g).tolist()          # 追加取值点 objects.swap_partner_u
    seq = [init_all[k % 6] for k in range(n)]
    P = np.array([c[:2] for c in rf["cubes"]])
    pc = InflCache(rf["cubes"], HS + 0.005); tc = SweepCache(rf["cubes"])
    for key, var in (("final", "B"), ("final_A", "A")):
        pairs, fail_k, fb = plan_final(pc, seq, u, var)
        if pairs is None:
            out[key] = dict(placed=True, plan=False, fail_k=fail_k, trials=rf["trials"], **uni(P)); continue
        m = ep_metrics(pairs, target, P, tc)
        m.update(placed=True, plan=True, fallback=fb, trials=rf["trials"], init6=len(set(seq)) == 6,
                 pert12=perturb_rej(rf["cubes"], target, pairs, seed, 0.012), pert20=perturb_rej(rf["cubes"], target, pairs, seed, 0.020), **uni(P))
        if key == "final":
            m["pairs"] = [(a, b) for a, b, *_ in pairs]; m["target"] = target; m["n"] = n
        out[key] = m
    # ── k2 参考列（规划期旧设计：目标每 3 次一轮 + 2 个最近可行 + 不重复上一对，余量 5 mm）──
    from final_design_sim import run
    from final_design_sim2 import seq_interleave
    r2 = place(seed, "hc0.12"); t2, _, ia2 = draw_selection(r2["g"])
    res = run(InflCache(r2["cubes"], 0.025), None, t2, r2["n_swaps"], seq_interleave(ia2, r2["n_swaps"]), np.random.default_rng(seed), k=2)
    out["k2"] = dict(placed=True, plan=res is not None, **({} if res is None else dict(all6=res["parts"] == 6, tmoves=res["tmoves"],
                     maxmult=res["maxmult"], distinct=res["distinct"], meanL=res["meanL"], maxL=res["maxL"])), **uni(np.array([c[:2] for c in r2["cubes"]])))
    return out


if __name__ == "__main__":
    M = int(sys.argv[1])
    seeds = [7_000_000 + i for i in range(M)]
    t0 = time.time(); R = []
    with Pool(24) as pool:
        for k, o in enumerate(pool.imap_unordered(work, seeds, chunksize=4)):
            R.append(o)
            if (k + 1) % 300 == 0:
                print(f"progress {k+1}/{M} t={time.time()-t0:.0f}s", flush=True)
    R.sort(key=lambda o: o["seed"])
    json.dump(R, open(os.path.join(os.path.dirname(__file__), f"final_rule_sim_{M}.json"), "w"))
    print("全部完成", f"t={time.time()-t0:.0f}s", flush=True)
