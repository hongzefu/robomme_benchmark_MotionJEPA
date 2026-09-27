"""交换顺序模拟 + D5 真实扫掠判据（bin_collision.check_swap_sweep / check_bin_layout）。

关键事实（源码）：swap_flat_two_lane 结束时 cube_a←(B 的 xy, B 的 q)、cube_b←(A 的 xy, A 的 q)，
所以「槽位」（xy+朝向）集合在整局交换中不变，只有占用者在槽位间置换；
两块的弯道路径只取决于无序槽位对 {i,j}（谁当发起者路径相同），因此扫掠结果按槽位对缓存。
"""
import numpy as np
from robomme.robomme_env.utils.bin_collision import (
    ObjectState, cube_shape_specs, cube_actor_pose, check_swap_sweep, check_bin_layout,
)

HS = 0.02
SHAPES = cube_shape_specs(HS)


def slot_states(cubes):
    out = []
    for i, (x, y, yaw) in enumerate(cubes):
        p, q = cube_actor_pose((x, y), yaw, HS)
        out.append(ObjectState(name=f"slot_{i}", p=p, q=q, shapes=SHAPES))
    return out


class SweepCache:
    def __init__(self, cubes):
        self.states = slot_states(cubes)
        self.P = np.array([[c[0], c[1]] for c in cubes])
        self.cache = {}

    def rejected(self, sa, sb):
        key = (min(sa, sb), max(sa, sb))
        if key not in self.cache:
            a, b = self.states[key[0]], self.states[key[1]]
            by = [s for k, s in enumerate(self.states) if k not in key]
            gap, rej = check_swap_sweep(a, b, by, sweep_index=0)
            self.cache[key] = (rej is not None, None if rej is None else rej.reason, gap)
        return self.cache[key][0]

    def initial_ok(self):
        gap, rej = check_bin_layout(self.states, stage="initial")
        return rej is None, gap


def nn_order(P, s):
    d = np.linalg.norm(P - P[s], axis=1)
    d[s] = np.inf
    # 稳定排序：等距时按槽位序（≈生成顺序；运行时按方块序号遍历、严格小于 → 首个胜出）
    return list(np.argsort(d, kind="stable")[: len(P) - 1]), d


def run_episode(cubes, target, n_swaps, initiator_seq, partner_rule, rng, cache=None):
    """initiator_seq: 长度 n_swaps 的「发起方块」序列（方块序号），或 'iid'/'randpair'。
    partner_rule: 'nn' | ('knn', k) | 'rand' | 'nn_feasible' """
    N = len(cubes)
    cache = cache or SweepCache(cubes)
    P = cache.P
    occ = list(range(N))          # occ[slot] = cube
    slot_of = list(range(N))      # slot_of[cube] = slot
    parts, inits, rej_idx = set(), set(), None
    n_rej = 0
    undo = 0
    prev = None
    tslots = [slot_of[target]]
    lengths = []
    infeasible = 0
    used_pairs = set(); repeats = 0
    for k in range(n_swaps):
        if initiator_seq == "iid":
            a = int(rng.integers(N))
        elif initiator_seq == "randpair":
            a, b2 = rng.choice(N, 2, replace=False)
            a = int(a)
        else:
            a = initiator_seq[k]
        sa = slot_of[a]
        order, d = nn_order(P, sa)
        if initiator_seq == "randpair":
            sb = slot_of[int(b2)]
        elif partner_rule == "nn":
            sb = order[0]
        elif isinstance(partner_rule, tuple) and partner_rule[0] == "knn":
            kk = partner_rule[1]
            sb = order[int(rng.random() * kk)]
        elif partner_rule == "rand":
            sb = order[int(rng.random() * (N - 1))]
        elif isinstance(partner_rule, tuple) and partner_rule[0] == "knn_feasible":
            kk = partner_rule[1]
            feas = [c for c in order if not cache.rejected(sa, c)]
            if feas:
                pool = feas[:kk] if kk > 0 else feas
                sb = pool[int(rng.random() * len(pool))]
            else:
                infeasible += 1
                sb = order[0]
        elif partner_rule == "nn_feasible":
            sb = None
            for cand in order:
                if not cache.rejected(sa, cand):
                    sb = cand
                    break
            if sb is None:
                infeasible += 1
                sb = order[0]
        else:
            raise ValueError(partner_rule)
        b = occ[sb]
        lengths.append(float(np.linalg.norm(P[sa] - P[sb])))
        if cache.rejected(sa, sb):
            n_rej += 1
            if rej_idx is None:
                rej_idx = k
        pair = (min(sa, sb), max(sa, sb))
        if prev == pair:
            undo += 1
        if pair in used_pairs:
            repeats += 1
        used_pairs.add(pair)
        prev = pair
        parts.update((a, b)); inits.add(a)
        occ[sa], occ[sb] = b, a
        slot_of[a], slot_of[b] = sb, sa
        tslots.append(slot_of[target])
    moved_net = sum(1 for c in range(N) if slot_of[c] != c)
    return dict(participants=len(parts), initiators=len(inits), moved_net=moved_net,
                any_rej=rej_idx is not None, first_rej=rej_idx, n_rej=n_rej, n_swaps=n_swaps,
                undo=undo, target_moves=sum(1 for i in range(1, len(tslots)) if tslots[i] != tslots[i - 1]),
                target_distinct_slots=len(set(tslots)), target_home=tslots[-1] == tslots[0],
                mean_len=float(np.mean(lengths)), max_len=float(np.max(lengths)), infeasible=infeasible,
                distinct_pairs=len(used_pairs), repeat_pairs=repeats)


def nn_graph_components(P):
    """槽位最近邻有向图（每点指向其最近邻）的弱连通分量数：NN 搭档下方块只能在分量内流动。"""
    N = len(P)
    parent = list(range(N))
    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for s in range(N):
        order, _ = nn_order(P, s)
        a, b = f(s), f(order[0])
        parent[a] = b
    return len({f(i) for i in range(N)})
