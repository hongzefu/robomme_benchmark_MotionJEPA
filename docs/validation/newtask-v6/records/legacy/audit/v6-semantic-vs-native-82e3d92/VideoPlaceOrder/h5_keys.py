import h5py,sys
f=h5py.File(sys.argv[1],'r')
def show(name,obj):
    if isinstance(obj,h5py.Dataset):
        print(name,obj.shape,obj.dtype)
    else:
        if obj.attrs: print(name,'ATTRS',{k:(str(v)[:200]) for k,v in obj.attrs.items()})
print('root attrs',{k:str(v)[:300] for k,v in f.attrs.items()})
cnt=[0]
def v(name,obj):
    if cnt[0]<150: show(name,obj); cnt[0]+=1
f.visititems(v)
