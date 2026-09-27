# 对比 exec（真实物理跟踪）与 dry（规划末点 FK）两种口径在 0.1 粗网格上的一致性
import glob, json
import pandas as pd, numpy as np
d = pd.read_csv("reach_grid.csv")
e = pd.concat([pd.read_csv(f) for f in glob.glob("exec_check/*.csv")])
k = ["x", "y", "yaw_deg", "pose_type", "direction"]
for df in (d, e):
    df["x"] = df.x.round(4); df["y"] = df.y.round(4)
m = e.merge(d, on=k, suffixes=("_e", "_d"))
out = {"n": len(m), "ok_agree": float((m.ok_e == m.ok_d).mean()),
       "plan_agree": float((m.plan_ok_e == m.plan_ok_d).mean()),
       "n_ok_diff": int((m.ok_e != m.ok_d).sum()),
       "err_absdiff_cm_median": float((m.err_cm_e - m.err_cm_d).abs().median()),
       "err_absdiff_cm_max": float((m.err_cm_e - m.err_cm_d).abs().max())}
diff = m[m.ok_e != m.ok_d][k + ["err_cm_e", "err_cm_d", "note_e", "note_d"]]
print(json.dumps(out, ensure_ascii=False)); print(diff.to_string())
json.dump(out, open("exec_check/summary.json", "w"), ensure_ascii=False)
