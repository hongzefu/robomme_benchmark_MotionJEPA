import h5py,sys,numpy as np
f=h5py.File(sys.argv[1],'r'); g=f[list(f.keys())[0]]
K=g['setup/front_camera_intrinsic'][()]; Ex=g['timestep_0/obs/front_camera_extrinsic'][()]
print(K);print(Ex)
def proj(p):
    pc=Ex@np.r_[p,1]; uv=K@pc; return uv[:2]/uv[2], pc[2]
for p in [(-0.1036,0.3018,0.01),(-0.1463,0.2757,0.01),(-0.0749,-0.0521,0.04),(-0.104,0.302,0.01)]:
    print(p,proj(np.array(p)))
