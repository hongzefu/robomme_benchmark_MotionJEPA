# 抽查：BinFill xhard 配额（color 3、put_in_color [2,3]、put_in [5,7]、spawn 12）下多数色 ≥7 的概率
import numpy as np
rng = np.random.default_rng(3)
N = 200000; cnt = {}
for _ in range(N):
    pool = list(rng.permutation(3))
    pic = rng.integers(2, 4)
    active = pool[:pic]
    tgt = [0, 0, 0]
    for _ in range(rng.integers(5, 8)):
        tgt[active[rng.integers(0, len(active))]] += 1
    sp = [0, 0, 0]
    for i in pool: sp[i] = max(tgt[i], 1)
    for _ in range(max(0, 12 - sum(sp))):
        sp[pool[rng.integers(0, 3)]] += 1
    m = max(sp); cnt[m] = cnt.get(m, 0) + 1
tot = sum(cnt.values())
print({k: round(v / tot, 4) for k, v in sorted(cnt.items())}, "P(>=7)=", round(sum(v for k, v in cnt.items() if k >= 7) / tot, 4))
