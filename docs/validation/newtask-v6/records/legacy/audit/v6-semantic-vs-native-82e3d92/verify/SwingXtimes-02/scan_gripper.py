import h5py, sys, json

path = sys.argv[1]
f = h5py.File(path, 'r')
ep_key = list(f.keys())[0]
g = f[ep_key]
task_goal = list(g['setup/task_goal'][()])
print("task_goal[0]:", task_goal[0])
print("task_goal[1]:", task_goal[1] if len(task_goal) > 1 else None)

n = 0
while f"timestep_{n}" in g:
    n += 1
print("n_timesteps:", n)

boundaries = []
prev_subgoal = None
for i in range(n):
    ts = g[f"timestep_{i}"]
    is_boundary = bool(ts['info/is_subgoal_boundary'][()])
    simple = ts['info/simple_subgoal'][()]
    if isinstance(simple, bytes):
        simple = simple.decode()
    gripper_close = bool(ts['obs/is_gripper_close'][()])
    if is_boundary or simple != prev_subgoal:
        boundaries.append((i, simple, gripper_close))
        prev_subgoal = simple

for b in boundaries:
    print(b)
