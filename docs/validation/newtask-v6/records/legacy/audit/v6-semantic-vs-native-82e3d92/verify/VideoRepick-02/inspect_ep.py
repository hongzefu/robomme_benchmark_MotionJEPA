import sys, h5py, json

path = sys.argv[1]
f = h5py.File(path, 'r')
ep_key = [k for k in f.keys() if k.startswith('episode_')][0]
ep = f[ep_key]
timesteps = sorted([k for k in ep.keys() if k.startswith('timestep_')], key=lambda x: int(x.split('_')[1]))
print("n_timesteps", len(timesteps))
for tk in timesteps:
    ts = ep[tk]
    info = ts['info']
    is_boundary = bool(info['is_subgoal_boundary'][()]) if 'is_subgoal_boundary' in info else None
    if not is_boundary:
        continue
    is_demo = bool(info['is_video_demo'][()]) if 'is_video_demo' in info else None
    simple = info['simple_subgoal'][()]
    grounded = info['grounded_subgoal'][()]
    if isinstance(simple, bytes): simple = simple.decode()
    if isinstance(grounded, bytes): grounded = grounded.decode()
    print(f"--- {tk} demo={is_demo} ---")
    print("simple:", simple)
    print("grounded:", grounded)
