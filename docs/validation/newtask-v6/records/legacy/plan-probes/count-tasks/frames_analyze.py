"""只读：汇总 frames/<env>.json，给出逐类段长统计、总帧数按难度分布、以及 T = a + b·单位数 的线性拟合与 5000 帧上限推算。"""
import json, sys
from collections import defaultdict
import numpy as np

D = "artifacts/newtask-v6/plan-probes/count-tasks/frames"
UNIT = {  # 每环境「一个单位」由哪些段组成
    "BinFill": ("pick", "place"),
    "PickXtimes": ("pick", "place"),
    "SwingXtimes": ("swingR", "swingL"),
    "PickHighlight": ("pick", "putback"),
}
LIMIT = 5000
out = {}
for env, unit in UNIT.items():
    rows = json.load(open(f"{D}/{env}.json"))
    print(f"\n===== {env}（{len(rows)} 局）=====")
    bydiff = defaultdict(list)
    for r in rows:
        bydiff[(r["src"], r["difficulty"])].append(r)
    for k in sorted(bydiff):
        Ts = [r["T"] for r in bydiff[k]]
        us = [r["counts"].get(unit[0], 0) for r in bydiff[k]]
        print(f"  {k[0]:8s} {k[1]:6s} n={len(Ts):3d} T 均值 {np.mean(Ts):7.1f} 中位 {np.median(Ts):6.0f} 最大 {max(Ts):5d}  单位数({unit[0]}) {min(us)}~{max(us)}")
    cats = defaultdict(list)
    for r in rows:
        for c, v in r["lens"].items():
            cats[(r["src"] == "v5-01", c)].extend(v)
    print("  段长（帧）：")
    for (isv5, c), v in sorted(cats.items()):
        v = np.array(v)
        print(f"    {'v5xhard' if isv5 else 'official'} {c:10s} n={len(v):4d} 均值 {v.mean():6.1f} sd {v.std():5.1f} p95 {np.percentile(v,95):6.0f} 最大 {v.max():4d}")
    # 线性拟合：T ≈ a + b·u（u = 单位数），全部局一起
    u = np.array([r["counts"].get(unit[0], 0) for r in rows], float)
    T = np.array([r["T"] for r in rows], float)
    A = np.vstack([np.ones_like(u), u]).T
    (a, b), *_ = np.linalg.lstsq(A, T, rcond=None)
    resid = T - (a + b * u)
    # 保守每单位：各局 (T - 固定开销) / u 的 p95
    per_unit = np.array([(r["T"]) / max(1, r["counts"].get(unit[0], 0)) for r in rows])
    unit_len = []
    for r in rows:
        n = r["counts"].get(unit[0], 0)
        s = sum(sum(r["lens"].get(c, [])) for c in unit)
        if n:
            unit_len.append(s / n)
    unit_len = np.array(unit_len)
    fixed = T - np.array([sum(sum(r["lens"].get(c, [])) for c in unit) for r in rows])
    ul95 = np.percentile(unit_len, 95); ulmax = unit_len.max()
    fx95 = np.percentile(fixed, 95); fxmax = fixed.max()
    print(f"  拟合 T ≈ {a:.1f} + {b:.1f}·u（残差 sd {resid.std():.1f}，最大 {resid.max():.1f}）")
    print(f"  每单位帧数（局内均值）: 均值 {unit_len.mean():.1f} p95 {ul95:.1f} 最大 {ulmax:.1f}；固定开销（非单位段）均值 {fixed.mean():.1f} p95 {fx95:.0f} 最大 {fxmax:.0f}")
    umax_mean = (LIMIT - fixed.mean()) / unit_len.mean()
    umax_cons = (LIMIT - fxmax) / ulmax
    print(f"  5000 帧下单位数上限：按均值 {umax_mean:.1f}，按最坏（固定开销最大 + 每单位最大）{umax_cons:.1f}")
    out[env] = dict(a=a, b=b, resid_sd=float(resid.std()), unit_mean=float(unit_len.mean()), unit_p95=float(ul95),
                    unit_max=float(ulmax), fixed_mean=float(fixed.mean()), fixed_max=float(fxmax),
                    umax_mean=float(umax_mean), umax_cons=float(umax_cons))
json.dump(out, open(f"{D}/summary.json", "w"), ensure_ascii=False, indent=1)
