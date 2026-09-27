import h5py, json, numpy as np, cv2, sys
sys.path.insert(0, '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/ButtonUnmask')
from extract import blobs, proj
H='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/ButtonUnmask_episode_6/hdf5_files/ButtonUnmask_ep6_seed6800600.h5'
f=h5py.File(H,'r'); ep=f[list(f.keys())[0]]
b=blobs(ep['timestep_16/obs/front_rgb'][()])
for c in ('red','green','blue'): print(c,b[c])
for t in range(276,392,4):
    g=ep[f'timestep_{t}']
    e=g['obs/eef_state'][()][:3]
    print(t, g['info/simple_subgoal'][()].decode()[:40], g['info/grounded_subgoal'][()].decode()[:60], g['action/choice_action'][()].decode(), 'eefproj',[round(x) for x in proj(ep,t,e)], 'z',round(float(e[2]),3),'grip',bool(g['obs/is_gripper_close'][()]), 'online', g['info/grounded_subgoal_online'][()].decode()[:60])
