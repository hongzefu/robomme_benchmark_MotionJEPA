import h5py, json, numpy as np

cases = [
    ("xhard2", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/PickHighlight_episode_6/hdf5_files/PickHighlight_ep6_seed11200600.h5",
     "artifacts/newtask-v6/v6-01/xhard2/specs.jsonl", 11200600, "1", 553),
    ("xhard3", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard3/rollout/run1/episodes/PickHighlight_episode_3/hdf5_files/PickHighlight_ep3_seed13200300.h5",
     "artifacts/newtask-v6/v6-01/xhard3/specs.jsonl", 13200300, "8", 786),
    ("xhard4", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickHighlight_episode_0/hdf5_files/PickHighlight_ep0_seed7200000.h5",
     "artifacts/newtask-v6/v6-01/xhard4/specs.jsonl", 7200000, "0", 869),
]
for tier, h5path, specpath, seed, cubeid, t in cases:
    f = h5py.File(h5path, 'r')
    ep = f[list(f.keys())[0]]
    eef = ep[f'timestep_{t}/obs/eef_state'][()]
    spec = None
    for line in open(specpath):
        d = json.loads(line)
        if d.get('task') == 'PickHighlight' and d.get('seed') == seed:
            spec = d['spec']; break
    x,y,yaw = spec['layout']['cubes'][cubeid]
    eef_xy = eef[:2] if hasattr(eef,'__len__') else eef
    print(tier, 't=',t, 'eef_state[:3]=', np.array(eef).flatten()[:3], 'target cube xy=', (x,y))
    dx = np.array(eef).flatten()[0]-x; dy=np.array(eef).flatten()[1]-y
    print('  planar dist=', (dx**2+dy**2)**0.5)
    f.close()
