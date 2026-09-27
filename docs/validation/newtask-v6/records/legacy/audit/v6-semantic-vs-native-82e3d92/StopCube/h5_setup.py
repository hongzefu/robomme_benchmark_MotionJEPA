import h5py,sys
f=h5py.File(sys.argv[1],'r')
s=f['episode_0/setup']
def show(name,obj):
    if isinstance(obj,h5py.Dataset):
        v=obj[()]
        if hasattr(v,'decode'): v=v.decode()
        print(name,obj.shape,repr(v)[:600])
    else: print(name,'GROUP',dict(obj.attrs))
s.visititems(show)
print(dict(s.attrs))
