import h5py,sys,numpy as np
f=h5py.File(sys.argv[1],'r'); ep=f['episode_0']
K=ep['setup/front_camera_intrinsic'][()]
ts=sorted([int(k.split('_')[1]) for k in ep if k.startswith('timestep')])
for t in [0,40,60,70,80,100,150,200]:
    if t not in ts: continue
    g=ep[f'timestep_{t}']
    E=g['obs/front_camera_extrinsic'][()]; p=g['obs/eef_state'][()][:3]
    pc=E@np.r_[p,1]; uv=K@pc; uv=uv[:2]/uv[2]
    print(t,p.round(3),'u(col),v(row)=',uv.round(1), g['info/grounded_subgoal'][()], g['action/choice_action'][()], g['info/simple_subgoal'][()])
