"""用离线螺旋模型预测 PatternLock 10 条 V4 候选的演示帧数，并与 3 条实跑 h5 对拍；RouteStick 用 L×50 公式。"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screw_model import make_planner, path_frames
H5 = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "h5_segments.json")))
rows = [json.loads(l) for l in open("scripts/configs/newtask-v4/v4-01/specs.jsonl")][1:]
p = make_planner()
print("PatternLock (model: demo = sum of per-segment screw1+screw2 frames)")
res = []
for r in rows:
    if r["task"] != "PatternLock":
        continue
    nodes = r["spec"]["actions"]["path_nodes"]
    first, segs = path_frames(p, nodes, 5, 5)
    pred = sum(segs)
    obs = H5.get(f"PatternLock_{r['episode']}", {}).get("demo")
    res.append((r["episode"], len(nodes), pred))
    print(f"  ep{r['episode']} sel={r['selected']} nodes={len(nodes)} segs={len(segs)} pred_demo={pred} ({pred/30:.2f}s) "
          f"fps/seg={pred/len(segs):.1f} min={min(segs)} max={max(segs)} observed={obs}"
          + (f" err={pred-obs:+d} ({(pred-obs)/obs*100:+.1f}%)" if obs else ""))
print("RouteStick (demo = L*50, exec = L*50)")
for r in rows:
    if r["task"] != "RouteStick":
        continue
    L = r["spec"]["objects"]["L"]
    obs = H5.get(f"RouteStick_{r['episode']}", {}).get("demo")
    print(f"  ep{r['episode']} sel={r['selected']} L={L} demo={L*50} ({L*50/30:.2f}s) observed={obs}")
