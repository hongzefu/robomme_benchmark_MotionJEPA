"""M1c：7700102 运行期与名义预演的第 1 段搭档不同——看是否临界等距；并统计合成布局里内部最近邻「第一 vs 第二」距离差 < 1/2/5 mm 的比例。"""
import sys, numpy as np, collections
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap")
from replica import bus_layout, vus_layout, inner_sequence, initiators
lay = bus_layout(7700102); lay["n_swaps"] = 6
for k, (a, b, d, pos, yaw) in enumerate(inner_sequence(lay)[:3]):
    ds = {j: float(np.linalg.norm(pos[a] - pos[j])) for j in range(4) if j != a}
    print("window", k, "initiator", a, "partner", b, {j: round(v, 5) for j, v in ds.items()})
# 运行期搭档解析读的是上一段 alpha=smoothstep(32/33) 时的位置（本步末才落终态）：模拟该偏差
def smooth(x): return x * x * (3 - 2 * x)
al = smooth(32 / 33)
for name, fn, base in (("VideoUnmaskSwap", vus_layout, 9_100_000), ("ButtonUnmaskSwap", bus_layout, 9_300_000)):
    margins = []; flips = 0; tot = 0
    for i in range(1000):
        lay = fn(base + i)
        if lay.get("spawn_fail"): continue
        seq = inner_sequence(lay)
        for k in range(1, len(seq)):
            a, b, d, pos, yaw = seq[k]
            pa, pb = seq[k - 1][0], seq[k - 1][1]
            ds = sorted(float(np.linalg.norm(pos[a] - pos[j])) for j in range(4) if j != a)
            margins.append(ds[1] - ds[0])
            # 上一段在 alpha=al 处的位置（含侧移 0.07 sin(pi al)）
            p0 = [p.copy() for p in seq[k - 1][3]]
            A, B = p0[pa], p0[pb]
            dvec = B - A; n = np.array([-dvec[1], dvec[0]]); n = n / np.linalg.norm(n)
            off = 0.07 * np.sin(np.pi * al)
            cur = [p.copy() for p in pos]
            cur[pa] = A + dvec * al + n * off; cur[pb] = B - dvec * al - n * off
            best = min((j for j in range(4) if j != a), key=lambda j: (float(np.linalg.norm(np.float32(cur[a]) - np.float32(cur[j]))), j))
            flips += best != b; tot += 1
    m = np.array(margins)
    print(f"{name}: windows={tot} nn_margin<1mm={np.mean(m<0.001):.4f} <2mm={np.mean(m<0.002):.4f} <5mm={np.mean(m<0.005):.4f}; partner_flip_due_to_unfinished_prev_swap={flips}/{tot}")
