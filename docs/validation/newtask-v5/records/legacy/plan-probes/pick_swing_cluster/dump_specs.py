"""把 specs.jsonl 中 PickXtimes / SwingXtimes 的 10 条候选布局打印成表。"""
import json, math, itertools
P="/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/configs/newtask-v4/v4-01/specs.jsonl"
rows=[json.loads(l) for l in open(P)]
hdr=rows[0]
for env in ["PickXtimes","SwingXtimes"]:
    print("=====",env)
    print(json.dumps(hdr["sampling_config"][env], ensure_ascii=False)[:3000])
    for r in rows[1:]:
        if r.get("task")!=env: continue
        s=r["spec"]; L=s["layout"]; O=s["objects"]
        print(f"-- ep{r['episode']} seed{r['seed']} sel={r['selected']} num={O['num_repeats']} tgt_idx={O.get('target_cube_idx')} cand={O.get('target_candidates')} order={O.get('color_order')}")
        print("   keys:", list(L.keys()))
        pts={}
        for k,v in L.get("cubes",{}).items(): pts["C:"+k]=v[:2]
        for k,v in L.get("distractors",{}).items(): pts["D:"+k]=v[:2]
        if "goal_xy" in L: print("   goal", [round(x,3) for x in L["goal_xy"]])
        if "targets" in L: print("   targets", {k:[round(x,3) for x in v] for k,v in L["targets"].items()} if isinstance(L["targets"],dict) else L["targets"])
        print("   button", [round(x,3) for x in L["button_xy"]])
        for k,v in pts.items(): print(f"   {k:12s} x={v[0]:+.3f} y={v[1]:+.3f}")
        # 两两距离
        ks=list(pts); dmin=min(math.dist(pts[a],pts[b]) for a,b in itertools.combinations(ks,2))
        print("   min pairwise (6 cubes) =", round(dmin,3))
