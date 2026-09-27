import h5py, glob

def get_texts(h5path):
    out = []
    with h5py.File(h5path, 'r') as f:
        ep_key = [k for k in f.keys() if k.startswith('episode_')][0]
        ep = f[ep_key]
        keys = sorted([k for k in ep.keys() if k.startswith('timestep_')], key=lambda x: int(x.split('_')[1]))
        for k in keys:
            g = ep[k]
            if 'info' not in g:
                continue
            info = g['info']
            gs = info['grounded_subgoal'][()] if 'grounded_subgoal' in info else None
            if isinstance(gs, bytes):
                gs = gs.decode()
            out.append((int(k.split('_')[1]), gs))
    return out

for p in sorted(glob.glob('artifacts/newtask-v6/v1/base/B/PickXtimes_episode_*/hdf5_files/*.h5')):
    texts = get_texts(p)
    button_texts = [(t,s) for t,s in texts if s and 'press the button' in s]
    uniq = sorted(set(s for t,s in button_texts))
    print(p.split('/')[-1], 'unique=', uniq)
