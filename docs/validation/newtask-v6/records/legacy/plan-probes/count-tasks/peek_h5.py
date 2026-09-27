# 只读：打印一个 h5 的时间步数与 simple_subgoal 分段（调试用）
import h5py, sys
p = sys.argv[1]
with h5py.File(p, "r") as f:
    for ek in f.keys():
        ep = f[ek]
        ts = sorted([k for k in ep.keys() if k.startswith("timestep_")], key=lambda s: int(s.split("_")[1]))
        print(ek, "timesteps", len(ts), "difficulty", ep["setup/difficulty"][()], "goal", ep["setup/task_goal"][()])
        prev = None; start = 0
        for i, k in enumerate(ts):
            sg = ep[k]["info/simple_subgoal"][()]
            demo = bool(ep[k]["info/is_video_demo"][()])
            key = (sg, demo)
            if key != prev:
                if prev is not None:
                    print(f"  [{start:5d},{i:5d}) len={i-start:4d} demo={prev[1]} {prev[0]}")
                prev = key; start = i
        print(f"  [{start:5d},{len(ts):5d}) len={len(ts)-start:4d} demo={prev[1]} {prev[0]}")
