"""Read-only RouteStick HDF5 extraction (no robomme import)."""
import json, math, glob, os
from pathlib import Path
import h5py, numpy as np

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts')
OUT = ROOT / 'audit/v6-semantic-vs-native-82e3d92/RouteStick'
idx = json.load(open(ROOT / 'audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['RouteStick']

def load_specs():
    specs = {}
    for t in ['xhard1', 'xhard2', 'xhard3', 'xhard4']:
        for line in open(ROOT / f'newtask-v6/v6-01/{t}/specs.jsonl'):
            d = json.loads(line)
            if d.get('task') == 'RouteStick' and d.get('record') == 'spec' and d.get('selected'):
                specs[(t, d['episode'])] = d['spec']
    return specs

def target_xy(n, theta_deg):
    th = math.radians(theta_deg)
    x0, y0 = -0.1, (n - 4) * 0.07
    return np.array([x0 * math.cos(th) - y0 * math.sin(th), x0 * math.sin(th) + y0 * math.cos(th)])

def fit_theta_nodes(pts):
    best = None
    for th in np.arange(-30, 30.0001, 0.01):
        T = np.stack([target_xy(n, th) for n in range(9)])
        d = np.linalg.norm(pts[:, None, :] - T[None], axis=2)
        err = d.min(1).sum()
        if best is None or err < best[0]:
            best = (err, th, d.argmin(1))
    return best

LBL = {"move to the nearest left target by circling around the stick clockwise": "A",
       "move to the nearest right target by circling around the stick clockwise": "B",
       "move to the nearest left target by circling around the stick counterclockwise": "C",
       "move to the nearest right target by circling around the stick counterclockwise": "D"}

def read(h5path):
    f = h5py.File(h5path, 'r'); ep = f[next(iter(f))]
    setup = {k: ep['setup'][k][()] for k in ep['setup']}
    n = sum(k.startswith('timestep_') for k in ep)
    rows = []
    for i in range(n):
        t = ep[f'timestep_{i}']
        dec = lambda k: t[k][()].decode() if isinstance(t[k][()], bytes) else t[k][()]
        rows.append(dict(i=i, xyz=t['obs/eef_state'][()][:3].astype(float).tolist(),
            grounded=dec('info/grounded_subgoal'), simple=dec('info/simple_subgoal'),
            grounded_online=dec('info/grounded_subgoal_online'), simple_online=dec('info/simple_subgoal_online'),
            boundary=bool(t['info/is_subgoal_boundary'][()]), demo=bool(t['info/is_video_demo'][()]),
            completed=bool(t['info/is_completed'][()]), choice=json.loads(dec('action/choice_action')),
            closed=bool(t['obs/is_gripper_close'][()])))
    return setup, rows, ep

def segments(rows):
    b = [r['i'] for r in rows if r['boundary'] and not r['completed']]  # completed tail frames re-flag boundary; merge into last segment
    segs = []
    for j, a in enumerate(b):
        e = b[j + 1] if j + 1 < len(b) else len(rows)
        segs.append((a, e))
    return segs

def analyse(h5path, tier, episode, spec=None):
    setup, rows, ep = read(h5path)
    xyz = np.array([r['xyz'] for r in rows])
    segs = segments(rows)
    seginfo = []
    for a, e in segs:
        r = rows[a]; pts = xyz[a:e]
        labels = sorted(set(rr['grounded'] for rr in rows[a:e]))
        choices = sorted(set(json.dumps(rr['choice']) for rr in rows[a:e]))
        seginfo.append(dict(start=a, end=e, n=e - a, demo=r['demo'], label=r['grounded'], simple=r['simple'],
            labels_in_seg=labels, choices_in_seg=choices, start_xy=pts[0, :2].tolist(), end_xy=pts[-1, :2].tolist(),
            z_min=float(pts[:, 2].min()), z_max=float(pts[:, 2].max())))
    # node positions: start of first seg and end of every seg
    demo_segs = [s for s in seginfo if s['demo']]; exec_segs = [s for s in seginfo if not s['demo']]
    def node_pts(ss):
        return np.array([ss[0]['start_xy']] + [s['end_xy'] for s in ss]) if ss else np.zeros((0, 2))
    allpts = np.concatenate([node_pts(demo_segs), node_pts(exec_segs)])
    err, th, _ = fit_theta_nodes(allpts)
    if spec is not None:
        th_use = spec['layout']['rotation_deg']
    else:
        th_use = th
    T = np.stack([target_xy(n, th_use) for n in range(9)])
    def nodes_of(ss):
        p = node_pts(ss)
        d = np.linalg.norm(p[:, None] - T[None], axis=2)
        return d.argmin(1).tolist(), d.min(1).tolist()
    dn, dd = nodes_of(demo_segs); en, ed = nodes_of(exec_segs)
    # direction per segment from trajectory (same formula as RouteStick.direction_fail: avg cross relative to prev->curr line)
    def dirs(ss, nodes):
        out = []
        for k, s in enumerate(ss):
            p0 = T[nodes[k]]; p1 = T[nodes[k + 1]]
            L = p1 - p0; pts = xyz[s['start']:s['end'], :2] - p0
            c = L[0] * pts[:, 1] - L[1] * pts[:, 0]
            side_geom = 'left' if T[nodes[k + 1]][1] > T[nodes[k]][1] else 'right'
            out.append(dict(dir_traj='clockwise' if c.mean() > 0 else 'counterclockwise', cross_mean=float(c.mean()),
                            side_geom=side_geom, prev=nodes[k], curr=nodes[k + 1],
                            passes_odd_between=[int(o) for o in range(9) if o % 2 == 1 and min(nodes[k], nodes[k+1]) < o < max(nodes[k], nodes[k+1])]))
        return out
    ddir = dirs(demo_segs, dn); edir = dirs(exec_segs, en)
    for s, dinfo in zip(demo_segs, ddir): s.update(dinfo)
    for s, dinfo in zip(exec_segs, edir): s.update(dinfo)
    for s in demo_segs + exec_segs:
        lab = s['label']
        s['label_side'] = 'left' if ' left ' in lab else ('right' if ' right ' in lab else None)
        s['label_dir'] = lab.split()[-1]
        s['label_code'] = LBL.get(lab)
        s['side_ok'] = s['label_side'] == s['side_geom']
        s['dir_ok'] = s['label_dir'] == s['dir_traj']
    rec = dict(tier=tier, episode=episode, h5=str(h5path), setup_difficulty=setup['difficulty'].decode() if isinstance(setup['difficulty'], bytes) else str(setup['difficulty']),
        seed=int(setup['seed']), task_goal=[g.decode() for g in setup['task_goal']], choices=json.loads(setup['available_multi_choices']),
        frames=len(rows), n_demo_frames=sum(r['demo'] for r in rows), n_exec_frames=sum(not r['demo'] for r in rows),
        n_demo_segs=len(demo_segs), n_exec_segs=len(exec_segs), seg_lengths=sorted(set(s['n'] for s in seginfo)),
        theta_fit=float(th), theta_fit_err_sum=float(err), theta_spec=(spec['layout']['rotation_deg'] if spec else None),
        demo_nodes=dn, exec_nodes=en, demo_node_err_max=float(max(dd)) if dd else None, exec_node_err_max=float(max(ed)) if ed else None,
        spec_nodes=(spec['actions']['nodes'] if spec else None),
        spec_dirs=([spec['actions']['directions'][str(k)] for k in range(len(spec['actions']['directions']))] if spec else None),
        demo_labels=[s['label'] for s in demo_segs], exec_labels=[s['label'] for s in exec_segs],
        labels_paired=[s['label'] for s in demo_segs] == [s['label'] for s in exec_segs],
        nodes_paired=dn == en, all_side_ok=all(s['side_ok'] for s in demo_segs + exec_segs),
        all_dir_ok=all(s['dir_ok'] for s in demo_segs + exec_segs),
        spec_nodes_match=(dn == spec['actions']['nodes'] and en == spec['actions']['nodes']) if spec else None,
        spec_dirs_match=([s['label_dir'] for s in demo_segs] == [spec['actions']['directions'][str(k)] for k in range(len(demo_segs))]) if spec else None,
        last_completed=rows[-1]['completed'], completed_frames=[r['i'] for r in rows if r['completed']][:3],
        first_exec_start_vs_demo_start=float(np.linalg.norm(np.array(exec_segs[0]['start_xy']) - np.array(demo_segs[0]['start_xy']))) if exec_segs and demo_segs else None,
        z_range=[float(xyz[:, 2].min()), float(xyz[:, 2].max())],
        gripper_closed_all=all(r['closed'] for r in rows),
        grounded_eq_simple=all(r['grounded'] == r['simple'] for r in rows),
        online_eq=all(r['grounded'] == r['grounded_online'] and r['simple'] == r['simple_online'] for r in rows),
        distinct_labels=sorted(set(r['grounded'] for r in rows)),
        distinct_choices=sorted(set(json.dumps(r['choice']) for r in rows)),
        segments=demo_segs + exec_segs)
    # choice label consistency: choice letter per segment vs label
    mism = []
    for s in rec['segments']:
        chs = [json.loads(c)['choice'] for c in s['choices_in_seg']]
        exp = s['label_code']
        if not (len(chs) == 1 and chs[0] == exp):
            mism.append(dict(start=s['start'], label=s['label'], choices=chs, expected=exp))
    rec['choice_label_mismatches'] = mism
    return rec

if __name__ == '__main__':
    specs = load_specs()
    recs = []
    for it in idx:
        recs.append(analyse(it['h5'], it['difficulty'], it['episode'], specs.get((it['difficulty'], it['episode']))))
        recs[-1]['mp4'] = it['mp4'][0]
    for d in sorted(glob.glob(str(ROOT / 'newtask-v6/v1/base/B/RouteStick_episode_*'))):
        h5 = glob.glob(d + '/hdf5_files/*.h5')[0]; mp4 = glob.glob(d + '/videos/*.mp4')[0]
        tier = os.path.basename(mp4).split('_')[3]
        ep = int(os.path.basename(d).split('_')[-1])
        recs.append(analyse(h5, tier, ep)); recs[-1]['mp4'] = mp4
    json.dump(recs, open(OUT / 'records_raw.json', 'w'), indent=1)
    for r in recs:
        print(r['tier'], r['episode'], 'frames', r['frames'], 'demo/exec', r['n_demo_frames'], r['n_exec_frames'], 'segs', r['n_demo_segs'], r['n_exec_segs'],
              'seglen', r['seg_lengths'], 'th', round(r['theta_fit'], 2), r['theta_spec'], 'nodes', r['demo_nodes'], 'paired', r['labels_paired'], r['nodes_paired'],
              'side', r['all_side_ok'], 'dir', r['all_dir_ok'], 'spec', r['spec_nodes_match'], r['spec_dirs_match'], 'chmis', len(r['choice_label_mismatches']),
              'nodeerr', round(r['demo_node_err_max'], 4), round(r['exec_node_err_max'], 4), 'last_completed', r['last_completed'], r['completed_frames'],
              'startdiff', round(r['first_exec_start_vs_demo_start'], 4), 'z', [round(v, 3) for v in r['z_range']], 'labels', len(r['distinct_labels']), 'choices', r['distinct_choices'])
