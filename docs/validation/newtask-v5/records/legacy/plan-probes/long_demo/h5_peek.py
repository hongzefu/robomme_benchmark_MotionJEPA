import h5py, sys
p = sys.argv[1]
with h5py.File(p, "r") as f:
    def show(name, obj):
        if name.count("/") <= 3 and ("timestep_0/" in name or "timestep" not in name):
            print(name, getattr(obj, "shape", ""), getattr(obj, "dtype", ""))
    f.visititems(show)
    ep = f["episode_0"]
    ks = [k for k in ep.keys()]
    print(len(ks), ks[:5], ks[-5:])
    print(dict(ep.attrs) if ep.attrs else "no attrs")
    print(dict(f.attrs) if f.attrs else "no file attrs")
