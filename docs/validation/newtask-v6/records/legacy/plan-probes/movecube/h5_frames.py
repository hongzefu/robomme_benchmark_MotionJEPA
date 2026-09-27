"""读 v5-01 的 MoveCube 三局 h5：总帧数、演示段（is_video_demo）帧数、执行段帧数、eef 最大水平距基座。"""
import glob, h5py, numpy as np
for f in sorted(glob.glob('artifacts/newtask-v5/v5-01/rollout/run1/episodes/MoveCube_episode_*/hdf5_files/*.h5')):
    h = h5py.File(f, 'r'); ep = h[list(h.keys())[0]]
    ts = sorted([k for k in ep if k.startswith('timestep_')], key=lambda s: int(s.split('_')[1]))
    demo = sum(bool(ep[t]['info/is_video_demo'][()]) for t in ts)
    eef = np.array([ep[t]['obs/eef_state'][()] for t in ts])
    goal = ep['setup/task_goal'][()]
    print(f.split('/')[-1], '总帧', len(ts), '演示帧', demo, '执行帧', len(ts) - demo,
          'difficulty', ep['setup/difficulty'][()], 'eef_xy 范围', np.round(eef[:, :2].min(0), 3), np.round(eef[:, :2].max(0), 3))
