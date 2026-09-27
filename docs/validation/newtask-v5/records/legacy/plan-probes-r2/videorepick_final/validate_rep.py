# 用 specs.jsonl 的 10 条 VideoRepick 候选核对复刻是否逐位一致
import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))
from v4rep import v4_reset
rows = [json.loads(l) for l in open("scripts/configs/newtask-v4/v4-01/specs.jsonl") if '"task":"VideoRepick"' in l and '"record":"spec"' in l]
ok_all = 0
for r in rows:
    s = r["spec"]; rep = v4_reset(r["seed"])
    spec_c = [s["layout"]["cubes"][str(i)]["xy_yaw"] for i in range(6)]
    maxdiff = max(abs(a - b) for sc, rc in zip(spec_c, rep["cubes"]) for a, b in zip(sc, rc))
    same = (maxdiff == 0.0 and rep["target"] == s["objects"]["target"] and rep["n_swaps"] == s["objects"]["n_swaps"]
            and rep["num_repeats"] == s["objects"]["num_repeats"] and rep["perm_remaining"][:2] == s["objects"]["swap_initiators_remaining"]
            and max(abs(a-b) for a, b in zip(rep["rgb"], s["objects"]["color_rgb"])) == 0.0)
    ok_all += same
    print(r["episode"], r["seed"], "exact" if same else "DIFF", "maxdiff_xyyaw=%.3g" % maxdiff, "button=(%.4f,%.4f)" % rep["button"])
print(f"REPLICATION exact={ok_all}/{len(rows)}")
