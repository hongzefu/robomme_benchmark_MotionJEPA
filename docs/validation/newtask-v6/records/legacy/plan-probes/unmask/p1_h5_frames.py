"""V6 规划探针 P1：读 v5-01 四个 Unmask 环境 12 条 h5，统计总帧数、演示帧数、各子目标段帧数（只读）。"""
import glob, json, sys
import h5py
import numpy as np

ROOT = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/v5-01/rollout/run1/episodes"
out = []
for task in ("VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"):
    for path in sorted(glob.glob(f"{ROOT}/{task}_episode_*/hdf5_files/*.h5")):
        with h5py.File(path, "r") as f:
            ep = f[[k for k in f if k.startswith("episode_")][0]]
            ts = sorted([k for k in ep if k.startswith("timestep_")], key=lambda s: int(s.split("_")[1]))
            demo = 0
            segs = []
            cur, n = None, 0
            for k in ts:
                info = ep[k]["info"]
                d = bool(info["is_video_demo"][()])
                demo += d
                sg = info["simple_subgoal"][()]
                sg = sg.decode() if isinstance(sg, bytes) else str(sg)
                if sg != cur:
                    if cur is not None:
                        segs.append((cur, n))
                    cur, n = sg, 0
                n += 1
            segs.append((cur, n))
            rec = dict(task=task, file=path.split("/")[-1], total=len(ts), demo=demo, nondemo=len(ts) - demo, segs=segs)
            out.append(rec)
            print(f"{task} {rec['file']} total={rec['total']} demo={demo} exec={rec['nondemo']}")
            for s, n in segs:
                print(f"    {n:5d}  {s[:90]}")
json.dump(out, open("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/plan-probes/unmask/p1_h5_frames.json", "w"), ensure_ascii=False, indent=1)
