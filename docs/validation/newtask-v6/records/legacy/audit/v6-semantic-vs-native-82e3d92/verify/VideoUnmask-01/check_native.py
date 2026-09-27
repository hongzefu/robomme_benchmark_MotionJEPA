import h5py, json, re
base = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B"
files = {
  0: 'seed6000', 1:'seed6100', 4:'seed6400',
  2:'seed6200', 6:'seed6600', 10:'seed7001',
  3:'seed6300', 7:'seed6700', 11:'seed7100',
}
coord_re = re.compile(r"<(\d+),\s*(\d+)>")
for ep, seed in files.items():
    p = f"{base}/VideoUnmask_episode_{ep}/hdf5_files/VideoUnmask_ep{ep}_{seed}.h5"
    f = h5py.File(p, 'r')
    e = f[f'episode_{ep}']
    tkeys = sorted([k for k in e.keys() if k.startswith('timestep')], key=lambda x:int(x.split('_')[-1]))
    n = len(tkeys)
    boundaries = []
    for t in range(n):
        b = e[f'timestep_{t}']['info/is_subgoal_boundary'][()]
        if b:
            gs = e[f'timestep_{t}']['info/grounded_subgoal'][()].decode()
            ss = e[f'timestep_{t}']['info/simple_subgoal'][()].decode()
            boundaries.append((t, ss, gs))
    print(f"=== ep{ep} {seed}: {n} steps, {len(boundaries)} boundaries ===")
    for t, ss, gs in boundaries:
        has_coord = bool(coord_re.search(gs))
        print(f"  t={t} simple='{ss}' grounded='{gs}' has_coord={has_coord}")
