"""V6 探针 P2：内环（4 个容器）交换对象选择的均匀性蒙特卡洛。

关键事实（代码核实）：交换在窗口末精确对换两者位姿（p 与 q），因此一局里 4 个容器的「位姿槽」集合不变，
某次交换可行与否只取决于两者当前占的槽对（其余槽静止）⇒ 每局只需对 C(4,2)=6 个槽对各做一次仓库精确判定
（check_swap_sweep_prefiltered，与运行时 check_swap_sweep 判定逐位相同），得到「可行槽对图」G，之后任意算法零成本模拟。

算法：
  S0 现状 V5：发起者 swap_indices[k%3] 轮转（replica 复刻主流取值），搭档 = XY 最近邻；不可行即整局拒（L20）。
  S1 可行对均匀：每窗在当前全部可行的对象对里均匀抽一对。
  S2 先发起者后搭档：在「至少有一个可行搭档」的对象里均匀抽发起者，再在其可行搭档里均匀抽。
  S3 匹配牌堆（局内均衡）：牌堆 = 随机完美匹配的 2 对（随机次序），发完再洗新匹配；每窗取牌堆中第一张当前可行的牌，
     全不可行则退回 S1 并计一次「失衡事件」。
  S4 先定序列再重抽布局：序列按 S3 的牌堆规则（不看几何）预先定死，布局最多重抽 64 次直到整段可行；
     统计接受率与被 64 次上限挤掉的序列（它们造成的边际偏差）。
  S1n/S2n：S1/S2 附加「不许立即撤销上一对」。
用法：p2_inner_mc.py <task> <N> [procs]
"""
import collections, json, math, multiprocessing as mp, sys, time
import numpy as np
import torch
sys.path.insert(0, ".")
from mclib import *  # noqa

N_OBJ = 4
PAIRS = [(a, b) for a in range(N_OBJ) for b in range(a + 1, N_OBJ)]


def slot_graph(lay):
    S = inner_states(lay["bins"])
    return {p: inner_pair_ok(S, *p) for p in PAIRS}, S


def nn_slot(S, a):
    return nearest(S, a)


def run_seq(rule, G, S, n, rng, init_seq=None):
    """返回对象对序列（None 表示本布局下该规则走不通）。occ[obj]=slot。"""
    occ = list(range(N_OBJ)); where = list(range(N_OBJ))  # where[slot]=obj
    seq = []; deck = []; imb = 0; last = None
    for k in range(n):
        def feas(o1, o2):
            s1, s2 = occ[o1], occ[o2]
            return G[(min(s1, s2), max(s1, s2))]
        allf = [(a, b) for a, b in PAIRS if feas(a, b)]
        if rule in ("S1n", "S2n") and last is not None:
            allf = [p for p in allf if p != last] or None
            if allf is None:
                return None, imb
        if rule == "S0":
            a = init_seq[k]
            # 最近邻按当前槽位置：a 所在槽的 XY 最近槽上的对象
            sa = occ[a]
            pos = [np.asarray(S[s].p[:2], dtype=np.float32) for s in range(N_OBJ)]
            best, bd = None, float("inf")
            for s in range(N_OBJ):
                if s == sa: continue
                d = np.linalg.norm(pos[sa] - pos[s])
                if d < bd: best, bd = s, d
            b = where[best]
            pair = (min(a, b), max(a, b))
            if not feas(*pair):
                return None, imb
        elif rule in ("S1", "S1n"):
            if not allf: return None, imb
            pair = allf[rng.integers(len(allf))]
        elif rule in ("S2", "S2n"):
            if not allf: return None, imb
            inits = sorted({o for p in allf for o in p})
            a = inits[rng.integers(len(inits))]
            partners = [p for p in allf if a in p]
            pair = partners[rng.integers(len(partners))]
        elif rule in ("S3", "S4"):
            if not deck:
                perm = rng.permutation(N_OBJ)
                m = [tuple(sorted((perm[0], perm[1]))), tuple(sorted((perm[2], perm[3])))]
                deck = [m[i] for i in rng.permutation(2)]
            pick = None
            for i, p in enumerate(deck):
                if feas(*p):
                    pick = i; break
            if pick is None:
                if rule == "S4": return None, imb
                if not allf: return None, imb
                pair = allf[rng.integers(len(allf))]; imb += 1
            else:
                pair = deck.pop(pick)
        a, b = pair
        seq.append(pair)
        sa, sb = occ[a], occ[b]
        occ[a], occ[b] = sb, sa
        where[sa], where[sb] = b, a
        last = pair
    return seq, imb


def one(args):
    task, seed = args
    lay = inner_layout(task, seed)
    if lay.get("spawn_fail"):
        return None
    G, S = slot_graph(lay)
    n = lay["n_swaps"]
    rng = np.random.default_rng(seed)
    out = {"seed": seed, "n": n, "G": [int(G[p]) for p in PAIRS],
           "dist": [float(np.linalg.norm(S[a].p[:2] - S[b].p[:2])) for a, b in PAIRS],
           "nn": [PAIRS.index(tuple(sorted((a, nn_slot(S, a))))) for a in range(N_OBJ)]}
    out["S0"] = run_seq("S0", G, S, n, rng, initiators(lay))[0]
    for r in ("S1", "S1n", "S2", "S2n", "S3"):
        seq, imb = run_seq(r, G, S, n, rng)
        out[r] = seq; out[r + "_imb"] = imb
    # S4：序列先定（不看几何：G 全真），再在「同一内环采样分布」下重抽布局（用 seed 派生的后续 seed）
    full = {p: True for p in PAIRS}
    seq4, _ = run_seq("S3", full, S, n, rng)
    tries = 0; ok = False
    if (seed % 10) != 0:  # S4 只在 1/10 子样本上跑（每局最多 16 次重抽，开销大）
        out["S4"] = None; out["S4_seq"] = None; out["S4_tries"] = None
        return out
    for t in range(16):
        tries += 1
        lay2 = lay if t == 0 else inner_layout(task, 50_000_000 + seed * 64 + t)
        if lay2.get("spawn_fail"): continue
        G2, S2 = slot_graph(lay2) if t else (G, S)
        # 回放固定序列
        occ = list(range(N_OBJ)); good = True
        for a, b in seq4:
            sa, sb = occ[a], occ[b]
            if not G2[(min(sa, sb), max(sa, sb))]:
                good = False; break
            occ[a], occ[b] = sb, sa
        if good:
            ok = True; break
    out["S4"] = seq4 if ok else None
    out["S4_seq"] = seq4
    out["S4_tries"] = tries
    return out


if __name__ == "__main__":
    task = sys.argv[1]; N = int(sys.argv[2]); procs = int(sys.argv[3]) if len(sys.argv) > 3 else 28
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    t0 = time.time()
    with mp.Pool(procs) as pool:
        res = [r for r in pool.imap(one, [(task, base + i) for i in range(N)], chunksize=20) if r is not None]
    json.dump(res, open(f"p2_inner_{task}.json", "w"), default=int)
    print(f"P2_DONE task={task} N={len(res)} wall={time.time()-t0:.1f}s")
