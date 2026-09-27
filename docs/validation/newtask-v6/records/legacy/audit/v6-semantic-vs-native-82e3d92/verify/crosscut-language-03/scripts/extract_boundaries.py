import h5py, json, numpy as np, sys

path = sys.argv[1] if len(sys.argv)>1 else "artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/VideoRepick_episode_3/hdf5_files/VideoRepick_ep3_seed6900300.h5"
epname = sys.argv[2] if len(sys.argv)>2 else "episode_3"

with h5py.File(path, "r") as f:
    ep = f[epname]
    ts_keys = [k for k in ep.keys() if k.startswith("timestep_")]
    idxs = sorted(int(k.split("_")[1]) for k in ts_keys)
    n = len(idxs)
    print("total timesteps:", n, "range", idxs[0], idxs[-1])

    demo_flags = []
    boundary_flags = []
    simple_subgoals = []
    for i in idxs:
        g = ep[f"timestep_{i}"]
        demo_flags.append(bool(g["info/is_video_demo"][()]))
        boundary_flags.append(bool(g["info/is_subgoal_boundary"][()]))
        sg = g["info/simple_subgoal"][()]
        if isinstance(sg, bytes): sg = sg.decode()
        simple_subgoals.append(str(sg))

    demo_flags = np.array(demo_flags)
    boundary_flags = np.array(boundary_flags)

    demo_idx = [idxs[i] for i in range(n) if demo_flags[i]]
    print("demo steps count:", len(demo_idx), "first", demo_idx[0] if demo_idx else None, "last", demo_idx[-1] if demo_idx else None)

    # boundaries within demo region
    boundary_idx_all = [idxs[i] for i in range(n) if boundary_flags[i]]
    print("ALL boundary steps (n=%d):" % len(boundary_idx_all), boundary_idx_all)

    print()
    print("simple_subgoal at each boundary (idx, subgoal, is_demo):")
    for i in range(n):
        if boundary_flags[i]:
            print(idxs[i], repr(simple_subgoals[i]), "demo" if demo_flags[i] else "notdemo")

    # unique subgoal transitions (subgoal text changes)
    print()
    print("subgoal text change points (idx -> new subgoal):")
    prev = None
    for i in range(n):
        if simple_subgoals[i] != prev:
            print(idxs[i], repr(simple_subgoals[i]))
            prev = simple_subgoals[i]
