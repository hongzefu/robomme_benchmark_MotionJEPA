import h5py,sys
f=h5py.File(sys.argv[1],'r'); ep=f[list(f.keys())[0]]
def v(n,o):
    if isinstance(o,h5py.Dataset):
        x=o[()]
        s=repr(x)[:120] if o.size<20 or o.dtype.kind in 'OS' else str(o.shape)+str(o.dtype)
        print(n,s)
ep['timestep_0'].visititems(v)
print(ep['setup/available_multi_choices'][()][:2000]); print(ep['setup/task_goal'][()])
