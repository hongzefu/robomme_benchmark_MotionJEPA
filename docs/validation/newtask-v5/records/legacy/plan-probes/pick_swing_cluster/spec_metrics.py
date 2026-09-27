"""对 specs.jsonl 的 10+10 条实际候选计算与 cluster_stats 相同的指标，并标出 <6cm 的方块对及其 OBB 是否退化。"""
import json, sys, math, itertools
sys.path.insert(0, sys.argv[1])
import numpy as np
from cluster_stats import metrics, PICK_BOX, SWING_BOX
from replica import cube_obb2d
P="/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/configs/newtask-v4/v4-01/specs.jsonl"
rows=[json.loads(l) for l in open(P)][1:]
for env, box in (("PickXtimes", PICK_BOX), ("SwingXtimes", SWING_BOX)):
    agg=[]
    print("=====", env)
    for r in rows:
        if r["task"]!=env: continue
        L=r["spec"]["layout"]; O=r["spec"]["objects"]
        order=O["color_order"]; names=["red","blue","green"]
        colored=[tuple(L["cubes"][f"{names[i]}_0"][:2]) for i in order]  # 放置顺序
        dist=[tuple(L["distractors"][f"{n}_0"][:2]) for n in ["yellow","cyan","magenta"]]
        tgt=colored[O["target_cube_idx"]]
        m=metrics(colored, dist, box, tgt); agg.append(m)
        # 退化 OBB 检查
        allc={**{k:v for k,v in L["cubes"].items()}, **L["distractors"]}
        degen=[]
        for k,v in allc.items():
            c,A,h=cube_obb2d(v[0],v[1],v[2])
            if min(np.linalg.norm(A[:,0]),np.linalg.norm(A[:,1]))<0.5: degen.append(k)
        close=[(a,b,round(math.dist(allc[a][:2],allc[b][:2]),3)) for a,b in itertools.combinations(allc,2) if math.dist(allc[a][:2],allc[b][:2])<0.07]
        print(f"seed{r['seed']} sel={r['selected']} sameCornerCell>=2={m['col_same_cornercell_ge2']} sameQuad>=2={m['col_same_quad_ge2']} all3quad={m['col_same_quad_all3']} inCorner={m['col_in_cornercell']:.2f} minpair={m['all_min_pair']:.3f} cl08>=3={m['cl08_ge3']} tgtEdge={m['tgt_dist_edge']:.3f} degenerateOBB={degen} pairs<7cm={close}")
    for k in ["col_same_cornercell_ge2","col_same_quad_ge2","col_same_quad_all3","col_in_cornercell","all_min_lt_0p06","all_min_lt_0p07","cl08_ge3","cl10_ge3"]:
        print(f"  mean {k} = {np.mean([m[k] for m in agg]):.3f}")
    print("  median tgt_dist_edge =", round(float(np.median([m['tgt_dist_edge'] for m in agg])),4))
