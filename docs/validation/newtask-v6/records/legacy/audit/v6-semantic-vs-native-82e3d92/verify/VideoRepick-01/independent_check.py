import h5py, re, json, sys

def load_episode(path, ep_key):
    f = h5py.File(path, 'r')
    root = f[ep_key]
    steps = [k for k in root.keys() if k.startswith('timestep_')]
    steps.sort(key=lambda s: int(s.split('_')[1]))
    n = len(steps)
    out = []
    for i, k in enumerate(steps):
        sg = root[k]['info/simple_subgoal_online'][()]
        if isinstance(sg, bytes): sg = sg.decode()
        out.append((i, str(sg)))
    seed = int(root['setup/seed'][()])
    diff = root['setup/difficulty'][()]
    if isinstance(diff, bytes): diff = diff.decode()
    goal = root['setup/task_goal'][()]
    goal = [g.decode() if isinstance(g,bytes) else str(g) for g in goal]
    f.close()
    return out, seed, diff, goal, n

def find_button_start(subgoals):
    # find first index where subgoal mentions "press"
    for i, sg in subgoals:
        if 'press' in sg.lower():
            return i
    return None

def pick_put_events(subgoals):
    # subgoal text changes -> boundary; find "pick up" occurrences distinguishing ordinal
    events = []
    prev = None
    for i, sg in subgoals:
        if sg != prev:
            events.append((i, sg))
            prev = sg
    return events

path = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/VideoRepick_episode_3/hdf5_files/VideoRepick_ep3_seed6900300.h5"
subgoals, seed, diff, goal, n = load_episode(path, "episode_3")
print("seed", seed, "difficulty", diff, "n_steps", n)
print("goal:", goal)
events = pick_put_events(subgoals)
for i,sg in events:
    print(i, sg)
