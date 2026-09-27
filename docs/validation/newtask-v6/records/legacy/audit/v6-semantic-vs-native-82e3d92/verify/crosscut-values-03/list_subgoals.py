import h5py, sys

path = sys.argv[1]
with h5py.File(path, "r") as f:
    ep = list(f.keys())[0]
    grp = f[ep]
    goal = grp["setup/task_goal"][()]
    print("task_goal[0]:", goal[0].decode() if isinstance(goal[0], bytes) else goal[0])
    ts_keys = sorted([k for k in grp.keys() if k.startswith("timestep_")],
                      key=lambda s: int(s.split("_")[1]))
    n = len(ts_keys)
    print("n_timesteps:", n)
    prev = None
    boundaries = []
    for k in ts_keys:
        sg = grp[f"{k}/info/simple_subgoal"][()]
        sg = sg.decode() if isinstance(sg, bytes) else sg
        boundary = grp[f"{k}/info/is_subgoal_boundary"][()]
        if sg != prev:
            boundaries.append((int(k.split("_")[1]), sg))
            prev = sg
    print("n_unique_subgoal_segments:", len(boundaries))
    for t, sg in boundaries:
        if "time" in sg:
            print(t, "|", sg)
