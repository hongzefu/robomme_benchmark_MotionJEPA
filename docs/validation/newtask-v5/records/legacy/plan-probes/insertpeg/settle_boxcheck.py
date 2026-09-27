"""Recompute the layouts used by settle_test (v4 specs and v5 injected) and report peg-box footprint overlap."""
import sys, json
import numpy as np
D = __file__.rsplit('/', 1)[0]
sys.path.insert(0, D)
import peggeom as G
from settle_test import v5_layout
REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
lines = [json.loads(l) for l in open(f"{REPO}/scripts/configs/newtask-v4/v4-01/specs.jsonl")]
rows = {r["episode"]: r for r in lines[1:] if r["task"] == "InsertPeg"}
rng = np.random.default_rng(20260924)
for mode in ("v4", "v5"):
    if mode == "v5":
        rng = np.random.default_rng(20260924)
    for ep in range(10):
        init = rows[ep]["spec"]["initializations"]["1"]
        bxy = np.array(init["box_jitter"], dtype=np.float32); byaw = init["box_yaw"]
        pegs = init["pegs"] if mode == "v4" else v5_layout(rng, bxy, byaw, 0.02)
        br = G.box_rect(bxy.astype(float), np.float64(byaw))
        info = []
        for i in range(4):
            root = np.array(pegs[str(i)][0]); yaw = np.float64(pegs[str(i)][1])
            pr = G.peg_rect(root, yaw)
            d = float(G.rect_dist(pr, br))
            # penetration depth proxy: overlap -> compute how far root is from box centre
            info.append(f"p{i}:{'OVL' if G.rect_intersect(pr, br) else f'{d:.3f}'}")
        print(mode, ep, " ".join(info))
