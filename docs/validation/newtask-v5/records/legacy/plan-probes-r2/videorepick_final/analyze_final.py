import json, sys, os, collections
import numpy as np
D = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(D, "final_rule_sim_2400.json")))
M = len(R)
def v(ep, k): return (ep.get(k) if isinstance(ep, dict) else None)
print(f"局数={M}  exact_obb 与退化 OBB 摆放逐位一致={sum(o['exact_eq_actor'] for o in R)}/{M}")
def col(key):
    eps = [o[key] for o in R]; pl = [e for e in eps if e.get("placed")]; ok = [e for e in pl if e.get("plan")]
    f = lambda k: np.mean([e[k] for e in ok])
    row = dict(place_ok=len(pl)/M, plan_fail=1-len(ok)/max(1,len(pl)), cell3=np.mean([e["cell3"] for e in pl]),
               all6=np.mean([e["all6"] for e in ok]), tmoves=f("tmoves"), tmoves_p_le2=np.mean([e["tmoves"]<=2 for e in ok]),
               tm_hist=dict(sorted(collections.Counter(e["tmoves"] for e in ok).items())), maxmult=f("maxmult"),
               maxmult_max=max(e["maxmult"] for e in ok), p_maxmult_ge3=np.mean([e["maxmult"]>=3 for e in ok]), distinct=f("distinct"),
               path_mean=f("meanL"), path_max_mean=f("maxL"), path_max=max(e["maxL"] for e in ok),
               path_max_p95=float(np.percentile([e["maxL"] for e in ok], 95)))
    if "d5_nominal" in ok[0]: row["d5_nominal_ep"] = np.mean([e["d5_nominal"] > 0 for e in ok])
    for k in ("pert12", "pert20", "fallback"):
        if k in ok[0]: row[k] = np.mean([bool(e[k]) for e in ok])
    if "fail_k" in (pl[0] if pl else {}) or any("fail_k" in e for e in pl):
        row["fail_k_hist"] = dict(sorted(collections.Counter(e["fail_k"] for e in pl if not e.get("plan")).items()))
    if key == "final":
        row["min_pair_min"] = min(e["min_pair"] for e in pl)
        row["trials_mean"] = np.mean([e["trials"] for e in pl])
        # 单段最长路径分布（全部交换段）
        row["init6"] = np.mean([e["init6"] for e in ok])
    return row
out = {k: col(k) for k in ("v4", "k2", "final", "final_A")}
for k, r in out.items():
    print(f"== {k}"); [print(f"  {a}: {b:.4f}" if isinstance(b, float) else f"  {a}: {b}") for a, b in r.items()]
json.dump(out, open(os.path.join(D, "analyze_final_2400.json"), "w"), default=float, indent=1)
# 峰值速度（解析）：smoothstep + 0.07 sin(pi α) 弯道，50 步窗口，逐控制步位移最大值
def peak_disp(Lm, lane=0.07, n=50):
    t = np.arange(n + 1) / n; a = t * t * (3 - 2 * t); x = Lm * a; y = lane * np.sin(np.pi * a)
    return float(np.max(np.hypot(np.diff(x), np.diff(y))))
for Lm in (0.10, 0.12, 0.16, 0.20, 0.25, 0.30, 0.35):
    print(f"peak_disp L={Lm:.2f} m → {peak_disp(Lm)*1000:.2f} mm/step = {peak_disp(Lm)*20:.3f} m/s (20 Hz)")
