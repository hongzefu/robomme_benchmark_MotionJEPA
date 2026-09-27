"""汇总 reset 探针结果。"""
import json, glob, collections, os
D = os.path.dirname(os.path.abspath(__file__))
for f in sorted(glob.glob(f"{D}/reset/*.jsonl")):
    rows = [json.loads(l) for l in open(f)]
    n = len(rows); ok = sum(r["ok"] for r in rows)
    errs = collections.Counter((r.get("err"), (r.get("msg") or "")[:40]) for r in rows if not r["ok"])
    wall = sum(r["wall_s"] for r in rows)
    extra = ""
    if "PickHighlight" in f:
        c = collections.Counter(r.get("n_cubes") for r in rows if r["ok"])
        p = collections.Counter(r.get("n_pick") for r in rows if r["ok"])
        d = collections.Counter(r.get("n_cubes") - r.get("n_pick") for r in rows if r["ok"] and r.get("n_pick") is not None)
        extra = f" spawn={dict(sorted(c.items()))} pick={dict(sorted(p.items()))} distract={dict(sorted(d.items()))}"
    if "Xtimes" in f:
        c = collections.Counter(r.get("n_cubes") for r in rows if r["ok"]); extra = f" all_cubes={dict(c)}"
    print(f"{os.path.basename(f)[:-6]:22s} n={n} ok={ok} fail={n-ok} rate={ok/n*100:.1f}% wall_mean={wall/n:.2f}s errs={dict(errs)}{extra}")
