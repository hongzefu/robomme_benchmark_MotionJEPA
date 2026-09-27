import h5py,sys
f=h5py.File(sys.argv[1],'r')
def show(name,obj):
    if isinstance(obj,h5py.Dataset):
        print(name,obj.shape,obj.dtype)
    else:
        if len(obj.attrs): print(name,'ATTRS',dict(obj.attrs))
top=list(f.keys()); print('TOP',top[:10],len(top))
print('rootattrs',dict(f.attrs))
g=f[top[0]]
print('ep keys',list(g.keys())[:20],len(g.keys()))
first=[k for k in g.keys()]
for k in first[:3]:
    g[k].visititems(show) if isinstance(g[k],h5py.Group) else print(k,g[k].shape)
