import h5py, sys, json
h5 = sys.argv[1]
with h5py.File(h5, 'r') as f:
    ep = list(f.keys())[0]
    g = f[ep]
    ts_keys = sorted([k for k in g.keys() if k.startswith('timestep_')], key=lambda x: int(x.split('_')[1]))
    n = len(ts_keys)
    boundaries = []
    for tk in ts_keys:
        t = int(tk.split('_')[1])
        step = g[tk]
        if bool(step['info']['is_subgoal_boundary'][()]):
            s = step['info']['simple_subgoal'][()]
            if isinstance(s, bytes): s = s.decode()
            demo = bool(step['info']['is_video_demo'][()])
            boundaries.append({'t': t, 's': s, 'demo': demo})
    print(json.dumps(boundaries, indent=1))
