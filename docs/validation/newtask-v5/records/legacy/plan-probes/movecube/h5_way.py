import h5py, sys, glob, json, re
D = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube/demo_out/hdf5_files"
for p in sorted(glob.glob(D + "/*.h5")):
    with h5py.File(p, "r") as f:
        ep = f[list(f.keys())[0]]
        keys = sorted(ep.keys(), key=lambda k: int(k.split('_')[-1]) if k.startswith('timestep_') else -1)
        ts = [k for k in keys if k.startswith("timestep_")]
        segs = set(); demo = 0
        for k in ts:
            info = ep[k]["info"]
            for name in ("simple_subgoal_online", "grounded_subgoal_online", "subgoal", "simple_subgoal"):
                if name in info:
                    v = info[name][()]
                    v = v.decode() if isinstance(v, bytes) else str(v)
                    segs.add(v[:60])
            if "is_video_demo" in info and bool(info["is_video_demo"][()]): demo += 1
        nonts = [k for k in ep.keys() if not k.startswith("timestep_")]
        print("H5WAY", p.split("/")[-1], "timesteps", len(ts), "demo_frames", demo, "non_ts_keys", nonts[:6], "subgoals", sorted(segs)[:8])
