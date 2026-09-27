import h5py,json,numpy as np
h='artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/PickHighlight_episode_0/hdf5_files/PickHighlight_ep0_seed9200000.h5'
f=h5py.File(h,'r'); ep=f['episode_0']
K=ep['setup/front_camera_intrinsic'][()]; Ex=ep['timestep_50/obs/front_camera_extrinsic'][()]
print(K);print(Ex)
print('eef0',ep['timestep_0/obs/eef_state'][()], ep['setup/available_multi_choices'][()])
spec=None
for line in open('artifacts/newtask-v6/v6-01/xhard1/specs.jsonl'):
    d=json.loads(line)
    if d.get('task')=='PickHighlight' and d.get('seed')==9200000: spec=d['spec']
img=ep['timestep_50/obs/front_rgb'][()]
for k,(x,y,yaw) in spec['layout']['cubes'].items():
    p=np.array([x,y,0.02,1.0]); c=Ex@p; uv=K@c; u,v=uv[0]/uv[2],uv[1]/uv[2]
    col=img[int(round(v)),int(round(u))] if 0<=v<256 and 0<=u<256 else None
    print(k,round(u,1),round(v,1),col,np.round(np.array(spec['objects']['color_rgba'][k][:3])*255))
