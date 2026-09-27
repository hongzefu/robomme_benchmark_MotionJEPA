import h5py

def top_group(f):
    return list(f.keys())[0]

def read_val(f, grp, ts, path):
    v = f[f"{grp}/timestep_{ts}/{path}"][()]
    return v.decode('utf-8', errors='replace') if isinstance(v, bytes) else v

def total_timesteps(f, grp):
    n = 0
    while f"{grp}/timestep_{n}" in f:
        n += 1
    return n

p = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/RouteStick_episode_0/hdf5_files/RouteStick_ep0_seed9600000.h5"
with h5py.File(p, 'r') as f:
    grp = top_group(f)
    n = total_timesteps(f, grp)
    print("group", grp, "total_timesteps", n)
    for t in range(489, 500):
        try:
            s_on = read_val(f, grp, t, "info/simple_subgoal_online")
            g_on = read_val(f, grp, t, "info/grounded_subgoal_online")
            print(f"  t={t}: simple_subgoal_online={s_on!r} grounded_subgoal_online={g_on!r}")
        except KeyError:
            print(f"  t={t}: MISSING")
