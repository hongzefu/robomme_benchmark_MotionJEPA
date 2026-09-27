"""V6 均匀性候选方案（纯函数；可行性矩阵 M 为槽位对口径，槽位集合整局不变、占用者在槽位间置换）。

所有方案返回 (plan, fail_k)：plan = [(initiator_cube, partner_cube, slot_a, slot_b, dist)]；失败时 plan=None。
随机性用 numpy Generator（探针口径；实装时换成 torch generator 的一次 rand 数组即可）。
"""
import numpy as np
import vr6_lib as L


def _state(N):
    return list(range(N)), list(range(N))  # occ[slot]=cube, slot_of[cube]=slot


def _apply(occ, slot_of, sa, sb):
    a, b = occ[sa], occ[sb]
    occ[sa], occ[sb] = b, a
    slot_of[a], slot_of[b] = sb, sa
    return a, b


def s0_current(r, M, rng=None, nearest_k=3):
    N = len(r["cubes"])
    seq = L.initiator_seq_current(r["target"], r["perm"], N, r["n_swaps"])
    plan, k = L.plan_current(r["cubes"], M, seq, r["u"], nearest_k)
    if plan is None:
        return None, k
    return [(p["initiator"], p["partner"], p["slot_a"], p["slot_b"], p["dist_m"]) for p in plan], None


def s2_rot_anyfeasible(r, M, rng):
    """发起者仍 k%N 轮转；搭档在该发起者全部可行槽位里均匀选（去掉「3 个最近」）。"""
    N = len(r["cubes"]); P = np.array([c[:2] for c in r["cubes"]])
    seq = L.initiator_seq_current(r["target"], r["perm"], N, r["n_swaps"])
    occ, slot_of = _state(N); plan = []
    for k, a in enumerate(seq):
        sa = slot_of[a]; cands = [s for s in range(N) if s != sa and M[sa, s]]
        if not cands:
            return None, k
        sb = cands[int(rng.integers(len(cands)))]
        ia, ib = _apply(occ, slot_of, sa, sb)
        plan.append((ia, ib, sa, sb, float(np.linalg.norm(P[sa] - P[sb]))))
    return plan, None


def s1_pair_uniform(r, M, rng, no_repeat=True):
    """每次在全部可行（无序）槽位对里均匀抽一对；可选禁止与上一对相同（避免原地换回）。"""
    N = len(r["cubes"]); P = np.array([c[:2] for c in r["cubes"]])
    pairs = [(a, b) for a in range(N) for b in range(a + 1, N) if M[a, b]]
    occ, slot_of = _state(N); plan = []; last = None
    for k in range(r["n_swaps"]):
        cands = [p for p in pairs if not (no_repeat and p == last)]
        if not cands:
            return None, k
        sa, sb = cands[int(rng.integers(len(cands)))]
        if rng.random() < 0.5:
            sa, sb = sb, sa
        ia, ib = _apply(occ, slot_of, sa, sb)
        plan.append((ia, ib, sa, sb, float(np.linalg.norm(P[sa] - P[sb])))); last = (min(sa, sb), max(sa, sb))
    return plan, None


def s3_balanced(r, M, rng, no_repeat=True):
    """均衡贪心：每次在可行对里取「两块已参与次数之和最小」的那些对（平局再比较较大者），其中均匀抽一对。

    目标：每块参与次数 ∈ {floor(2n/N), ceil(2n/N)}；可行图有孤立槽位（该块永远换不动）时直接判失败。
    """
    N = len(r["cubes"]); P = np.array([c[:2] for c in r["cubes"]])
    if (M.sum(1) == 0).any():
        return None, -1
    pairs = [(a, b) for a in range(N) for b in range(a + 1, N) if M[a, b]]
    occ, slot_of = _state(N); plan = []; last = None; cnt = np.zeros(N, int)
    for k in range(r["n_swaps"]):
        cands = [p for p in pairs if not (no_repeat and p == last)]
        if not cands:
            return None, k
        score = [(cnt[occ[a]] + cnt[occ[b]], max(cnt[occ[a]], cnt[occ[b]])) for a, b in cands]
        best = min(score)
        pool = [p for p, s in zip(cands, score) if s == best]
        sa, sb = pool[int(rng.integers(len(pool)))]
        if rng.random() < 0.5:
            sa, sb = sb, sa
        ia, ib = _apply(occ, slot_of, sa, sb)
        cnt[ia] += 1; cnt[ib] += 1
        plan.append((ia, ib, sa, sb, float(np.linalg.norm(P[sa] - P[sb])))); last = (min(sa, sb), max(sa, sb))
    return plan, None


