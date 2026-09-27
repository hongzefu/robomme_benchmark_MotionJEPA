import h5py, json

def top_group(f):
    return list(f.keys())[0]

def read_val(f, grp, ts, path):
    g = f[f"{grp}/timestep_{ts}/{path}"]
    v = g[()]
    if isinstance(v, bytes):
        return v.decode('utf-8', errors='replace')
    return v

def total_timesteps(f, grp):
    n = 0
    while f"{grp}/timestep_{n}" in f:
        n += 1
    return n

def scan(path, label, lo, hi):
    with h5py.File(path, 'r') as f:
        grp = top_group(f)
        n = total_timesteps(f, grp)
        print(f"=== {label} ===  path={path}  group={grp}")
        print(f"  total_timesteps={n}  (expect hi+1={hi+1})")
        for t in range(lo, hi+1):
            s_on = read_val(f, grp, t, "info/simple_subgoal_online")
            print(f"    t={t}: simple_subgoal_online={s_on!r}")
        if lo-1 >= 0:
            t=lo-1
            s_on = read_val(f, grp, t, "info/simple_subgoal_online")
            print(f"    t={t} (one before): simple_subgoal_online={s_on!r}")
        if lo-2 >= 0:
            t=lo-2
            s_on = read_val(f, grp, t, "info/simple_subgoal_online")
            print(f"    t={t} (two before): simple_subgoal_online={s_on!r}")

cases = [
    ("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/RouteStick_episode_3/hdf5_files/RouteStick_ep3_seed16300.h5", "native hard ep3", 244, 249),
    ("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/RouteStick_episode_10/hdf5_files/RouteStick_ep10_seed17000.h5", "native medium ep10", 194, 199),
]
for p, label, lo, hi in cases:
    scan(p, label, lo, hi)
