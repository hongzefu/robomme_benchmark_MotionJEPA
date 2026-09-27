import h5py,sys,numpy as np
f=h5py.File(sys.argv[1],'r'); g=f[list(f.keys())[0]]
for t in [int(x) for x in sys.argv[2:]]:
    o=g[f'timestep_{t}']['obs']; a=g[f'timestep_{t}']['action']
    print(t,np.round(o['eef_state'][()],4),o['is_gripper_close'][()],np.round(o['gripper_state'][()],4),np.round(a['waypoint_action'][()],3))
