import json, h5py, re
d = json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))
vu = d['VideoUnmask']
coord_re = re.compile(r"<(\d+),\s*(\d+)>")
for item in vu:
    p = item['h5']
    ep = item['episode']
    diff = item['difficulty']
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
    print(f"=== {diff} ep{ep} seed{item['seed']}: {n} steps, {len(boundaries)} boundaries, n_mp4={len(item['mp4'])} ===")
    for t, ss, gs in boundaries:
        if 'pick up' in ss:
            has_coord = bool(coord_re.search(gs))
            print(f"  t={t} simple='{ss}' has_coord={has_coord} grounded='{gs}'")
