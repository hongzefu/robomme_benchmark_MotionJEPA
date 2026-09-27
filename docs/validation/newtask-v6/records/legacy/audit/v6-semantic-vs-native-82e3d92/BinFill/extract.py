"""Read-only BinFill audit extractor (h5py/numpy/cv2/json only). No robomme import, no simulation."""
import json, re, glob, os
from pathlib import Path
import h5py, numpy as np, cv2

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill'
idx = json.loads((ROOT / 'artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json').read_text())['BinFill']
eps = [dict(kind='new', **e) for e in idx]
for d in sorted(glob.glob(str(ROOT / 'artifacts/newtask-v6/v1/base/B/BinFill_episode_*'))):
    h5 = glob.glob(d + '/hdf5_files/*.h5')[0]
    mp4 = glob.glob(d + '/videos/*.mp4')
    m = re.search(r'_(easy|medium|hard)_', os.path.basename(mp4[0]))
    eps.append(dict(kind='native', difficulty=m.group(1), episode=int(re.search(r'episode_(\d+)', d).group(1)), h5=h5, mp4=mp4))

CH = {'red': 0, 'green': 1, 'blue': 2}
def color_mask(rgb, color):
    ch = CH[color]; rgb = rgb.astype(float)
    other = np.max(rgb[:, :, [c for c in range(3) if c != ch]], axis=2)
    return (rgb[:, :, ch] > 60) & (rgb[:, :, ch] > other * 2.5)

def classify_px(rgb, u, v, r=2):
    patch = rgb[max(0, v - r):v + r + 1, max(0, u - r):u + r + 1].reshape(-1, 3).astype(float)
    res = {}
    for c in CH:
        ch = CH[c]; other = np.max(patch[:, [k for k in range(3) if k != ch]], axis=1)
        res[c] = int(((patch[:, ch] > 60) & (patch[:, ch] > other * 2.5)).sum())
    best = max(res, key=res.get)
    return best if res[best] > 0 else 'none', res

def backproject(e, t, us, vs):
    g = e[f'timestep_{t}/obs']
    ki = np.linalg.inv(e['setup/front_camera_intrinsic'][()])
    depth = g['front_depth'][()][:, :, 0].astype(float) / 1000
    ext = g['front_camera_extrinsic'][()]
    us = np.asarray(us); vs = np.asarray(vs)
    cam = (ki @ np.vstack([us, vs, np.ones(len(us))])) * depth[vs, us]
    return (ext[:, :3].T @ (cam - ext[:, 3, None])).T

def table_blobs(e, t, zmax=0.06):
    """count cube-like blobs per color lying on the table (world z<zmax) in front camera"""
    g = e[f'timestep_{t}/obs']; rgb = g['front_rgb'][()]
    out = {}
    for c in CH:
        m = color_mask(rgb, c)
        v, u = np.nonzero(m)
        if len(u):
            w = backproject(e, t, u, v)
            keep = w[:, 2] < zmax
            mm = np.zeros_like(m, dtype=np.uint8); mm[v[keep], u[keep]] = 1
        else:
            mm = m.astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mm, connectivity=8)
        areas = [int(s[4]) for s in stats[1:] if s[4] >= 15]
        out[c] = dict(n=len(areas), areas=sorted(areas, reverse=True))
    return out

