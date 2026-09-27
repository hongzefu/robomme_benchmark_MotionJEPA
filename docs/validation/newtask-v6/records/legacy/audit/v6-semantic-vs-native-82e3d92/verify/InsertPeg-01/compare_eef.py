#!/usr/bin/env python3
"""独立核对: demo段最后一步 vs exec段最后一步的 eef_state 位置差(欧氏距离,前3维视为xyz)。"""
import h5py
import numpy as np

# (tag, path, demo_end_ts, exec_end_ts) 取自 inspect_h5.py 输出的段边界(最后一个 timestep index)
cases = [
    ("easy_ep0",  "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/InsertPeg_episode_0/hdf5_files/InsertPeg_ep0_seed13000.h5", 237, 462),
    ("hard_ep11", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/InsertPeg_episode_11/hdf5_files/InsertPeg_ep11_seed14100.h5", 246, 492),
    ("xhard4_ep6","/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/InsertPeg_episode_6/hdf5_files/InsertPeg_ep6_seed7300600.h5", 218, 434),
    ("xhard4_ep2","/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/InsertPeg_episode_2/hdf5_files/InsertPeg_ep2_seed7300200.h5", 231, 451),
    ("xhard4_ep4","/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/InsertPeg_episode_4/hdf5_files/InsertPeg_ep4_seed7300400.h5", 213, 415),
]

for tag, path, demo_end, exec_end in cases:
    f = h5py.File(path, "r")
    ep_key = [k for k in f.keys() if k.startswith("episode_")][0]
    g = f[ep_key]
    demo_eef = g[f"timestep_{demo_end}"]["obs"]["eef_state"][()]
    exec_eef = g[f"timestep_{exec_end}"]["obs"]["eef_state"][()]
    diff = demo_eef[:3] - exec_eef[:3]
    dist = float(np.linalg.norm(diff))
    print(f"{tag}: demo_eef(xyz)={demo_eef[:3]} exec_eef(xyz)={exec_eef[:3]} dist={dist:.5f} m")
    f.close()
