import h5py,sys
f=h5py.File(sys.argv[1],'r'); ep=f['episode_0']
s=ep['setup']
for k in s: print(k, s[k][()])
def v(n,o):
    if isinstance(o,h5py.Dataset):
        x=o[()] 
        print(n,o.shape,o.dtype, x if (o.size<20 and o.dtype.kind not in 'u') else '')
ep['timestep_100'].visititems(v)
