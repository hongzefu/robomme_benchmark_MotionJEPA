"""V6 探针 P3：外环干扰容器交换对象选择的均匀性蒙特卡洛（复用仓库 V5 纯函数）。

每局：replica 复刻内环布局与 V5 内环序列（swap_indices[k%3] + 最近邻）→ 仓库 prejudge_inner_windows（L20）→
仓库 sample_distractor_layout（V5 预设 count 个、V4 环带、InnerSweepGuard 作 extra_reject、独立流 distractor_generator）→
对每个内环窗口，把全部 C(count,2) 个外环「槽对」各跑一次仓库 evaluate_outer_candidate（可见/按钮/内环净距/两对联合精确证明，
干扰碰撞盒外扩 plan_pad_m 5 mm，与 V5 规划逐项同口径）⇒ 每窗可行槽对图 G_k；之后各算法零成本模拟：
  O0 现状 V5：perm=randperm(count)，第 k 窗从 perm[k%count] 起顺延，搭档=最近邻，第一个可行者。
  O1 可行对均匀：每窗在全部可行对象对里均匀抽。
  O2 先发起者后搭档：在有可行搭档的对象里均匀抽发起者，再在其可行搭档里均匀抽。
  O3 匹配牌堆：随机完美匹配的 count/2 对随机排序作牌堆，每窗取第一张可行牌，全不可行退回 O1 记失衡。
  O4 计数均衡贪心：可行对里取「两者已参与次数的 max、再 sum」最小者（不许立即撤销，除非别无选择），并列均匀。
  O1k3：O1 但只在「发起者的前 3 近邻」构成的可行对里均匀抽（折中：保短路径）。
另记：按「搭档距离名次」（1=最近邻）的可行率，回答「不限最近邻时可行率怎样」。
用法：p3_outer_mc.py <task> <N> [count] [procs]
"""
import json, multiprocessing as mp, sys, time
import numpy as np
sys.path.insert(0, ".")
from mclib import *  # noqa
from replica import initiators as v5_initiators  # noqa

RULE_NAMES = ("O0", "O1", "O2", "O3", "O1k3", "O4")


def v5_inner_windows(lay):
    S = inner_states(lay["bins"])
    pos = [np.array([x, y, 0.0], dtype=np.float32) for x, y, _ in lay["bins"]]
    return ux.predict_inner_windows_from_states(S, pos, v5_initiators(lay), [0, 1])


