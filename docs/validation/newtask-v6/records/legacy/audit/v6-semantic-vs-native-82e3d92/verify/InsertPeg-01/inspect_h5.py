#!/usr/bin/env python3
"""只读检查 InsertPeg h5 里的 simple_subgoal 文本，独立复现 InsertPeg-01 发现。"""
import re
import h5py
import numpy as np

files = {
    "easy_ep0": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/InsertPeg_episode_0/hdf5_files/InsertPeg_ep0_seed13000.h5",
    "medium_ep_lookup": None,
    "hard_ep11": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/InsertPeg_episode_11/hdf5_files/InsertPeg_ep11_seed14100.h5",
    "xhard4_ep6": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/InsertPeg_episode_6/hdf5_files/InsertPeg_ep6_seed7300600.h5",
    "xhard4_ep2": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/InsertPeg_episode_2/hdf5_files/InsertPeg_ep2_seed7300200.h5",
    "xhard4_ep4": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/InsertPeg_episode_4/hdf5_files/InsertPeg_ep4_seed7300400.h5",
}


def decode(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def process(tag, path):
    print(f"\n===== {tag} : {path} =====")
    f = h5py.File(path, "r")
    ep_key = [k for k in f.keys() if k.startswith("episode_")][0]
    g = f[ep_key]
    ts_keys = [k for k in g.keys() if k.startswith("timestep_")]
    ts_keys.sort(key=lambda k: int(k.split("_", 1)[1]))
    n = len(ts_keys)
    print("n_timesteps:", n)

    boundaries = []
    prev_text = None
    prev_demo = None
    seg_start = None
    for i, tk in enumerate(ts_keys):
        info = g[tk]["info"]
        text = decode(info["simple_subgoal"][()]) if "simple_subgoal" in info else None
        is_demo = decode(info["is_video_demo"][()]) if "is_video_demo" in info else None
        if text != prev_text:
            if prev_text is not None:
                boundaries.append((seg_start, i - 1, prev_text, prev_demo))
            seg_start = i
            prev_text = text
            prev_demo = is_demo
    if prev_text is not None:
        boundaries.append((seg_start, n - 1, prev_text, prev_demo))

    for (s, e, text, demo) in boundaries:
        print(f"  timesteps {s}-{e} is_video_demo={demo}: {text!r}")
    f.close()


for tag, path in files.items():
    if path is None:
        continue
    process(tag, path)
