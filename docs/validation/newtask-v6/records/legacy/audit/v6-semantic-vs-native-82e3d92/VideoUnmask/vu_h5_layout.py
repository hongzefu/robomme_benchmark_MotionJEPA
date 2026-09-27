import h5py,sys
f=h5py.File(sys.argv[1],'r')
print('attrs',dict(f.attrs))
def v(name,obj):
    if name.count('/')<=3:
        print(name, getattr(obj,'shape',''), getattr(obj,'dtype',''), dict(obj.attrs) if len(obj.attrs) else '')
f.visititems(v)
