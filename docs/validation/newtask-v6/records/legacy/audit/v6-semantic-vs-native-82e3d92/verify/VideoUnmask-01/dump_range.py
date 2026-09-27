import h5py, json
p = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard2/rollout/run1/episodes/VideoUnmask_episode_0/hdf5_files/VideoUnmask_ep0_seed10600000.h5"
f = h5py.File(p, 'r')
ep = f['episode_0']
def get(t, field):
    v = ep[f'timestep_{t}'][field][()]
    if isinstance(v, bytes):
        v = v.decode('utf-8', errors='replace')
    return v

for t in [0,5,10,15,20,380,384,386,387,388,389,390,395,400,410,420,430,440,450,460,470,480,482,483,484,485,489]:
    try:
        sg = get(t, 'info/simple_subgoal')
        gs = get(t, 'info/grounded_subgoal')
        gso = get(t, 'info/grounded_subgoal_online')
        boundary = get(t, 'info/is_subgoal_boundary')
        ca = get(t, 'action/choice_action')
        print(f"t={t} boundary={boundary}")
        print(f"  simple_subgoal   = {sg}")
        print(f"  grounded_subgoal = {gs}")
        print(f"  grounded_subgoal_online = {gso}")
        print(f"  choice_action = {ca}")
    except Exception as e:
        print(f"t={t} ERROR {e}")
