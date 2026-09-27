import h5py, json, numpy as np, sys

path = "artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/VideoRepick_episode_3/hdf5_files/VideoRepick_ep3_seed6900300.h5"

with h5py.File(path, "r") as f:
    keys_top = list(f.keys())
    print("TOP KEYS:", keys_top)
    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.count("/") <= 2:
            pass
    f.visititems(lambda n,o: print(n, o.shape if isinstance(o,h5py.Dataset) else "GROUP") if n.count("/")<=1 else None)
