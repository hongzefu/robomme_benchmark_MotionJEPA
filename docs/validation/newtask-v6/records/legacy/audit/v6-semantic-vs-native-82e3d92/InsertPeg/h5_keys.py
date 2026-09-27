import h5py,sys
f=h5py.File(sys.argv[1],'r')
print(dict(f.attrs))
def v(n,o):
    if isinstance(o,h5py.Dataset):
        if n.count('/')<=4: print(n,o.shape,o.dtype)
    else:
        if n.count('/')<=2: print('G',n,dict(o.attrs) if len(o.attrs) else '')
f.visititems(v)
