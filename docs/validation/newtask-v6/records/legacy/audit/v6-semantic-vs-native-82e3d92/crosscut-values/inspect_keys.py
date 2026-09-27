import h5py,sys
p=sys.argv[1]
with h5py.File(p,'r') as f:
    print('root keys',list(f.keys())[:10], dict(f.attrs))
    for k in f.keys():
        g=f[k]
        print(k, type(g), dict(g.attrs) if hasattr(g,'attrs') else '')
        if isinstance(g,h5py.Group):
            ks=list(g.keys()); print(' n',len(ks), ks[:5], ks[-5:])
            ts=[x for x in ks if x.startswith('timestep_')]
            nt=[x for x in ks if not x.startswith('timestep_')]
            print(' non-ts', nt)
            for x in nt:
                def v(name,obj):
                    if isinstance(obj,h5py.Dataset):
                        val=obj[()] if obj.size<50 else obj.shape
                        print('   ',x+'/'+name, obj.dtype, val if not hasattr(val,'__len__') or len(str(val))<400 else str(val)[:400])
                g[x].visititems(v) if isinstance(g[x],h5py.Group) else print('   ',x,g[x][()] if g[x].size<50 else g[x].shape)
            if ts:
                def v2(name,obj):
                    if isinstance(obj,h5py.Dataset):
                        val=obj[()] if obj.size<30 else obj.shape
                        print('   ts0/'+name, obj.dtype, str(val)[:200])
                g[ts[0]].visititems(v2)
