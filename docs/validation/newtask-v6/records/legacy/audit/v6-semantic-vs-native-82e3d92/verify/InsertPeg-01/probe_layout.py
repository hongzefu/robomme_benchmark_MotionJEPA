#!/usr/bin/env python3
import sys
import h5py

path = sys.argv[1]
f = h5py.File(path, "r")

def visit(name, obj):
    depth = name.count("/")
    if depth <= 2:
        kind = "GRP" if isinstance(obj, h5py.Group) else f"DSET shape={obj.shape} dtype={obj.dtype}"
        print(f"{'  '*depth}{name}  [{kind}]")

f.visititems(visit)
print("--- root attrs ---")
for k, v in f.attrs.items():
    print(k, "=", v if not hasattr(v, "shape") or v.shape == () else f"<array {v.shape}>")
f.close()
