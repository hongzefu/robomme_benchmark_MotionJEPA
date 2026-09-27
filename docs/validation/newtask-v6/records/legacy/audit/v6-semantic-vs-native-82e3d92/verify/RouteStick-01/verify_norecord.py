import h5py, json, sys

def read_val(f, ts, path):
    g = f[f"episode_0/timestep_{ts}/{path}"]
    v = g[()]
    if isinstance(v, bytes):
        return v.decode('utf-8', errors='replace')
    return v

def total_timesteps(f):
    n = 0
    while f"episode_0/timestep_{n}" in f:
        n += 1
    return n

def scan(path, label, lo, hi):
    with h5py.File(path, 'r') as f:
        n = total_timesteps(f)
        print(f"=== {label} ===  path={path}")
        print(f"  total_timesteps={n}")
        # print last 12 frames' simple_subgoal_online + grounded_subgoal_online
        start = max(0, n-12)
        for t in range(start, n):
            s_on = read_val(f, t, "info/simple_subgoal_online")
            g_on = read_val(f, t, "info/grounded_subgoal_online")
            print(f"    t={t}: simple_subgoal_online={s_on!r} grounded_subgoal_online={g_on!r}")
        # verify claimed range
        print(f"  --- claimed NO RECORD range [{lo},{hi}] ---")
        for t in range(lo, hi+1):
            s_on = read_val(f, t, "info/simple_subgoal_online")
            print(f"    t={t}: simple_subgoal_online={s_on!r}")
        # check one frame before range
        if lo-1 >= 0:
            t=lo-1
            s_on = read_val(f, t, "info/simple_subgoal_online")
            print(f"    t={t} (one before claimed range): simple_subgoal_online={s_on!r}")

cases = [
    ("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/RouteStick_episode_0/hdf5_files/RouteStick_ep0_seed16000.h5", "native easy ep0", 94, 99),
    ("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/RouteStick_episode_3/hdf5_files/RouteStick_ep3_seed16300.h5", "native hard ep3", 244, 249),
]
for p, label, lo, hi in cases:
    scan(p, label, lo, hi)
