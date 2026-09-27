"""各拒绝循环的最坏单次接受率与预算耗尽概率（网格 + 蒙特卡洛，numpy）。"""
import math, numpy as np
rng = np.random.default_rng(7)
M = 200_000
for r in (0.3, 0.5):
    s = math.sqrt(r)
    wc = s * 0.1
    c = rng.random((M, 2)) * 0.2 - 0.1
    cin = np.max(np.abs(c), axis=1) < wc
    for seg, half in (("demo", 0.11), ("exec", 0.06)):
        wg = s * half
        grid = np.linspace(-half, half, 41)
        worst = 1.0; wg_at = None
        for gx in grid:
            for gy in grid:
                if max(abs(gx), abs(gy)) < wg:
                    continue
                acc = np.mean((~cin) & (np.linalg.norm(c - np.array([gx, gy]), axis=1) > 0.1))
                if acc < worst:
                    worst, wg_at = acc, (round(gx, 3), round(gy, 3))
        print(f"WORST r={r} 候选循环({seg}) 最坏 goal={wg_at} 单次接受率={worst:.3f} ⇒ 128 次全拒≈{(1-worst)**128:.1e}")
    # 最终 xy 循环：候选在禁区外时，局部盒 c±0.03 的可接受比例的最小值
    grid = np.linspace(-0.1, 0.1, 81)
    loc = rng.random((20000, 2)) * 0.06 - 0.03
    worst = 1.0; at = None
    for cx in grid:
        for cy in grid:
            if max(abs(cx), abs(cy)) < wc:
                continue
            f = np.array([cx, cy]) + loc
            acc = np.mean(np.max(np.abs(f), axis=1) >= wc)
            if acc < worst:
                worst, at = acc, (round(cx, 4), round(cy, 4))
    print(f"WORST r={r} 最终 xy 循环 最坏候选={at} 单次接受率={worst:.3f} ⇒ 256 次全拒≈{(1-worst)**256:.1e}")
    print(f"WORST r={r} 杆 128 次全拒={r**128:.1e}；goal 256 次全拒={r**256:.1e}")
# V4 对照：候选循环（无中心判据）最坏
c = rng.random((M, 2)) * 0.2 - 0.1
for seg, half in (("demo", 0.11), ("exec", 0.06)):
    grid = np.linspace(-half, half, 41)
    worst = min(np.mean(np.linalg.norm(c - np.array([gx, gy]), axis=1) > 0.1) for gx in grid for gy in grid)
    print(f"WORST V4 b=0 候选循环({seg}) 单次接受率最坏={worst:.3f}")
