import h5py,sys
f=h5py.File(sys.argv[1],'r')
def v(n,o):
    if isinstance(o,h5py.Dataset): print(n,o.shape,o.dtype)
top=list(f.keys()); print(top)
ep=f[top[0]]
print(dict(f.attrs)); print(dict(ep.attrs))
keys=list(ep.keys()); print(len(keys),keys[:5],keys[-5:])
ep[keys[0]].visititems(v) if isinstance(ep[keys[0]],h5py.Group) else None
for k in keys:
    if not k.startswith('timestep'): 
        print('NONTS',k); 
        o=ep[k]
        if isinstance(o,h5py.Group): o.visititems(v)
        else: print(o[()] if o.size<50 else o.shape)
