import h5py, json, numpy as np

cases = [
    ("xhard2", "artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/PickHighlight_episode_6/hdf5_files/PickHighlight_ep6_seed11200600.h5",
     "artifacts/newtask-v6/v6-01/xhard2/specs.jsonl", 11200600, "1", [88,122], 500),
    ("xhard3", "artifacts/newtask-v6/v6-01/xhard3/rollout/run1/episodes/PickHighlight_episode_3/hdf5_files/PickHighlight_ep3_seed13200300.h5",
     "artifacts/newtask-v6/v6-01/xhard3/specs.jsonl", 13200300, "8", [57,92], 720),
    ("xhard4", "artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickHighlight_episode_0/hdf5_files/PickHighlight_ep0_seed7200000.h5",
     "artifacts/newtask-v6/v6-01/xhard4/specs.jsonl", 7200000, "0", [56,118], 805),
]

for tier, h5path, specpath, seed, targetcube, claimed_pt, t_sample in cases:
    f = h5py.File(h5path, 'r')
    ep = f[list(f.keys())[0]]
    K = ep['setup/front_camera_intrinsic'][()]
    Ex = ep[f'timestep_{t_sample}/obs/front_camera_extrinsic'][()]
    spec = None
    for line in open(specpath):
        d = json.loads(line)
        if d.get('task') == 'PickHighlight' and d.get('seed') == seed:
            spec = d['spec']
            break
    x, y, yaw = spec['layout']['cubes'][targetcube]
    p = np.array([x, y, 0.02, 1.0])
    c = Ex @ p
    uv = K @ c
    u, v = uv[0]/uv[2], uv[1]/uv[2]
    print(tier, targetcube, 'projected u,v =', round(u,1), round(v,1), ' | claimed choice_action.point [px,py]=', claimed_pt)
    f.close()