def one(args):
    task, seed, count = args
    t0 = time.perf_counter()
    lay = inner_layout(task, seed)
    if lay.get("spawn_fail"):
        return {"seed": seed, "status": "inner_spawn_fail"}
    wins = v5_inner_windows(lay)
    if ux.prejudge_inner_windows(wins) is not None:
        return {"seed": seed, "status": "inner_prejudge_reject"}
    dcfg = dict(ux.v5_distractor_cfg(task)); dcfg["count"] = count
    lo = count // 2; dcfg["cube_count_range"] = [lo, lo]
    scfg = ux.parse_distractor_swap_cfg(ux.v5_distractor_swap_cfg(task))
    guard = ux.InnerSweepGuard(wins)
    pad = ux.padded_bin_shapes(CH, scfg.plan_pad_m)
    gen = ux.distractor_generator(seed)
    try:
        layout = sample_distractor_layout(dcfg, obstacles=obstacles(lay), generator=gen, cube_half_size=CH,
                                          extra_reject=lambda i, x, y, yaw, _p: guard.first_rejection(
                                              ux.distractor_bin_state(i, x, y, yaw, CH, pad)) is not None)
    except DistractorPlacementError:
        return {"seed": seed, "status": "placement_fail"}
    outer0 = [ux.distractor_bin_state(i, x, y, yaw, CH, pad) for i, (x, y, yaw) in enumerate(layout.bins)]
    n = len(wins)
    pairs = [(a, b) for a in range(count) for b in range(a + 1, count)]
    xy = np.array([s.p[:2] for s in outer0])
    D = np.linalg.norm(xy[:, None] - xy[None], axis=-1)
    rank = np.argsort(np.argsort(D + np.eye(count) * 9, axis=1), axis=1) + 1  # rank[i,j]: j 在 i 的距离名次
    G = []  # G[k][pair] 以「槽」为单位
    cache = {}
    for k, w in enumerate(wins):
        key = (tuple(np.round(w.states[w.a].p[:2], 6)), tuple(np.round(w.states[w.b].p[:2], 6)))
        key = tuple(sorted(key))
        if key not in cache:
            g = {}
            for (a, b) in pairs:
                ok, _r, _ = ux.evaluate_outer_candidate(k, w, a, b, outer0, cfg=scfg, cube_half_size=CH,
                                                        buttons_xy=[np.asarray(bb) for bb in lay["buttons"]])
                g[(a, b)] = bool(ok)
            cache[key] = g
        G.append(cache[key])
    rng = np.random.default_rng(seed)
    perm = rng.permutation(count).tolist()
    out = {"seed": seed, "status": "ok", "n": n, "count": count,
           "rank_feas": [[int(rank[a, b]), int(rank[b, a]), int(G[k][(a, b)])] for k in range(len(cache) and 1) for (a, b) in pairs],
           "G_density": float(np.mean([np.mean(list(g.values())) for g in cache.values()])),
           "slot_deg": [float(np.mean([sum(g[p] for p in pairs if i in p) for g in cache.values()])) for i in range(count)],
           "slot_xy": xy.round(4).tolist()}
    for rule in RULE_NAMES:
        occ = list(range(count)); where = list(range(count)); seq = []; deck = []; imb = 0; fail = None; plen = []
        cnt = [0] * count; last = None
        for k in range(n):
            def feas(o1, o2):
                s1, s2 = occ[o1], occ[o2]
                return G[k][(min(s1, s2), max(s1, s2))]
            allf = [(a, b) for a, b in pairs if feas(a, b)]
            pair = None
            if rule == "O0":
                for j in range(count):
                    o = perm[(k + j) % count]
                    so = occ[o]
                    d = D[so].copy(); d[so] = 9
                    sp = int(np.argmin(d)); p = where[sp]
                    if feas(o, p):
                        pair = (min(o, p), max(o, p)); break
            elif rule == "O1":
                if allf: pair = allf[rng.integers(len(allf))]
            elif rule == "O1k3":
                near = [(a, b) for a, b in allf if rank[occ[a], occ[b]] <= 3 or rank[occ[b], occ[a]] <= 3]
                if near: pair = near[rng.integers(len(near))]
            elif rule == "O2":
                if allf:
                    inits = sorted({o for p_ in allf for o in p_})
                    a = inits[rng.integers(len(inits))]
                    cands = [p_ for p_ in allf if a in p_]
                    pair = cands[rng.integers(len(cands))]
            elif rule == "O3":
                if not deck:
                    pm = rng.permutation(count)
                    m = [tuple(sorted((int(pm[2 * i]), int(pm[2 * i + 1])))) for i in range(count // 2)]
                    deck = [m[i] for i in rng.permutation(len(m))]
                for i, p_ in enumerate(deck):
                    if feas(*p_):
                        pair = deck.pop(i); break
                if pair is None and allf:
                    pair = allf[rng.integers(len(allf))]; imb += 1
            elif rule == "O4":
                cands = [p_ for p_ in allf if p_ != last] or allf
                if cands:
                    key = [(max(cnt[a_], cnt[b_]), cnt[a_] + cnt[b_]) for a_, b_ in cands]
                    best = min(key)
                    cands = [p_ for p_, kk in zip(cands, key) if kk == best]
                    pair = cands[rng.integers(len(cands))]
            if pair is None:
                fail = k; break
            a, b = pair
            cnt[a] += 1; cnt[b] += 1; last = pair
            plen.append(float(D[occ[a], occ[b]]))
            seq.append([int(a), int(b)])
            sa, sb = occ[a], occ[b]
            occ[a], occ[b] = sb, sa; where[sa], where[sb] = b, a
        out[rule] = None if fail is not None else seq
        out[rule + "_fail"] = fail
        out[rule + "_imb"] = imb
        out[rule + "_plen"] = float(np.mean(plen)) if plen else None
    out["wall"] = time.perf_counter() - t0
    return out


if __name__ == "__main__":
    task = sys.argv[1]; N = int(sys.argv[2])
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    procs = int(sys.argv[4]) if len(sys.argv) > 4 else 28
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    t0 = time.time()
    with mp.Pool(procs) as pool:
        res = list(pool.imap_unordered(one, [(task, base + i, count) for i in range(N)], chunksize=4))
    json.dump(res, open(f"p3_outer_{task}_c{count}.json", "w"), default=int)
    print(f"P3_DONE task={task} count={count} N={len(res)} wall={time.time()-t0:.1f}s")
