import h5py, cv2, numpy as np
p = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/VideoUnmask_episode_0/hdf5_files/VideoUnmask_ep0_seed10600000.h5"
f = h5py.File(p, 'r')
ep = f['episode_0']
outdir = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/verify/VideoUnmask-01/frames"
targets = [240, 388, 387, 420, 483]
# Also check t just after boundary at 237 (green pick done, before blue occlusion appears - baseline for blue cube visible)
for t in [238, 240, 250, 260, 270, 280, 300, 320, 340, 360, 380, 385, 387, 388, 389, 400, 420, 440, 460, 483]:
    rgb = ep[f'timestep_{t}']['obs/front_rgb'][()]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cv2.imwrite(f"{outdir}/front_t{t:03d}.png", bgr)
print("done")
