import h5py,sys
f=h5py.File(sys.argv[1],'r')
def show(name,obj):
    if name.count('/')>3: return
    if isinstance(obj,h5py.Dataset): print('D',name,obj.shape,obj.dtype)
    else: print('G',name,dict(obj.attrs) if len(obj.attrs)<6 else list(obj.attrs))
print(dict(f.attrs))
f.visititems(show)
