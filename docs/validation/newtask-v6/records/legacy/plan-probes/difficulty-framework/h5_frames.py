"""只读探针：统计 v5-01 48 局正式局 h5 的 timestep 数、演示帧数，并附规格里的关键 objects 字段。"""
import glob, json, re, sys
import h5py
specs = {}
for line in open("scripts/configs/newtask-v5/v5-01/specs.jsonl"):
    r = json.loads(line)
    if r.get("record") == "spec":
        specs[(r["task"], r["episode"])] = r["spec"]
rows = []
for path in sorted(glob.glob("artifacts/newtask-v5/v5-01/rollout/run1/episodes/*/hdf5_files/*.h5")):
    m = re.search(r"/([A-Za-z]+)_episode_(\d+)/hdf5_files/.*seed(\d+)", path)
    task, ep, seed = m.group(1), int(m.group(2)), int(m.group(3))
    with h5py.File(path, "r") as f:
        g = f[list(f.keys())[0]]
        steps = [k for k in g.keys() if k.startswith("timestep_")]
        demo = sum(bool(g[k]["info"]["is_video_demo"][()]) for k in steps)
    obj = specs.get((task, ep), {}).get("objects", {})
    rows.append({"task": task, "ep": ep, "seed": seed, "timesteps": len(steps), "demo": demo,
                 "objects": {k: v for k, v in obj.items() if not isinstance(v, (list, dict)) or len(json.dumps(v)) < 120}})
json.dump(rows, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
for r in rows:
    print(r["task"], r["ep"], r["seed"], "T=", r["timesteps"], "demo=", r["demo"], json.dumps(r["objects"], ensure_ascii=False)[:300])
