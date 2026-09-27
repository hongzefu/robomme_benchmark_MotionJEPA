import h5py, sys

p = sys.argv[1]
with h5py.File(p, 'r') as f:
    ep = list(f.keys())[0]
    g = f[ep]
    print("EP GROUP KEYS:", list(g.keys()))
    print("ATTRS:", dict(g.attrs))
    def cb(name, obj):
        if isinstance(obj, h5py.Group):
            pass
        # print top 3 levels only
        depth = name.count('/')
        if depth <= 2:
            print(depth, name, type(obj).__name__, getattr(obj, 'shape', ''))
    g.visititems(cb)
