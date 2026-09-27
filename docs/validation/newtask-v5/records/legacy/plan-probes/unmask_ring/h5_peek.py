import h5py, sys, numpy as np
f = h5py.File(sys.argv[1], 'r')
def walk(g, pre='', depth=0):
    for k in list(g.keys())[:12]:
        v = g[k]
        if isinstance(v, h5py.Group):
            print(pre + k + '/')
            if depth < 3: walk(v, pre + '  ', depth + 1)
        else:
            print(pre + k, v.shape, v.dtype)
walk(f)
ep = f['episode_0']
ts = sorted([k for k in ep.keys() if k.startswith('timestep_')], key=lambda s: int(s.split('_')[1]))
print('n timesteps', len(ts))
