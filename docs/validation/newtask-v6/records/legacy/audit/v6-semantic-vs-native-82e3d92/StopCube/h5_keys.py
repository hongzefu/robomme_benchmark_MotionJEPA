import h5py,sys
f=h5py.File(sys.argv[1],'r')
print('attrs',dict(f.attrs))
top=list(f.keys()); print('top',top[:10],len(top))
def show(name,obj):
    if name.count('/')<=3 and ('timestep_0/' in name or name.count('/')<=1):
        if isinstance(obj,h5py.Dataset): print(name,obj.shape,obj.dtype)
        else: print(name,'GROUP',dict(obj.attrs) if len(obj.attrs) else '')
f.visititems(show)
