"""For each V4 InsertPeg rollout episode: number of frames, demo frames, last subgoal reached."""
import glob, h5py, re
BASE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes"
for k in range(10):
    fs = glob.glob(f"{BASE}/InsertPeg_episode_{k}/hdf5_files/*.h5")
    if not fs:
        print(k, "no h5"); continue
    with h5py.File(fs[0], "r") as f:
        ep = f[list(f.keys())[0]]
        ts = sorted([int(t.split("_")[1]) for t in ep.keys() if t.startswith("timestep_")])
        demo = 0; subs = []
        for t in ts:
            g = ep[f"timestep_{t}"]
            if bool(g["info/is_video_demo"][()]):
                demo += 1
            s = g["info/simple_subgoal"][()]
            s = s.decode() if isinstance(s, bytes) else str(s)
            if not subs or subs[-1][0] != s:
                subs.append((s, t, bool(g["info/is_video_demo"][()])))
        print(f"episode={k} frames={len(ts)} demo_frames={demo}")
        for s, t, d in subs:
            print(f"    t={t:5d} demo={d} subgoal={s}")
