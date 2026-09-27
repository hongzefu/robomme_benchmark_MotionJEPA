import h5py,sys
f=h5py.File(sys.argv[1],'r')
def v(n,o):
    if isinstance(o,h5py.Dataset): print(n,o.shape,o.dtype)
    else:
        if o.attrs: print(n,'ATTRS',dict(o.attrs))
f.visititems(v)
print('ROOT ATTRS',dict(f.attrs))
