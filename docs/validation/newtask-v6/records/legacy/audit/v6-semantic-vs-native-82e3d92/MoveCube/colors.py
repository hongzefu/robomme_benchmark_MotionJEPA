import h5py,json,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
raw=json.load(open(E+'/raw_extract.json'))
r=raw[0]; f=h5py.File(r['h5'],'r'); ep=f[list(f)[0]]
img=ep['timestep_0/obs/front_rgb'][()]
for (rr,cc) in [(125,130),(124,129),(122,130),(128,130),(75,90),(97,70),(97,85),(40,40)]:
    print((rr,cc),img[rr-2:rr+3,cc-2:cc+3].reshape(-1,3).tolist()[:25:6])
