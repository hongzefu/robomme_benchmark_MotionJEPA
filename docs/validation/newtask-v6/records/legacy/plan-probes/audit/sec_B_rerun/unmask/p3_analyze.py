"""P3 结果汇总：各外环算法的整局可行率、对象级参与频率（按干扰序号 i）与卡方、局内均衡、撤销率、平均路径长度；
以及第 0 窗「搭档距离名次」→ 可行率。用法：p3_analyze.py <json>..."""
import json, sys, collections
import numpy as np
from scipy.stats import chisquare
RULES = ("O0", "O1", "O2", "O3", "O1k3", "O4")
for path in sys.argv[1:]:
    R = json.load(open(path))
    st = collections.Counter(r["status"] for r in R)
    ok = [r for r in R if r["status"] == "ok"]
    count = ok[0]["count"]
    print(f"=== {path} 局数 {len(R)} 状态 {dict(st)} 每窗可行槽对密度均值 {np.mean([r['G_density'] for r in ok]):.3f}（即 {count*(count-1)//2} 对中约 {np.mean([r['G_density'] for r in ok])*count*(count-1)/2:.1f} 对可行） 墙钟 p50 {np.median([r['wall'] for r in ok]):.2f}s")
    deg = np.array([r["slot_deg"] for r in ok])
    print(f"  槽的平均可行搭档数：均值 {deg.mean():.2f}，局内「0 个可行搭档的槽」占比 {np.mean(deg == 0):.3f}")
    rk = collections.defaultdict(lambda: [0, 0])
    for r in ok:
        for ra, rb, f in r["rank_feas"]:
            m = min(ra, rb); rk[m][0] += f; rk[m][1] += 1
    print("  第 0 窗：按「两者互为第几近邻（取小）」的可行率：" + " ".join(f"r{m}={rk[m][0]/rk[m][1]:.3f}" for m in sorted(rk)[:6]))
    for rule in RULES:
        seqs = [(r, r[rule]) for r in ok if r[rule] is not None]
        part = np.zeros(count); spread = []; cover = []; undo = []; untouched = []
        for r, s in seqs:
            c = np.zeros(count)
            for k, (a, b) in enumerate(s):
                part[a] += 1; part[b] += 1; c[a] += 1; c[b] += 1
                if k: undo.append(tuple(s[k - 1]) == (a, b))
            spread.append(c.max() - c.min()); untouched.append(np.mean(c == 0))
            cover.append(2 * len(s) >= count and (c > 0).all())
        chi = chisquare(part)
        feas = len(seqs) / len(ok)
        plen = np.mean([r[rule + "_plen"] for r, _ in seqs])
        imb = np.mean([r[rule + "_imb"] for r, _ in seqs])
        print(f"  {rule}: 整局可行 {feas:.4f} 参与频率 min/max {part.min()/part.sum():.4f}/{part.max()/part.sum():.4f}（均匀 {1/count:.4f}）χ²={chi.statistic:.1f} p={chi.pvalue:.3g} | "
              f"局内极差均值 {np.mean(spread):.2f} 未参与对象占比 {np.mean(untouched):.3f} 撤销率 {np.mean(undo):.3f} 平均交换距离 {plen:.3f} m 失衡事件/局 {imb:.2f}")
