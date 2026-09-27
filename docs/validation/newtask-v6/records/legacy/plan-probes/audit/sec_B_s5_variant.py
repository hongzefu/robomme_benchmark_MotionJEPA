"""审计：计划 2.2 描述的内环 S5（键 = 两块参与次数之和；禁止与上一对相同；整条极差>1 重排 ≤20 次，仍不行接受）
与原探针 p2c/p2d 实测的变体（键 = (max, sum) 字典序；不重排）在同一批 G（原 p2_inner_*.json，只读）上的对比。种子固定 seed+17。"""
import json, sys
import numpy as np
from scipy.stats import chisquare
N = 4; PAIRS = [(a, b) for a in range(N) for b in range(a + 1, N)]
SRC = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/plan-probes/unmask"
def conn(G):
    e = [p for p, g in zip(PAIRS, G) if g]; seen = {0}; st = [0]
    while st:
        u = st.pop()
        for a, b in e:
            for x, y in ((a, b), (b, a)):
                if x == u and y not in seen: seen.add(y); st.append(y)
    return len(seen) == N
def once(G, n, rng, key):
    occ = list(range(N)); cnt = [0] * N; last = None; seq = []
    for k in range(n):
        allf = [(a, b) for a, b in PAIRS if G[(min(occ[a], occ[b]), max(occ[a], occ[b]))]]
        c = [p for p in allf if p != last] or allf
        if not c: return None, None
        ks = [key(cnt, a, b) for a, b in c]; m = min(ks)
        c = [p for p, kk in zip(c, ks) if kk == m]; a, b = c[rng.integers(len(c))]
        seq.append((a, b)); cnt[a] += 1; cnt[b] += 1; occ[a], occ[b] = occ[b], occ[a]; last = (a, b)
    return seq, cnt
KEYS = {"maxsum": lambda c, a, b: (max(c[a], c[b]), c[a] + c[b]), "sum": lambda c, a, b: c[a] + c[b]}
for task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
    R = json.load(open(f"{SRC}/p2_inner_{task}.json"))
    for only_conn in (False, True):
        for kname in ("maxsum", "sum"):
            for retry in (1, 20):
                part = np.zeros(N); spreads = []; undo = []; ok = 0; tot = 0
                for r in R:
                    if only_conn and not conn(r["G"]): continue
                    tot += 1
                    G = {p: bool(g) for p, g in zip(PAIRS, r["G"])}
                    rng = np.random.default_rng(r["seed"] + 17)
                    best = None
                    for t in range(retry):
                        seq, cnt = once(G, r["n"], rng, KEYS[kname])
                        if seq is None: break
                        best = (seq, cnt)
                        if max(cnt) - min(cnt) <= 1: break
                    if best is None: continue
                    ok += 1; seq, cnt = best
                    for a, b in seq: part[a] += 1; part[b] += 1
                    undo += [seq[i] == seq[i - 1] for i in range(1, len(seq))]
                    spreads.append(max(cnt) - min(cnt))
                sp = np.array(spreads)
                print(f"{task:17s} G连通子集={only_conn!s:5} 键={kname:6s} 重排上限={retry:2d} 可行 {ok}/{tot} 边际p={chisquare(part).pvalue:.3f} "
                      f"极差均值 {sp.mean():.2f} 极差<=1 {np.mean(sp<=1):.4f} <=2 {np.mean(sp<=2):.4f} 撤销率 {np.mean(undo):.4f}")
