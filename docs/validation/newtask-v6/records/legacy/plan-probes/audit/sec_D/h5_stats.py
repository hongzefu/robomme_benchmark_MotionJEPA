"""只读：逐局统计 h5 的总步数、演示帧数、执行步数、演示段内子目标段长度。"""
import glob, json, re, sys
import h5py
pat = sys.argv[1]; out = sys.argv[2]
rows = []
for path in sorted(glob.glob(pat, recursive=True)):
    with h5py.File(path, "r") as f:
        for ek in f.keys():
            g = f[ek]
            steps = sorted([k for k in g.keys() if k.startswith("timestep_")], key=lambda s: int(s.split("_")[1]))
            demo = []; bnd = []; sub = []
            for k in steps:
                inf = g[k]["info"]
                demo.append(bool(inf["is_video_demo"][()]))
                bnd.append(bool(inf["is_subgoal_boundary"][()]) if "is_subgoal_boundary" in inf else False)
                s = inf["simple_subgoal"][()] if "simple_subgoal" in inf else b""
                sub.append(s.decode() if isinstance(s, bytes) else str(s))
            # 按 simple_subgoal 变化切段（分 demo/exec）
            segs = []
            cur = None
            for d, s in zip(demo, sub):
                key = (d, s)
                if cur is not None and cur[0] == key:
                    cur[1] += 1
                else:
                    if cur is not None: segs.append((cur[0][0], cur[0][1], cur[1]))
                    cur = [key, 1]
            if cur is not None: segs.append((cur[0][0], cur[0][1], cur[1]))
            m = re.search(r"([A-Za-z]+)_ep(\d+)_seed(\d+)", path)
            rows.append({"path": path, "episode_key": ek, "task": m.group(1) if m else None,
                         "ep": int(m.group(2)) if m else None, "seed": int(m.group(3)) if m else None,
                         "T": len(steps), "demo": sum(demo), "exec": len(steps) - sum(demo),
                         "segs": segs})
json.dump(rows, open(out, "w"), ensure_ascii=False)
for r in rows:
    print(r["task"], r["ep"], "T=", r["T"], "demo=", r["demo"], "exec=", r["exec"], "nseg=", len(r["segs"]))
