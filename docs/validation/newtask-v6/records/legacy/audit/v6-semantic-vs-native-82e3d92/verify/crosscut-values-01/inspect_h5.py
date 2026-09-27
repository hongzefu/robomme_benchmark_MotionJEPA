import h5py, sys, json
h5 = sys.argv[1]
with h5py.File(h5, 'r') as f:
    g = f[list(f.keys())[0]]
    print("top group:", list(f.keys()))
    print("group attrs:", dict(g.attrs))
    ts_keys = sorted([k for k in g.keys() if k.startswith('timestep_')], key=lambda x: int(x.split('_')[1]))
    print("n_timesteps:", len(ts_keys))
    # print first timestep structure
    first = g[ts_keys[0]]
    def show(grp, prefix=''):
        for k in grp.keys():
            item = grp[k]
            if isinstance(item, h5py.Group):
                show(item, prefix+k+'/')
            else:
                print(prefix+k, item.shape if hasattr(item,'shape') else '', item.dtype if hasattr(item,'dtype') else '')
    show(first)
    print("first attrs:", dict(first.attrs))
