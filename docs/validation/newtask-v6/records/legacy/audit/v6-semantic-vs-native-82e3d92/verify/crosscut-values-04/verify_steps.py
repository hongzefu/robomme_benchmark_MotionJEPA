"""独立复核 crosscut-values-04：直接读取 HDF5，不依赖 measured.json。
只读，不导入仿真源码。"""
import h5py

def check(path, ep):
    with h5py.File(path, "r") as f:
        g = f[f"episode_{ep}"]
        keys = sorted((k for k in g if k.startswith("timestep_")), key=lambda k: int(k.split("_")[1]))
        n_demo = sum(1 for k in keys if bool(g[k]["info/is_video_demo"][()]))
        first_completed = None
        for k in keys:
            if bool(g[k]["info/is_completed"][()]):
                first_completed = int(k.split("_")[1])
                break
        return len(keys), n_demo, first_completed

cases = [
    ("PickXtimes xhard2 ep0", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/PickXtimes_episode_0/hdf5_files/PickXtimes_ep0_seed10100000.h5", 0),
    ("PickHighlight xhard4 ep0", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickHighlight_episode_0/hdf5_files/PickHighlight_ep0_seed7200000.h5", 0),
    ("PickHighlight xhard4 ep3", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickHighlight_episode_3/hdf5_files/PickHighlight_ep3_seed7200300.h5", 3),
    ("PickHighlight xhard4 ep6", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickHighlight_episode_6/hdf5_files/PickHighlight_ep6_seed7200600.h5", 6),
]

for name, path, ep in cases:
    n_steps, n_demo, first_completed = check(path, ep)
    exec_to_completion = first_completed - n_demo if first_completed is not None else None
    print(f"{name}: n_steps={n_steps} n_demo={n_demo} first_completed_t={first_completed} exec_steps_to_completion={exec_to_completion}")
