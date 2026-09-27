import h5py,sys
f=h5py.File(sys.argv[1],'r')
print('root keys',list(f.keys())[:5], dict(f.attrs))
ep=f[next(iter(f))]
print('ep attrs',{k:(v if len(str(v))<500 else str(v)[:500]) for k,v in ep.attrs.items()})
ks=[k for k in ep if not k.startswith('timestep_')]
print('non-timestep',ks)
for k in ks:
    def v(n,o):
        if isinstance(o,h5py.Dataset): print(' ',k+'/'+n,o.shape,o.dtype, (o[()] if o.size<20 else ''))
    if isinstance(ep[k],h5py.Group): ep[k].visititems(v)
    else: print(k, ep[k][()] if ep[k].size<50 else ep[k].shape)
t=ep['timestep_0']
t.visititems(lambda n,o: print('  t0/'+n, getattr(o,'shape',None), getattr(o,'dtype',None), (o[()] if isinstance(o,h5py.Dataset) and o.size<10 else '')))
