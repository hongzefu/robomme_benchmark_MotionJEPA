"""V6 规划探针：读 v5-01 六个环境各 3 局正式 h5，统计演示帧数、执行帧数与逐段帧数（按 is_subgoal_boundary 切段）。"""
import h5py, json, glob, os, collections
import numpy as np
ROOT = "artifacts/newtask-v5/v5-01/rollout/run1/episodes"
ENVS = ("PatternLock", "RouteStick", "VideoPlaceButton", "VideoPlaceOrder", "InsertPeg", "StopCube")
out = {}
for env in ENVS:
    for d in sorted(glob.glob(f"{ROOT}/{env}_episode_*")):
        p = glob.glob(f"{d}/hdf5_files/*.h5")[0]
        with h5py.File(p, "r") as f:
            gk = [k for k in f.keys() if k.startswith("episode_")][0]
            g = f[gk]
            keys = sorted([k for k in g.keys() if k.startswith("timestep_")], key=lambda s: int(s.split("_")[1]))
            n = len(keys)
            demo = np.zeros(n, bool); bound = np.zeros(n, bool); sub = []
            for i, k in enumerate(keys):
                t = g[k]
                demo[i] = bool(t["info/is_video_demo"][()])
                bound[i] = bool(t["info/is_subgoal_boundary"][()])
                s = t["info/simple_subgoal"][()]
                sub.append(s.decode() if isinstance(s, bytes) else str(s))
            goal = g["setup/task_goal"][()]
            goal = [x.decode() if isinstance(x, bytes) else str(x) for x in (goal if hasattr(goal, "__len__") and not isinstance(goal, (bytes, str)) else [goal])]
            diff = g["setup/difficulty"][()]
        cuts = np.where(bound)[0].tolist(); segs = []; s0 = 0
        for c in cuts:
            segs.append(dict(len=c - s0 + 1, demo=bool(demo[s0]), sub=sub[s0])); s0 = c + 1
        if s0 < n:
            segs.append(dict(len=n - s0, demo=bool(demo[s0]), sub=sub[s0], tail=True))
        nd = int(demo.sum())
        rec = dict(file=os.path.basename(p), total=n, demo=nd, exec=n - nd, demo_s=round(nd / 30, 2),
                   demo_segs=[(s["sub"][:60], s["len"]) for s in segs if s["demo"]],
                   exec_segs=[(s["sub"][:60], s["len"]) for s in segs if not s["demo"]],
                   goal=goal[0][:200], difficulty=str(diff))
        out[os.path.basename(d)] = rec
        print(f"== {os.path.basename(d)}: total={n} demo={nd} ({nd/30:.1f}s) exec={n-nd} n_demo_segs={len(rec['demo_segs'])} n_exec_segs={len(rec['exec_segs'])}")
        print("   goal:", rec["goal"])
        c = collections.defaultdict(list)
        for name, L in rec["demo_segs"]:
            c[name.split(" at ")[0][:40]].append(L)
        print("   demo seg by kind:", {k: (len(v), round(float(np.mean(v)), 1)) for k, v in c.items()})
        print("   exec segs:", rec["exec_segs"][:6], "..." if len(rec["exec_segs"]) > 6 else "")
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "h5_baseline.json"), "w"), indent=1, ensure_ascii=False)
