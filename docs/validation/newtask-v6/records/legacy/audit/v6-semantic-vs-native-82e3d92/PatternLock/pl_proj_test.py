import h5py,numpy as np,json
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/PatternLock/records_raw.json'))
r=R[0]
f=h5py.File(r['h5'],'r'); ep=f['episode_0']; K=ep['setup/front_camera_intrinsic'][()]
t=ep['timestep_23']; X=t['obs/front_camera_extrinsic'][()]; print(X)
p=t['obs/eef_state'][()][:3]
for name,P in [('eef',p)]+[(f'n{k}',np.array([-0.1+(k//5-2)*0.1,(k%5-2)*0.1,0.01])) for k in (0,2,7,22,24)]:
    c=X@np.r_[P,1]; uv=K@c; print(name,P.round(3),'cam',c.round(3),'uv',(uv[:2]/uv[2]).round(1))
