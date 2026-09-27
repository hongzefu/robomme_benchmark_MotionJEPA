"""P3c：从 P3 结果补算——各外环算法「全部 count 个对象都至少参与一次」的整局比例（即若把它当 reset 级接受条件的接受率），
按干扰序号 i 的参与频率（看序号偏差的形状），以及 O1 的逐窗失败率（外推更多 swap 次数的整局可行率）。"""
import json, sys
import numpy as np
for path in sys.argv[1:]:
    R = [r for r in json.load(open(path)) if r["status"] == "ok"]
    count = R[0]["count"]
    print(f"=== {path}")
    for rule in ("O0", "O1", "O2", "O3", "O1k3", "O4"):
        cov = []; part = np.zeros(count)
        for r in R:
            s = r[rule]
            if s is None: continue
            c = np.zeros(count)
            for a, b in s: c[a] += 1; c[b] += 1
            part += c; cov.append((c > 0).all())
        print(f"  {rule}: 全员参与 {np.mean(cov):.4f} 序号参与频率 {(part/part.sum()).round(4).tolist()}")
    fails = sum(r["O1_fail"] is not None for r in R); wins = sum((r["O1_fail"] + 1) if r["O1_fail"] is not None else r["n"] for r in R)
    h = fails / wins
    print(f"  O1 逐窗失败率 {h:.5f} ⇒ 整局可行外推：n=12 {(1-h)**12:.4f} n=16 {(1-h)**16:.4f} n=20 {(1-h)**20:.4f} n=24 {(1-h)**24:.4f}")
