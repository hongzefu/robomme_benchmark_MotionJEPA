import h5py,sys
f=h5py.File(sys.argv[1],'r')
def v(n,o):
    if isinstance(o,h5py.Dataset): print(n,o.shape,o.dtype)
top=list(f.keys()); print(top)
g=f[top[0]]; print(list(g.keys())[:10], len(g.keys()))
print(dict(f.attrs)); print(dict(g.attrs))
ks=list(g.keys())
for k in ks[:1]+[x for x in ks if not x.startswith('timestep')][:5]:
    g[k].visititems(v) if isinstance(g[k],h5py.Group) else print(k,g[k])
