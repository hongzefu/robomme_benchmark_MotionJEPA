import h5py
p = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/VideoUnmask_episode_1/hdf5_files/VideoUnmask_ep1_seed6100.h5"
f = h5py.File(p, 'r')
print(list(f.keys()))