records = []
for ep in eps:
    f = h5py.File(ep['h5'], 'r'); key = list(f.keys())[0]; e = f[key]
    n = len([k for k in e.keys() if k.startswith('timestep_')])
    s = lambda t, k: e[f'timestep_{t}/{k}'][()]
    dec = lambda x: x.decode() if isinstance(x, bytes) else x
    goal = [dec(x) for x in e['setup/task_goal'][()]]
    diff = dec(e['setup/difficulty'][()])
    segs = []; prev = None
    demo = 0; bounds = []
    for t in range(n):
        ss = dec(s(t, 'info/simple_subgoal_online'))
        if s(t, 'info/is_video_demo'): demo += 1
        if s(t, 'info/is_subgoal_boundary'):
            bounds.append(dict(t=t, choice=dec(s(t, 'action/choice_action')), grounded=dec(s(t, 'info/grounded_subgoal_online')), simple=ss))
        if ss != prev:
            segs.append(dict(start=t, simple=ss, grounded=dec(s(t, 'info/grounded_subgoal_online')), simple_offline=dec(s(t, 'info/simple_subgoal'))))
            prev = ss
    for i, sg in enumerate(segs):
        sg['end'] = segs[i + 1]['start'] - 1 if i + 1 < len(segs) else n - 1
    completed_last = bool(s(n - 1, 'info/is_completed'))
    # parse goal counts
    num = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
    goal_counts = {c: 0 for c in CH}
    for w, c in re.findall(r'(\w+) (red|blue|green) cubes?', goal[0]):
        goal_counts[c] += num[w]
    # chain counts
    picks = [re.match(r'pick up the (\w+) (red|blue|green) cube', sg['simple']) for sg in segs]
    chain_counts = {c: 0 for c in CH}; ordinals_ok = True; ord_seen = {c: [] for c in CH}
    ORD = ["first","second","third","fourth","fifth","sixth","seventh","eighth","ninth","tenth","eleventh","twelfth"]
    for m in picks:
        if m:
            chain_counts[m.group(2)] += 1; ord_seen[m.group(2)].append(m.group(1))
    for c in CH:
        if ord_seen[c] != ORD[:len(ord_seen[c])]: ordinals_ok = False
    # grounded point color check at segment start (u=x,v=y assumption tested both ways)
    gchecks = []
    board_uv = None
    for sg in segs:
        m = re.search(r'at <(\d+), (\d+)>', sg['grounded'])
        if not m: continue
        a, b = int(m.group(1)), int(m.group(2))   # grounded text is <row, col>
        rgb = s(sg['start'], 'obs/front_rgb')
        c_rc, cnt = classify_px(rgb, b, a)   # u=col=b, v=row=a
        w = backproject(e, sg['start'], [b], [a])[0]
        mm = re.match(r'pick up the \w+ (red|blue|green) cube', sg['simple'])
        gchecks.append(dict(t=sg['start'], text=sg['grounded'], expected=mm.group(1) if mm else None, color_at_point=c_rc, color_px=cnt, world_xyz=[round(float(x), 4) for x in w]))
        if sg['simple'] == 'put it into the bin' and board_uv is None:
            board_uv = (a, b); board_xy = w[:2]
    # board center: from rng_trace if present
    rt = Path(ep['h5']).parent.parent / 'rng_trace.json'
    trace = None
    if rt.exists():
        trace = {c['path']: c['drawn'] for c in json.loads(rt.read_text())['calls']}
        off = trace['layout.board.offsets']; board_xy = np.array([0.15 + off[0], off[1]])
    # drops: color disappearing above the hole
    drops = []
    for j, sg in enumerate(segs):
        if sg['simple'] != 'put it into the bin': continue
        named = picks[j - 1].group(2) if j > 0 and picks[j - 1] else None
        end = sg['end'] + 1
        per = {}
        for c in CH:
            seq = []
            for ti in range(max(0, end - 14), min(n, end + 2)):
                rgb = s(ti, 'obs/front_rgb'); v, u = np.nonzero(color_mask(rgb, c))
                if len(u) == 0: seq.append(0); continue
                w = backproject(e, ti, u, v)
                sel = (np.linalg.norm(w[:, :2] - board_xy, axis=1) < 0.07) & (w[:, 2] > 0.07) & (w[:, 2] < 0.35)
                seq.append(int(sel.sum()))
            per[c] = seq
        # color with max pre-drop presence
        dropped = max(per, key=lambda c: max(per[c][:-2]) if per[c][:-2] else 0)
        drops.append(dict(seg_start=sg['start'], seg_end=sg['end'], named_color=named, above_hole_color=dropped if max(per[dropped]) > 0 else 'none', pixel_seq=per))
    rec = dict(kind=ep['kind'], difficulty=diff, episode=ep['episode'], seed=int(e['setup/seed'][()]), h5=ep['h5'], mp4=ep['mp4'],
               task_goal=goal, n_steps=n, is_video_demo_steps=demo, completed_last=completed_last,
               choices=json.loads(dec(e['setup/available_multi_choices'][()])),
               goal_counts=goal_counts, chain_counts=chain_counts, ordinals_ok=ordinals_ok, ordinals=ord_seen,
               segments=segs, boundaries=bounds, grounded_checks=gchecks, drops=drops,
               table_blobs_t0=table_blobs(e, 0), table_blobs_last=table_blobs(e, n - 1))
    if trace:
        rec['trace'] = {k: trace[k] for k in ['layout.dynamic', 'objects.color_pool', 'objects.put_in_color', 'objects.spawn_numbers', 'objects.target_numbers', 'objects.color_redraws', 'objects.color_mix_fallback', 'objects.color_mix_max_component', 'initializations.0.color_order', 'initializations.1.color_order'] if k in trace}
        rec['trace']['layout.board.offsets'] = trace['layout.board.offsets']
        rec['trace']['layout.button_xy'] = trace['layout.button_xy']
        rec['trace']['cubes'] = {k[len('layout.cubes.'):]: v for k, v in trace.items() if k.startswith('layout.cubes.')}
    records.append(rec)
    f.close()
    print(ep['kind'], diff, ep['episode'], n, goal[0][:90], goal_counts, chain_counts, ordinals_ok, 'demo', demo, 'done', completed_last)
(OUT / 'records.json').write_text(json.dumps(records, indent=1, default=float))
