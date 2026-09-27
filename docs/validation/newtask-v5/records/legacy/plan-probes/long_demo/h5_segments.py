"""逐局统计 V4 run1 的 PatternLock / RouteStick：演示帧数、执行帧数、按 is_subgoal_boundary 切出的逐段帧数与 TCP 位移。"""
import h5py, json, glob, os
import numpy as np
ROOT = "artifacts/newtask-v4/v4-01/rollout/run1/episodes"
out = {}
for env in ("PatternLock", "RouteStick"):
    for ep in (0, 3, 6):
        p = glob.glob(f"{ROOT}/{env}_episode_{ep}/hdf5_files/*.h5")[0]
        with h5py.File(p, "r") as f:
            g = f[f"episode_{ep}"]
            n = len([k for k in g.keys() if k.startswith("timestep_")])
            demo = np.zeros(n, bool); sub = []; bound = np.zeros(n, bool); comp = np.zeros(n, bool)
            eef = np.zeros((n, 6), np.float32)
            for i in range(n):
                t = g[f"timestep_{i}"]
                demo[i] = bool(t["info/is_video_demo"][()])
                s = t["info/simple_subgoal"][()]
                sub.append(s.decode() if isinstance(s, bytes) else str(s))
                bound[i] = bool(t["info/is_subgoal_boundary"][()])
                comp[i] = bool(t["info/is_completed"][()])
                eef[i] = t["obs/eef_state"][()]
            goal = g["setup/task_goal"][()]
            diff = g["setup/difficulty"][()]
        nd = int(demo.sum())
        first_nondemo = int(np.argmin(demo)) if not demo.all() else n
        prefix = bool(demo[:first_nondemo].all() and not demo[first_nondemo:].any())
        # 段切分：boundary=True 的帧作为一段的最后一帧
        cuts = np.where(bound)[0].tolist()
        segs = []; s0 = 0
        for c in cuts:
            segs.append(dict(start=s0, end=c, len=c - s0 + 1, demo=bool(demo[s0]), sub=sub[s0],
                             dxy=float(np.linalg.norm(eef[c, :2] - eef[s0, :2]))))
            s0 = c + 1
        if s0 < n:
            segs.append(dict(start=s0, end=n - 1, len=n - s0, demo=bool(demo[s0]), sub=sub[s0], dxy=0.0, tail=True))
        dsegs = [s for s in segs if s["demo"]]; esegs = [s for s in segs if not s["demo"]]
        rec = dict(total=n, demo=nd, exec=n - nd, demo_s=round(nd / 30, 2), demo_prefix=prefix, completed_last=bool(comp[-1]),
                   n_demo_segs=len(dsegs), n_exec_segs=len(esegs), demo_seg_lens=[s["len"] for s in dsegs],
                   exec_seg_lens=[s["len"] for s in esegs], demo_seg_names=[s["sub"] for s in dsegs], difficulty=str(diff))
        out[f"{env}_{ep}"] = rec
        print(f"== {env} ep{ep}: total={n} demo={nd} ({nd/30:.2f}s) exec={n-nd} prefix={prefix} completed_last={comp[-1]} "
              f"demo_segs={len(dsegs)} exec_segs={len(esegs)} diff={diff}")
        print("   demo lens:", [s["len"] for s in dsegs])
        print("   exec lens:", [s["len"] for s in esegs])
        print("   demo names:", [s["sub"][:40] for s in dsegs][:4], "...")
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "h5_segments.json"), "w"), indent=1, default=str)
