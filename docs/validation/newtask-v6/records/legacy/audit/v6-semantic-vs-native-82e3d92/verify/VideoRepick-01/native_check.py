import h5py, glob, os, sys

def load_episode(path):
    f = h5py.File(path, 'r')
    ep_key = [k for k in f.keys() if k.startswith('episode_')][0]
    root = f[ep_key]
    steps = [k for k in root.keys() if k.startswith('timestep_')]
    steps.sort(key=lambda s: int(s.split('_')[1]))
    n = len(steps)
    out = []
    prev = None
    for i, k in enumerate(steps):
        sg = root[k]['info/simple_subgoal_online'][()]
        if isinstance(sg, bytes): sg = sg.decode()
        sg = str(sg)
        if sg != prev:
            out.append((i, sg))
            prev = sg
    seed = int(root['setup/seed'][()])
    diff = root['setup/difficulty'][()]
    if isinstance(diff, bytes): diff = diff.decode()
    f.close()
    return out, seed, diff, n

base = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B"
eps = sorted(glob.glob(os.path.join(base, "VideoRepick_episode_*")), key=lambda p: int(p.rsplit('_',1)[1]))
for d in eps:
    h5s = glob.glob(os.path.join(d, "hdf5_files", "*.h5"))
    if not h5s: continue
    path = h5s[0]
    events, seed, diff, n = load_episode(path)
    print(f"=== {os.path.basename(d)} seed={seed} diff={diff} n_steps={n} ===")
    for i,sg in events:
        print(" ", i, sg)
