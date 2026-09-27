"""Geometry of the 10 frozen V4 InsertPeg candidates (effective layout = last initialization) vs rollout outcome."""
import json, sys, itertools
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
import peggeom as G

REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
rows = [json.loads(l) for l in open(f"{REPO}/scripts/configs/newtask-v4/v4-01/specs.jsonl")][1:]
rows = {r["episode"]: r for r in rows if r["task"] == "InsertPeg"}
res = {}
for l in open(f"{REPO}/artifacts/newtask-v4/v4-01/rollout/run1/results.jsonl"):
    d = json.loads(l)
    if d["task"] == "InsertPeg":
        res[d["episode"]] = d
print("ep ok  err_type            obj grasp  tgt_root(x,y)     tgt_yaw  d03_root  min_root_all  tgt_minRectGap  tgt_visOvl tgt_collOvl any_visOvl  finger_intrude(grasped end)  finger_intrude(either end)  peg-box ovl(tgt/any)")
agg = []
for ep in range(10):
    spec = rows[ep]["spec"]
    init = spec["initializations"][str(max(int(k) for k in spec["initializations"]))]
    pegs = [init["pegs"][str(i)] for i in range(4)]
    roots = [np.array(p[0]) for p in pegs]; yaws = [p[1] for p in pegs]
    box_xy = np.array(init["box_jitter"]); box_yaw = init["box_yaw"]
    pm = {}
    for i, j in itertools.combinations(range(4), 2):
        pm[(i, j)] = G.pair_metrics(roots[i], np.float64(yaws[i]), roots[j], np.float64(yaws[j]))
    tgt_pairs = [pm[(0, j)] for j in (1, 2, 3)]
    obj_flag = -1 if init["obj_sample"] == 0 else 1
    grasp = "head" if obj_flag == -1 else "tail"
    u0 = G.axis(np.float64(yaws[0]))
    head_c = roots[0]; tail_c = roots[0] - G.L * u0
    def intrude(link_c):
        fl, fr = G.finger_rects(link_c, np.float64(yaws[0]))
        hit = []
        for j in (1, 2, 3):
            rj = G.peg_rect(roots[j], np.float64(yaws[j]))
            if G.rect_intersect(fl, rj) or G.rect_intersect(fr, rj):
                hit.append(j)
        return hit
    gi = intrude(head_c if grasp == "head" else tail_c)
    ei = sorted(set(intrude(head_c)) | set(intrude(tail_c)))
    br = G.box_rect(box_xy, box_yaw)
    pb = [bool(G.rect_intersect(G.peg_rect(roots[i], np.float64(yaws[i])), br)) for i in range(4)]
    ok = res[ep]["ok"]
    row = dict(ep=ep, ok=ok, err=res[ep]["error_type"], grasp=grasp,
               d03=float(pm[(0, 3)]["root_dist"]),
               min_root=min(float(m["root_dist"]) for m in pm.values()),
               tgt_gap=min(float(m["rect_gap"]) for m in tgt_pairs),
               tgt_vis=any(bool(m["visual_overlap"]) for m in tgt_pairs),
               tgt_coll=any(bool(m["collision_overlap"]) for m in tgt_pairs),
               any_vis=any(bool(m["visual_overlap"]) for m in pm.values()),
               gi=gi, ei=ei, pb=pb, root=roots[0], yaw=np.degrees(yaws[0]))
    agg.append(row)
    print(f"{ep:2d} {str(ok):5s} {str(row['err']):20s} {obj_flag:3d} {grasp:5s} ({roots[0][0]:+.3f},{roots[0][1]:+.3f}) {row['yaw']:+7.1f}  {row['d03']:.4f}    {row['min_root']:.4f}        {row['tgt_gap']:.4f}          {str(row['tgt_vis']):5s}      {str(row['tgt_coll']):5s}      {str(row['any_vis']):5s}      {str(gi):10s}                {str(ei):10s}                 {pb[0]}/{any(pb)}")
succ = [r for r in agg if r["ok"]]; fail = [r for r in agg if not r["ok"]]
for name, grp in (("success", succ), ("failed", fail)):
    print(f"{name}: n={len(grp)} tgt_visual_overlap={sum(r['tgt_vis'] for r in grp)} tgt_coll_overlap={sum(r['tgt_coll'] for r in grp)} "
          f"grasped_end_finger_intrusion={sum(bool(r['gi']) for r in grp)} mean_tgt_rect_gap={np.mean([r['tgt_gap'] for r in grp]):.4f} "
          f"min_tgt_rect_gap={min(r['tgt_gap'] for r in grp):.4f}")
