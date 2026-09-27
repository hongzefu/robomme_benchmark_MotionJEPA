import h5py,sys
f=h5py.File(sys.argv[1],'r')
def show(name,obj):
    if isinstance(obj,h5py.Dataset): print(name,obj.shape,obj.dtype)
    else: print(name,'GROUP',dict(obj.attrs) if len(obj.attrs) and len(obj.attrs)<10 else len(obj.attrs))
top=list(f.keys()); print(top[:5],len(top)); print(dict(f.attrs).keys())
g=f[top[0]]
cnt=0
def v(name,obj):
    global cnt
    if name.startswith('timestep_') and not name.split('/')[0]=='timestep_0' : return
    show(name,obj)
g.visititems(v)
