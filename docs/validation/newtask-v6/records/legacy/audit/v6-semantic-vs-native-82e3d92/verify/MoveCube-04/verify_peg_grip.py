import h5py, numpy as np, glob
h = glob.glob('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-s2-20260926-01/episodes/MoveCube-xhard4-6100001/hdf5_files/*.h5')[0]
f = h5py.File(h,'r'); ep = f[list(f)[0]]
ts = sorted([k for k in ep if k.startswith('timestep_')], key=lambda k:int(k.split('_')[1]))
n = len(ts)
def simple(i): return ep[ts[i]]['info/simple_subgoal'][()].decode()
def demo(i): return bool(ep[ts[i]]['info/is_video_demo'][()])
def grip(i): return bool(ep[ts[i]]['obs/is_gripper_close'][()])
# find hook segment boundaries by scanning simple_subgoal transitions
boundaries=[]
prev=None
for i in range(n):
    s=(simple(i),demo(i))
    if s!=prev:
        boundaries.append((i,s))
        prev=s
print("boundaries:", boundaries)
demo_hook = range(145,241)
exec_hook = range(426,537)
gd = np.mean([grip(i) for i in demo_hook])
ge = np.mean([grip(i) for i in exec_hook])
print("demo_hook grip_closed_frac", gd)
print("exec_hook grip_closed_frac", ge)
