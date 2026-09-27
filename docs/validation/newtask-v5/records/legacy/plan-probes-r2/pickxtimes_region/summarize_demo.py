import json, sys, statistics as st
from pathlib import Path
D = Path(__file__).parent
out = {}
for tag in ("demo_hw0p20", "demo_hw0p25"):
    rows = [json.loads(l) for l in open(D / tag / "summary.jsonl")]
    ok = [r for r in rows if r["ok"]]
    far = [r for r in rows if r["target_reach"] > 0.75]
    out[tag] = {"n": len(rows), "ok": len(ok), "fails": [(r["seed"], r["failure_class"], r["error_type"], r["error"][:200]) for r in rows if not r["ok"]],
                "steps": [r["h5_steps"] for r in rows], "steps_mean": round(st.mean(r["h5_steps"] for r in ok), 1),
                "steps_min": min(r["h5_steps"] for r in ok), "steps_max": max(r["h5_steps"] for r in ok),
                "layout_diff_max": max(r["layout_vs_offline_maxabs"] for r in rows),
                "far_target_n": len(far), "far_target_ok": sum(r["ok"] for r in far),
                "max_target_reach": max(r["target_reach"] for r in rows), "max_cube_reach": max(r["max_cube_reach"] for r in rows),
                "reset_s_mean": round(st.mean(r["phases"]["reset_s"] for r in rows if r.get("phases")), 2)}
json.dump(out, open(D / "demo_summary.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
