import h5py, sys, numpy as np, json

def analyze(path, out_prefix):
    f = h5py.File(path, 'r')
    top = list(f.keys())
    ep = f[top[0]]
    n = sum(1 for k in ep.keys() if k.startswith('timestep_'))
    steps = [f'timestep_{i}' for i in range(n)]
    simple = []
    eefz = []
    grounded = []
    online = []
    for s in steps:
        g = ep[s]
        simple.append(g['info/simple_subgoal'][()].decode() if isinstance(g['info/simple_subgoal'][()], bytes) else str(g['info/simple_subgoal'][()]))
        online.append(g['info/simple_subgoal_online'][()].decode() if isinstance(g['info/simple_subgoal_online'][()], bytes) else str(g['info/simple_subgoal_online'][()]))
        eefz.append(float(g['obs/eef_state'][2]))
    simple = np.array(simple)
    eefz = np.array(eefz)
    # find segment where simple_subgoal == "press the second button"
    mask = simple == "press the second button"
    idxs = np.where(mask)[0]
    result = {"path": path, "n_steps": n}
    if len(idxs) == 0:
        result["press_second_button_segment"] = None
    else:
        seg_start, seg_end = idxs[0], idxs[-1]
        result["press_second_button_segment"] = [int(seg_start), int(seg_end)]
        result["seg_len"] = int(seg_end - seg_start + 1)
        # eef z trajectory within segment
        seg_z = eefz[seg_start:seg_end+1]
        result["eef_z_min_idx"] = int(seg_start + np.argmin(seg_z))
        result["eef_z_min"] = float(np.min(seg_z))
        result["eef_z_last"] = float(eefz[seg_end])
        result["eef_z_at_min_plus_context"] = seg_z[max(0,np.argmin(seg_z)-2):np.argmin(seg_z)+8].tolist()
        # what is the next subgoal after segment
        if seg_end + 1 < n:
            result["next_subgoal"] = simple[seg_end+1]
        # trailing static run: compute step-to-step eef displacement (position only, first 3 dims) within segment after press moment
        pos = np.array([ep[steps[i]]['obs/eef_state'][:3] for i in range(seg_start, seg_end+1)])
        diffs = np.linalg.norm(np.diff(pos, axis=0), axis=1)
        # find longest trailing run where diff < 1e-4 ending at seg_end-1 (diffs index i corresponds to pos[i]->pos[i+1])
        thresh = 1e-4
        static_run = 0
        for d in diffs[::-1]:
            if d < thresh:
                static_run += 1
            else:
                break
        result["trailing_static_steps_within_seg"] = int(static_run)
        result["diffs_tail"] = diffs[-10:].tolist()
    with open(out_prefix + '.json', 'w') as fo:
        json.dump(result, fo, indent=2)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    analyze(sys.argv[1], sys.argv[2])
