import h5py, json

cases = [
    ("xhard2", 6, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/PickHighlight_episode_6/hdf5_files/PickHighlight_ep6_seed11200600.h5", (480,585)),
    ("xhard3", 3, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard3/rollout/run1/episodes/PickHighlight_episode_3/hdf5_files/PickHighlight_ep3_seed13200300.h5", (701,820)),
    ("xhard4", 0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickHighlight_episode_0/hdf5_files/PickHighlight_ep0_seed7200000.h5", (785,908)),
]

for tier, ep, h5path, (t0,t1) in cases:
    f = h5py.File(h5path, 'r')
    epgrp = f[list(f.keys())[0]]
    print("====", tier, "ep", ep, "range", t0, t1)
    for t in [t0-2, t0-1, t0, t0+1, t0+5, t0+20, t1-1, t1]:
        if t < 0: continue
        try:
            g = epgrp[f'timestep_{t}/info']
        except KeyError:
            print(f'  t={t}: MISSING')
            continue
        s = g['simple_subgoal'][()].decode()
        gs = g['grounded_subgoal'][()].decode()
        go = g['grounded_subgoal_online'][()].decode()
        bnd = g['is_subgoal_boundary'][()] if 'is_subgoal_boundary' in g else None
        print(f'  t={t} boundary={bnd} simple={s!r}')
        print(f'       grounded={gs!r}')
        print(f'       online={go!r}')
    f.close()
