"""V4 实跑 3 局 PatternLock 演示段逐段帧数按方向分类（直行左右 / 直行前后 / 斜向），并按远端行（x=0.1）标注。"""
import json, collections, numpy as np, os
H = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "h5_segments.json")))
specs = {r["episode"]: r["spec"]["actions"]["path_nodes"] for r in map(json.loads, open("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/configs/newtask-v4/v4-01/specs.jsonl").readlines()[1:]) if r["task"] == "PatternLock"}
cat = collections.defaultdict(list); far = collections.defaultdict(list)
for ep in (0, 3, 6):
    rec = H[f"PatternLock_{ep}"]; lens = rec["demo_seg_lens"][1:]; names = rec["demo_seg_names"][1:]
    nodes = specs[ep]
    assert len(lens) == len(nodes) - 1, (len(lens), len(nodes))
    for i, (l, nm) in enumerate(zip(lens, names)):
        d = nm.replace("move ", "")
        k = "diag" if "-" in d else ("left/right" if d in ("left", "right") else "forward/backward")
        cat[k].append(l)
        a, b = nodes[i], nodes[i + 1]
        if max(a // 5, b // 5) == 4: far[k].append(l)
for k, v in cat.items():
    print(f"{k:17s} n={len(v):2d} mean={np.mean(v):.1f} min={min(v)} max={max(v)} | touching far row x=0.1: n={len(far[k])} mean={np.mean(far[k]) if far[k] else float('nan'):.1f}")
allv = sum(cat.values(), []); print(f"all n={len(allv)} mean={np.mean(allv):.2f} min={min(allv)} max={max(allv)}")
