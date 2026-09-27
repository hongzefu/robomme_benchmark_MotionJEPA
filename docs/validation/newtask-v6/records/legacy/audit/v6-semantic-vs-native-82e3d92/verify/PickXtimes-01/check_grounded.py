import h5py, json, sys

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

paths = {
    'xhard1_ep0': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/PickXtimes_episode_0/hdf5_files/PickXtimes_ep0_seed8100000.h5',
    'xhard1_ep3': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/PickXtimes_episode_3/hdf5_files/PickXtimes_ep3_seed8100300.h5',
    'xhard1_ep6': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/PickXtimes_episode_6/hdf5_files/PickXtimes_ep6_seed8100600.h5',
    'xhard2_ep0': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/PickXtimes_episode_0/hdf5_files/PickXtimes_ep0_seed10100000.h5',
    'xhard2_ep3': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/PickXtimes_episode_3/hdf5_files/PickXtimes_ep3_seed10100300.h5',
    'xhard2_ep6': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/PickXtimes_episode_6/hdf5_files/PickXtimes_ep6_seed10100600.h5',
    'xhard3_ep0': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard3/rollout/run1/episodes/PickXtimes_episode_0/hdf5_files/PickXtimes_ep0_seed12100000.h5',
    'xhard3_ep3': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard3/rollout/run1/episodes/PickXtimes_episode_3/hdf5_files/PickXtimes_ep3_seed12100300.h5',
    'xhard3_ep6': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard3/rollout/run1/episodes/PickXtimes_episode_6/hdf5_files/PickXtimes_ep6_seed12100600.h5',
    'xhard4_ep0': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickXtimes_episode_0/hdf5_files/PickXtimes_ep0_seed6100000.h5',
    'xhard4_ep3': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickXtimes_episode_3/hdf5_files/PickXtimes_ep3_seed6100300.h5',
    'xhard4_ep6': '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/PickXtimes_episode_6/hdf5_files/PickXtimes_ep6_seed6100600.h5',
}

for name, p in paths.items():
    texts = get_texts(p)
    button_texts = [(t,s) for t,s in texts if s and 'press the button' in s]
    if not button_texts:
        print(name, 'NO BUTTON SEGMENT FOUND', 'total_steps=', len(texts))
        continue
    uniq = sorted(set(s for t,s in button_texts))
    tmin = min(t for t,s in button_texts)
    tmax = max(t for t,s in button_texts)
    print(name, f'button_seg t{tmin}-t{tmax} n={len(button_texts)}', 'unique_texts=', uniq)
