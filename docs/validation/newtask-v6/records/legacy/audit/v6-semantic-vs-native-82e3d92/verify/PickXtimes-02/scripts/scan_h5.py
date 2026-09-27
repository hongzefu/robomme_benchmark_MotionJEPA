import h5py, sys, json

def scan(path, ep_key=None):
    with h5py.File(path, 'r') as f:
        if ep_key is None:
            ep_key = [k for k in f.keys() if k.startswith('episode_')][0]
        g = f[ep_key]
        ts_keys = [k for k in g.keys() if k.startswith('timestep_')]
        n_total = len(ts_keys)
        # find first is_completed True, scanning in numeric order
        idxs = sorted(int(k.split('_')[1]) for k in ts_keys)
        first_completed = None
        for i in idxs:
            info = g[f'timestep_{i}/info']
            if bool(info['is_completed'][()]):
                first_completed = i
                break
        # video-demo count
        n_video_demo = 0
        for i in idxs:
            info = g[f'timestep_{i}/info']
            if bool(info['is_video_demo'][()]):
                n_video_demo += 1
        return {
            'path': path,
            'n_total_steps': n_total,
            'max_idx': max(idxs),
            'first_completed_step': first_completed,
            'n_video_demo_steps': n_video_demo,
        }

if __name__ == '__main__':
    path = sys.argv[1]
    ep_key = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(scan(path, ep_key), indent=2))
