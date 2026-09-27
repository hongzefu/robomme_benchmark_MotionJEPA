import h5py,sys
f=h5py.File(sys.argv[1],'r'); g=f['episode_0']
s=g['setup']
for k in s: print('setup',k, s[k][()])
t=g['timestep_100']
def v(n,o):
    if isinstance(o,h5py.Dataset):
        val = o[()] if o.size<20 else o.shape
        print(n,o.shape,o.dtype, val)
t.visititems(v)
