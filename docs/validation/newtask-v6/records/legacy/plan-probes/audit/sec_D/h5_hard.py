"""只读：原始数据集 data-0306 的 hard 局逐局统计（与 h5_stats.py 同口径）。"""
import json, sys, h5py
TASKS = sys.argv[1].split(","); out = sys.argv[2]
rows = []
for task in TASKS:
    meta = json.load(open(f"/data/hongzefu/data-0306/record_dataset_{task}_metadata.json"))
    hard = [r for r in meta["records"] if r["difficulty"] == "hard"]
    with h5py.File(f"/data/hongzefu/data-0306/record_dataset_{task}.h5", "r") as f:
        for r in hard:
            g = f[f"episode_{r['episode']}"]
            steps = sorted([k for k in g.keys() if k.startswith("timestep_")], key=lambda s: int(s.split("_")[1]))
            demo = []; sub = []
            for k in steps:
                inf = g[k]["info"]
                demo.append(bool(inf["is_video_demo"][()]))
                s = inf["simple_subgoal"][()] if "simple_subgoal" in inf else b""
                sub.append(s.decode() if isinstance(s, bytes) else str(s))
            segs = []; cur = None
            for d, s in zip(demo, sub):
                if cur is not None and cur[0] == (d, s): cur[1] += 1
                else:
                    if cur is not None: segs.append((cur[0][0], cur[0][1], cur[1]))
                    cur = [(d, s), 1]
            if cur is not None: segs.append((cur[0][0], cur[0][1], cur[1]))
            rows.append({"task": task, "ep": r["episode"], "seed": r["seed"], "T": len(steps),
                         "demo": sum(demo), "exec": len(steps) - sum(demo), "segs": segs})
            print(task, r["episode"], "T=", len(steps), "demo=", sum(demo), flush=True)
json.dump(rows, open(out, "w"), ensure_ascii=False)
print("HARD_DONE", len(rows), flush=True)
