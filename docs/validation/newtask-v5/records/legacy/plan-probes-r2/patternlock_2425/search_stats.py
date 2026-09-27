"""汇总 search_probe.json：各预算命中率、命中尝试次数与墙钟分位。"""
import json, numpy as np, sys
D = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "search_probe.json"))
for name, recs in D.items():
    n = len(recs); att = np.array([r["hit_attempt"] for r in recs if r["hit_attempt"]])
    wall = np.array([r["wall_s"] for r in recs])
    per_att = wall.sum() / sum((r["hit_attempt"] or 20000) for r in recs)
    hr = {b: float(np.mean([bool(r["hit_attempt"] and r["hit_attempt"] <= b) for r in recs])) for b in (1000, 5000, 10000, 20000)}
    q = lambda a, p: float(np.percentile(a, p)) if len(a) else None
    print(f"{name}: N={n} " + " ".join(f"hit@{b}={v:.3f}" for b, v in hr.items()) +
          f" | attempts median={q(att,50):.0f} p95={q(att,95):.0f} max={att.max() if len(att) else None} mean={att.mean():.0f}"
          f" | wall_s median={q(wall,50):.3f} p95={q(wall,95):.3f} max={wall.max():.3f} | per_attempt_ms={per_att*1e3:.3f}"
          f" | miss={n-len(att)} miss_final_len={[r['final_len'] for r in recs if not r['hit_attempt']]}")
