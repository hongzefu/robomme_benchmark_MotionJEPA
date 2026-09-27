"""用 specs.jsonl 的 20 条（PickXtimes/SwingXtimes 各 10）逐位核对复刻器。"""
import json, sys
sys.path.insert(0, sys.argv[1])
from replica import pick_layout, swing_layout
P="/data/hongzefu/robomme_v5_probe_wt/scripts/configs/newtask-v4/v4-01/specs.jsonl"
rows=[json.loads(l) for l in open(P)][1:]
tot=ok=0
for r in rows:
    env=r["task"]
    if env not in ("PickXtimes","SwingXtimes"): continue
    L=r["spec"]["layout"]; seed=r["seed"]
    out = pick_layout(seed) if env=="PickXtimes" else swing_layout(seed)
    exp={}
    for k,v in L["cubes"].items(): exp[k]=v
    for k,v in L["distractors"].items(): exp[k]=v
    got={}
    for (n,x,y,yaw) in out["colored"]: got[f"{n}_0"]=[x,y,yaw]
    for (n,x,y,yaw) in out["distractors"]: got[f"{n}_0"]=[x,y,yaw]
    exp["button"]=L["button_xy"]; got["button"]=list(out["button"])
    if env=="PickXtimes":
        exp["goal"]=L["goal_xy"]; got["goal"]=list(out["goal"])
    else:
        for i in ("0","1"): exp["disk"+i]=L["targets"][i]
        got["disk0"]=list(out["disks"][0]); got["disk1"]=list(out["disks"][1])
    bad=[k for k in exp if any(abs(a-b)>0 for a,b in zip(exp[k],got[k]))]
    maxd=max(max(abs(a-b) for a,b in zip(exp[k],got[k])) for k in exp)
    tot+=1; ok+= (len(bad)==0)
    print(env, seed, "EXACT" if not bad else f"DIFF {bad}", f"maxabs={maxd:.3g}", "tidx", out["target_idx"], r["spec"]["objects"]["target_cube_idx"])
print(f"REPLICA_EXACT={ok}/{tot}")
