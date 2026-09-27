import h5py,sys
f=h5py.File(sys.argv[1],'r')
print(dict(f.attrs))
for k in f.keys():
    print('TOP',k, list(f[k].keys())[:8], len(f[k]))
    e=f[k]
    for kk in ['setup']:
        if kk in e:
            def v(n,o):
                if isinstance(o,h5py.Dataset): print('  setup/',n,o.shape,o.dtype, o[()] if o.size<20 else '')
            e[kk].visititems(v)
    t=e['timestep_0']
    def v2(n,o):
        if isinstance(o,h5py.Dataset): print('  ts0/',n,o.shape,o.dtype, o[()] if o.size<8 else '')
    t.visititems(v2)
    print(dict(e.attrs))
