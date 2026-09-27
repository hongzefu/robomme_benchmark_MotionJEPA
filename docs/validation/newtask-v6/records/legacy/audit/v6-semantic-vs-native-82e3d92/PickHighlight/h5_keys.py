import h5py,sys
f=h5py.File(sys.argv[1],'r')
def p(name,obj):
    if isinstance(obj,h5py.Dataset):
        if name.count('/')<=3 or 'timestep_0/' in name or 'timestep_0' ==name.split('/')[1] :
            print(name,obj.shape,obj.dtype)
    else:
        if name.count('/')<=1: print('G',name, dict(obj.attrs) if len(obj.attrs)<10 else list(obj.attrs))
f.visititems(p)
print('root attrs',dict(f.attrs))
