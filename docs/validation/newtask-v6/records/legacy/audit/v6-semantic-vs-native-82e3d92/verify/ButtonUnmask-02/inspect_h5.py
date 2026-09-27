import h5py, sys, json

def visit(f, path=""):
    keys = []
    def cb(name, obj):
        keys.append(name)
    f.visititems(cb)
    return keys

p = sys.argv[1]
with h5py.File(p, 'r') as f:
    print("TOP KEYS:", list(f.keys()))
    print("ATTRS:", dict(f.attrs))
    ks = visit(f)
    # print keys related to spec/layout/bin
    for k in ks:
        if 'spec' in k.lower() or 'layout' in k.lower() or 'bin' in k.lower() or 'meta' in k.lower():
            print("  ", k)
