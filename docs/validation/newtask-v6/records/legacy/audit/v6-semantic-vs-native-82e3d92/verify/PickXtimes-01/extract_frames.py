import h5py, cv2, numpy as np
p='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/PickXtimes_episode_3/hdf5_files/PickXtimes_ep3_seed8100300.h5'
outdir='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/verify/PickXtimes-01/'
f=h5py.File(p,'r')
ep=f['episode_3']
for t in [0, 955, 958, 960, 962, 970, 1000, 1033, 1078, 1079]:
    key=f'timestep_{t}'
    if key not in ep:
        continue
    g=ep[key]
    rgb = g['obs']['front_rgb'][()]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cv2.imwrite(outdir+f'frame_t{t}.png', bgr)
    gs = g['info']['grounded_subgoal'][()]
    if isinstance(gs, bytes): gs = gs.decode()
    print(t, gs, 'boundary=', bool(g['info']['is_subgoal_boundary'][()]))