def s3n_balanced_near(r, M, rng, near_k=3, no_repeat=True):
    """S3 的短路径变体：候选对限制为「互为对方最近 near_k 个可行槽位之一」的对；该集合使某块无对可换时退回全部可行对。"""
    N = len(r["cubes"]); P = np.array([c[:2] for c in r["cubes"]])
    if (M.sum(1) == 0).any():
        return None, -1
    D = np.linalg.norm(P[:, None] - P[None], axis=-1)
    near = np.zeros_like(M)
    for s in range(N):
        order = [int(j) for j in np.argsort(D[s] + np.eye(N)[s] * 9, kind="stable") if j != s and M[s, j]]
        for j in order[:near_k]:
            near[s, j] = near[j, s] = True
    if (near.sum(1) == 0).any():
        near = M
    pairs = [(a, b) for a in range(N) for b in range(a + 1, N) if near[a, b]]
    occ, slot_of = _state(N); plan = []; last = None; cnt = np.zeros(N, int)
    for k in range(r["n_swaps"]):
        cands = [p for p in pairs if not (no_repeat and p == last)]
        if not cands:
            return None, k
        score = [(cnt[occ[a]] + cnt[occ[b]], max(cnt[occ[a]], cnt[occ[b]])) for a, b in cands]
        best = min(score)
        pool = [p for p, s in zip(cands, score) if s == best]
        sa, sb = pool[int(rng.integers(len(pool)))]
        if rng.random() < 0.5:
            sa, sb = sb, sa
        ia, ib = _apply(occ, slot_of, sa, sb)
        cnt[ia] += 1; cnt[ib] += 1
        plan.append((ia, ib, sa, sb, float(np.linalg.norm(P[sa] - P[sb])))); last = (min(sa, sb), max(sa, sb))
    return plan, None


def s4_reject(r, M, rng, base=s1_pair_uniform, budget=200, crit="balanced"):
    """整条序列拒绝采样：用 base 反复抽，直到满足判据（balanced: max-min≤1；all: 全员参与），最多 budget 次。

    返回 (plan, fail)，并在 r['_tries'] 留下尝试次数。
    """
    N = len(r["cubes"])
    if (M.sum(1) == 0).any():
        r["_tries"] = 0
        return None, -1
    for t in range(1, budget + 1):
        plan, k = base(r, M, rng)
        if plan is None:
            continue
        c = participation(plan, N)
        ok = (c.max() - c.min() <= 1) if crit == "balanced" else (c.min() >= 1)
        if ok:
            r["_tries"] = t
            return plan, None
    r["_tries"] = budget
    return None, -2


def participation(plan, N):
    c = np.zeros(N, int)
    for a, b, *_ in plan:
        c[a] += 1; c[b] += 1
    return c


SCHEMES = {
    "S0_现状(k%N+3近可行)": s0_current,
    "S2_k%N+任一可行": s2_rot_anyfeasible,
    "S1_可行对均匀": s1_pair_uniform,
    "S3_均衡贪心": s3_balanced,
    "S3n_均衡贪心(3近)": s3n_balanced_near,
    "S4_对均匀+整条拒绝(均衡)": s4_reject,
}


def s5_balanced_retry(r, M, rng, budget=20):
    """S3 均衡贪心 + 整条重试：平局随机，重试直到每块参与次数极差 ≤ 1（最多 budget 次；耗尽则取最后一条仍 ≤2 的结果）。"""
    N = len(r["cubes"])
    if (M.sum(1) == 0).any():
        r["_tries"] = 0
        return None, -1
    best = None
    for t in range(1, budget + 1):
        plan, k = s3_balanced(r, M, rng)
        if plan is None:
            return None, k
        c = participation(plan, N)
        if c.max() - c.min() <= 1:
            r["_tries"] = t
            return plan, None
        best = plan
    r["_tries"] = budget
    return best, None


SCHEMES["S5_均衡贪心+重试(≤1)"] = s5_balanced_retry
