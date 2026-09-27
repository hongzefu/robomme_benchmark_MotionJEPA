import h5py, sys, json
path = sys.argv[1]
with h5py.File(path, "r") as f:
    keys_seen = []
    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and len(keys_seen) < 40:
            keys_seen.append(name)
    f.visititems(visit)
    print("SAMPLE KEYS:", keys_seen[:40])
    # find simple_subgoal / grounded_subgoal per-step group
    steps = sorted([k for k in f.keys() if k.isdigit()], key=int) if all(k.isdigit() for k in list(f.keys())[:3]) else None
    print("top-level keys:", list(f.keys())[:10], "n_top=", len(f.keys()))
