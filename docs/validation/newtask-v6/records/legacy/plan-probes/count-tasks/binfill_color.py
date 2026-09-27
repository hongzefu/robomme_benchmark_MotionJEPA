"""BinFill：更多方块 / 更多投入数时，配额规则与同色成团上限（color_mix T=3, link 0.09, K=64）是否还撑得住。

配额逐式复刻 BinFill._load_scene（num_colors=3）：color_pool=randperm(3)；put_in_color∈[2,3]；
总投入 total∈[lo,hi] 逐个均匀分给前 put_in_color 种色；spawn 每色先取 max(target,1)，余量逐个均匀分给 3 色。
位置用 run_mc.binfill 的复刻（现值框或放大框），成团判据同 _max_same_color_component（≤ link 相连）。
"""
import sys, json
import numpy as np
from run_mc import binfill


def quota(rng, N, lo, hi, pic=(2, 3)):
    pool = list(rng.permutation(3))
    k = int(rng.integers(pic[0], pic[1] + 1))
    active = pool[:k]
    tgt = [0, 0, 0]
    total = int(rng.integers(lo, hi + 1))
    for _ in range(total):
        tgt[active[int(rng.integers(len(active)))]] += 1
    sp = [0, 0, 0]
    for i in pool:
        sp[i] = max(tgt[i], 1)
    for _ in range(max(0, N - sum(sp))):
        sp[pool[int(rng.integers(3))]] += 1
    return tgt, sp


def max_comp(P, lab, link=0.09):
    n = len(P)
    D = np.linalg.norm(P[:, None] - P[None], axis=-1)
    seen = np.zeros(n, bool); best = 0
    for s in range(n):
        if seen[s]:
            continue
        seen[s] = True; st = [s]; sz = 0
        while st:
            u = st.pop(); sz += 1
            for v in np.flatnonzero((~seen) & (lab == lab[u]) & (D[u] <= link)):
                seen[v] = True; st.append(v)
        best = max(best, sz)
    return best


def run(N, lo, hi, region_half=(0.2, 0.25), eps=1024, seed=3):
    rng = np.random.default_rng(seed * 100 + N)
    n_ok = 0; red = []; fb = 0; over = 0; maxcol = []; spawn_gt_N = 0
    for e in range(eps):
        tgt, sp = quota(rng, N, lo, hi)
        if sum(sp) != N:
            spawn_gt_N += 1   # 目标数超过 N 时原规则会让实际块数 > N（配额口径问题）
        ok, cs, _ = binfill(rng, sum(sp), region_half=region_half)
        if not ok:
            continue
        n_ok += 1
        P = np.array(cs)
        lab0 = np.array(sum([[c] * sp[c] for c in range(3)], []))
        lab = lab0[rng.permutation(len(lab0))]   # spawn_order 洗牌
        best = max_comp(P, lab); r = 0
        while best > 3 and r < 64:
            r += 1
            c = max_comp(P, lab[rng.permutation(len(lab))])
            best = min(best, c)
        red.append(r); fb += best > 3; over += max(sp) >= 8; maxcol.append(max(sp))
    print(f"N={N:2d} put_in=[{lo},{hi}] 框半宽={region_half}: reset 成功 {n_ok}/{eps}；需重排 {np.mean(np.array(red)>0)*100:.1f}% "
          f"平均重排 {np.mean(red):.2f}；兜底（团>3）{fb}/{n_ok}={fb/max(1,n_ok)*100:.2f}%；单色最多块数 中位 {np.median(maxcol):.0f} 最大 {max(maxcol)}；"
          f"总块数≠N 的局 {spawn_gt_N}", flush=True)
    return dict(N=N, lo=lo, hi=hi, region_half=region_half, reset_ok=n_ok, redraw_frac=float(np.mean(np.array(red) > 0)),
                fallback=fb, max_single_color_max=int(max(maxcol)))


if __name__ == "__main__":
    rows = []
    for N, lo, hi, rh in [(12, 5, 7, (0.2, 0.25)), (14, 7, 9, (0.2, 0.25)), (16, 9, 11, (0.2, 0.25)),
                          (17, 10, 12, (0.2, 0.25)), (18, 11, 13, (0.2, 0.32)), (20, 12, 14, (0.2, 0.32)),
                          (16, 8, 10, (0.2, 0.25)), (18, 10, 12, (0.2, 0.32))]:
        rows.append(run(N, lo, hi, rh))
    json.dump(rows, open("binfill_color.json", "w"), ensure_ascii=False, indent=1)
