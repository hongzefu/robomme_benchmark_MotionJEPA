"""预筛开/关判定一致性：同 seed 的状态、尝试次数、放置、外环交换对逐项比较；并比规划墙钟。"""
import json, numpy as np
for t in ["VideoUnmaskSwap", "ButtonUnmaskSwap"]:
    on = {r["seed"]: r for r in map(json.loads, open(f"offline_{t}_main.jsonl"))}
    off = [json.loads(l) for l in open(f"offline_{t}_pf0.jsonl")]
    same = 0
    for r in off:
        a = on[r["seed"]]
        eq = a["status"] == r["status"] and a.get("n_attempts") == r.get("n_attempts") and a.get("pairs") == r.get("pairs") \
            and (a.get("placements") is None or np.allclose(a["placements"], r["placements"], atol=0, rtol=0))
        same += eq
    ton = np.array([on[r["seed"]]["t"] for r in off]); toff = np.array([r["t"] for r in off])
    print(f"PREFILTER_EQUIV {t} same={same}/{len(off)} plan_s_on mean={ton.mean():.3f} p95={np.percentile(ton,95):.3f} | off mean={toff.mean():.1f} p95={np.percentile(toff,95):.1f} max={toff.max():.1f}")
