import h5py, sys, json
p = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/VideoUnmask_episode_0/hdf5_files/VideoUnmask_ep0_seed10600000.h5"
f = h5py.File(p, 'r')
def visit(name, obj):
    pass
keys = list(f.keys())
print("top-level keys count:", len(keys))
print("sample keys:", keys[:5], keys[-5:])
