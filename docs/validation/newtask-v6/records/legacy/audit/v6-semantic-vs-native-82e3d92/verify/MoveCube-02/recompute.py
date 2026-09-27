import h5py, json, numpy as np, glob, os

def red_count(im):
    im = im.astype(int)
    return int(((im[...,0] > 120) & (im[...,1] < 35) & (im[...,2] < 35)).sum())

def analyze(h5path, tag):
    f = h5py.File(h5path, 'r')
    ep = f[list(f)[0]]
    steps = sorted([k for k in ep.keys() if k.startswith('timestep_')], key=lambda s: int(s.split('_')[1]))
    n = len(steps)
    is_demo = []
    is_boundary = []
    for s in steps:
        info = ep[s]['info']
        is_demo.append(bool(info['is_video_demo'][()]))
        is_boundary.append(bool(info['is_subgoal_boundary'][()]))
    # find demo region and the last contiguous "static" segment within demo (is_video_demo True)
    demo_idx = [i for i, d in enumerate(is_demo) if d]
    if not demo_idx:
        return {'tag': tag, 'error': 'no demo segment', 'n_steps': n}
    demo_end = max(demo_idx)
    # boundaries within demo range give subgoal segments; last boundary before demo_end starts static segment
    boundary_idx = [i for i in demo_idx if is_boundary[i]]
    # static segment = from last boundary (inclusive) to demo_end
    static_start = max(boundary_idx) if boundary_idx else demo_end
    fr = []
    wr = []
    for i in range(static_start, demo_end + 1):
        s = steps[i]
        front = ep[s]['obs']['front_rgb'][()]
        wrist = ep[s]['obs']['wrist_rgb'][()]
        fr.append(red_count(front))
        wr.append(red_count(wrist))
    subgoal = ep[steps[static_start]]['info']['simple_subgoal'][()]
    if isinstance(subgoal, bytes):
        subgoal = subgoal.decode()
    return {
        'tag': tag, 'n_steps': n,
        'static_range': [int(steps[static_start].split('_')[1]), int(steps[demo_end].split('_')[1])],
        'subgoal_at_static_start': subgoal,
        'front_red_min': min(fr), 'front_red_max': max(fr),
        'wrist_red_min': min(wr), 'wrist_red_max': max(wr),
        'n_static_frames': len(fr),
    }

results = {}

# delivered run1 (already audited) - recompute independently to cross-check
run1 = {
    'xhard4_ep0_run1': 'artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/MoveCube_episode_0/hdf5_files/MoveCube_ep0_seed7400000.h5',
    'xhard4_ep3_run1': 'artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/MoveCube_episode_3/hdf5_files/MoveCube_ep3_seed7400300.h5',
    'xhard4_ep6_run1': 'artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/MoveCube_episode_6/hdf5_files/MoveCube_ep6_seed7400600.h5',
}
for tag, p in run1.items():
    try:
        results[tag] = analyze(p, tag)
    except Exception as e:
        results[tag] = {'tag': tag, 'error': str(e)}

# s2 probing batch (the candidate "other" episodes)
s2_h5 = sorted(glob.glob('artifacts/newtask-v6/v6-s2-20260926-01/episodes/MoveCube-xhard4-*/hdf5_files/*.h5'))
for p in s2_h5:
    tag = 's2_' + os.path.basename(os.path.dirname(os.path.dirname(p)))
    try:
        results[tag] = analyze(p, tag)
    except Exception as e:
        results[tag] = {'tag': tag, 'error': str(e)}

print(json.dumps(results, indent=1))
json.dump(results, open('artifacts/audit/v6-semantic-vs-native-82e3d92/verify/MoveCube-02/recompute_results.json', 'w'), indent=1)
