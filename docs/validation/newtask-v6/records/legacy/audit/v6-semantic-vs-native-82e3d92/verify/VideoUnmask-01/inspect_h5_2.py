import h5py
p = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/VideoUnmask_episode_0/hdf5_files/VideoUnmask_ep0_seed10600000.h5"
f = h5py.File(p, 'r')
ep = f['episode_0']
print("episode_0 keys:", list(ep.keys())[:20], "... total", len(list(ep.keys())))
# find timestep groups
tkeys = sorted([k for k in ep.keys() if k.startswith('timestep')], key=lambda x: int(x.split('_')[-1]))
print("num timesteps:", len(tkeys), tkeys[0], tkeys[-1])
t0 = ep[tkeys[0]]
def show(g, prefix=""):
    for k in g.keys():
        item = g[k]
        if isinstance(item, h5py.Group):
            print(prefix+k+"/")
            show(item, prefix+"  ")
        else:
            print(prefix+k, item.shape if hasattr(item,'shape') else '', item.dtype if hasattr(item,'dtype') else '')
show(t0)
print("--- attrs on episode ---")
for k,v in ep.attrs.items():
    print(k, ":", str(v)[:200])
