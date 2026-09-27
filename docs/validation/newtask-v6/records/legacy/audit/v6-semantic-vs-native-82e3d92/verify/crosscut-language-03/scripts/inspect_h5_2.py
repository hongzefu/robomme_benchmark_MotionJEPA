import h5py, json, numpy as np

path = "artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/VideoRepick_episode_3/hdf5_files/VideoRepick_ep3_seed6900300.h5"

with h5py.File(path, "r") as f:
    ep = f["episode_3"]
    print("setup keys:", list(ep["setup"].keys()) if "setup" in ep else None)
    print("attrs of episode_3:", dict(ep.attrs))
    print("attrs of root:", dict(f.attrs))
    ts0 = ep["timestep_0"]
    def show(g, prefix=""):
        for k in g.keys():
            item = g[k]
            if isinstance(item, h5py.Group):
                print(prefix+k+"/  (group)")
                show(item, prefix+"  ")
            else:
                print(prefix+k, item.shape, item.dtype)
    show(ts0)
    # count total timesteps
    n_ts = sum(1 for k in ep.keys() if k.startswith("timestep_"))
    print("N timesteps:", n_ts)
