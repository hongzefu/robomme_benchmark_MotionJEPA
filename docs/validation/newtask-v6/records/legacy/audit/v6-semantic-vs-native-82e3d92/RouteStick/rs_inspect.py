import h5py,sys
f=h5py.File(sys.argv[1],'r')
print('root keys',list(f.keys())[:5], dict(f.attrs))
ep=f[next(iter(f))]
print('ep keys sample',[k for k in ep if not k.startswith('timestep_')], dict(ep.attrs))
for k in ep:
    if not k.startswith('timestep_'):
        def v(n,o):
            if isinstance(o,h5py.Dataset): 
                d=o[()]
                print(' ',k+'/'+n,o.shape,o.dtype, (d if o.size<20 else ''))
        if isinstance(ep[k],h5py.Group): ep[k].visititems(v)
        else: print(k, ep[k][()])
t=ep['timestep_0']
def v(n,o):
    if isinstance(o,h5py.Dataset): print(' ts0/'+n,o.shape,o.dtype, (o[()] if o.size<20 else ''))
t.visititems(v)
