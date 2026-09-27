import h5py,sys
f=h5py.File(sys.argv[1],'r')
print('attrs',dict(f.attrs))
def v(n,o):
    if isinstance(o,h5py.Dataset):
        if n.count('/')<4 or 'timestep_0/' in n or 'timestep_1/' in n: print(n,o.shape,o.dtype)
    else:
        if o.attrs: print('G',n,dict(o.attrs))
f.visititems(v)
