"""Read-only extraction of ButtonUnmask HDF5 facts (h5py/numpy/cv2 only)."""
import h5py, json, re, glob, os, sys
import numpy as np, cv2

ROOT = '/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
OUT = f'{ROOT}/artifacts/audit/v6-semantic-vs-native-82e3d92/ButtonUnmask'
COLS = {  # HSV hue ranges (OpenCV 0-179), saturated pixels only
    'red': [(0, 6), (174, 180)], 'yellow': [(22, 38)], 'green': [(50, 70)],
    'cyan': [(80, 100)], 'blue': [(110, 130)], 'magenta': [(140, 160)],
}
def dec(x):
    x = x[()] if hasattr(x, 'shape') else x
    if isinstance(x, bytes): return x.decode()
    if isinstance(x, np.ndarray) and x.dtype == object: return [dec(v) for v in x]
    return x

def blobs(rgb, min_area=12):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = (hsv[..., 1] > 150) & (hsv[..., 2] > 70)
    res = {}
    for name, rngs in COLS.items():
        m = np.zeros(sat.shape, bool)
        for lo, hi in rngs: m |= (hsv[..., 0] >= lo) & (hsv[..., 0] < hi)
        m &= sat
        n, lab, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        res[name] = [dict(area=int(st[i, 4]), rc=[float(cen[i, 1]), float(cen[i, 0])]) for i in range(1, n) if st[i, 4] >= min_area]
    return res

def proj(ep, t, p):
    K = ep['setup/front_camera_intrinsic'][()]
    E = ep[f'timestep_{t}/obs/front_camera_extrinsic'][()]
    uv = K @ (E @ np.r_[p, 1]); return [float(uv[1] / uv[2]), float(uv[0] / uv[2])]  # row, col

def color_at(rgb, rc, r=3):
    y, x = int(round(rc[0])), int(round(rc[1]))
    patch = rgb[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
    b = blobs(np.ascontiguousarray(patch.copy()), min_area=1)
    counts = {k: sum(d['area'] for d in v) for k, v in b.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else 'none', counts

def process(h5, tier, epi, mp4s):
    f = h5py.File(h5, 'r'); rec_keys = list(f.keys()); assert len(rec_keys) == 1, rec_keys; ep = f[rec_keys[0]]; s = ep['setup']
    rec = dict(h5=h5, mp4=mp4s, tier=tier, episode=epi, setup_difficulty=dec(s['difficulty']), seed=int(s['seed'][()]),
               task_goal=dec(s['task_goal']), choices=json.loads(dec(s['available_multi_choices'])))
    ts = sorted(int(k.split('_')[1]) for k in ep if k.startswith('timestep'))
    rec['n_steps'] = len(ts); rec['ts_contiguous'] = ts == list(range(len(ts)))
    rows = []
    for t in ts:
        g = ep[f'timestep_{t}']
        rows.append(dict(t=t, ss=dec(g['info/simple_subgoal']), gs=dec(g['info/grounded_subgoal']),
                         sso=dec(g['info/simple_subgoal_online']), gso=dec(g['info/grounded_subgoal_online']),
                         ca=dec(g['action/choice_action']), bd=bool(g['info/is_subgoal_boundary'][()]),
                         done=bool(g['info/is_completed'][()]), demo=bool(g['info/is_video_demo'][()]),
                         grip=bool(g['obs/is_gripper_close'][()]), eef=g['obs/eef_state'][()][:3].tolist()))
    rec['demo_steps'] = sum(r['demo'] for r in rows)
    rec['completed_last'] = rows[-1]['done']; rec['completed_first_t'] = next((r['t'] for r in rows if r['done']), None)
    # segments of simple_subgoal
    segs = []
    for r in rows:
        if not segs or segs[-1]['ss'] != r['ss'] or segs[-1]['gs'] != r['gs']:
            segs.append(dict(ss=r['ss'], gs=r['gs'], t0=r['t'], t1=r['t'], choices=set()))
        segs[-1]['t1'] = r['t']; segs[-1]['choices'].add(r['ca'])
    for sg in segs: sg['choices'] = sorted(sg['choices'])[:6]
    rec['boundaries'] = [r['t'] for r in rows if r['bd']]
    # reveal frame: step 16 (bins parked [0,32))
    rev = {}
    for t in (0, 16, 31, 32, 33):
        rgb = ep[f'timestep_{t}/obs/front_rgb'][()]
        b = blobs(rgb); rev[t] = {k: len(v) for k, v in b.items()}
        if t == 16: rev_blobs = b; rev_rgb = rgb
        cv2.imwrite(f"{OUT}/frames/{tier}_ep{epi}_t{t:04d}.png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    rec['reveal_blob_counts'] = rev
    rec['reveal_rgb_blobs_t16'] = {k: v for k, v in rev_blobs.items() if k in ('red', 'green', 'blue')}
    # picks
    picks = []
    m = re.compile(r'pick up the container at <(\d+), (\d+)> that hides the (\w+) cube')
    for sg in segs:
        if not sg['ss'].startswith('pick up'): continue
        mm = m.match(sg['gs'] or '')
        grounded_missing = mm is None
        if grounded_missing:  # fall back to the per-frame online grounding (first online text with coords in segment)
            onl = [r['gso'] for r in rows if sg['t0'] <= r['t'] <= sg['t1'] and m.match(r['gso'] or '')]
            mm = m.match(onl[0]) if onl else None
            if mm is None: continue
        rc = [int(mm.group(1)), int(mm.group(2))]; named = mm.group(3)
        # nearest saturated cube blob in reveal frame to grounded coordinate
        cand = [(np.hypot(b['rc'][0] - rc[0], b['rc'][1] - rc[1]), c, b['rc']) for c, bl in rev_blobs.items() for b in bl]
        cand.sort()
        # grasp moment: first gripper close within segment; lift = max eef z in segment
        seg_rows = [r for r in rows if sg['t0'] <= r['t'] <= sg['t1']]
        gt = next((seg_rows[i]['t'] for i in range(1, len(seg_rows)) if seg_rows[i]['grip'] and not seg_rows[i-1]['grip']), None)
        g_rc = proj(ep, gt, rows[gt]['eef']) if gt is not None else None
        gcand = sorted([(np.hypot(b['rc'][0] - g_rc[0], b['rc'][1] - g_rc[1]), c) for c, bl in rev_blobs.items() for b in bl])[:2] if g_rc else None
        maxz = max(r['eef'][2] for r in seg_rows)
        # exposure check: at segment end, which colour sits at the reveal-frame centroid of the named cube
        end_rgb = ep[f"timestep_{sg['t1']}/obs/front_rgb"][()]
        cv2.imwrite(f"{OUT}/frames/{tier}_ep{epi}_pickend_t{sg['t1']:04d}.png", cv2.cvtColor(end_rgb, cv2.COLOR_RGB2BGR))
        named_blob = [b for b in rev_blobs.get(named, [])]
        exp = color_at(end_rgb, named_blob[0]['rc']) if named_blob else None
        picks.append(dict(t0=sg['t0'], t1=sg['t1'], named=named, grounded_text=sg['gs'], grounded_missing=grounded_missing, grounded_rc=rc,
                          nearest_reveal_blob=dict(color=cand[0][1], dist=round(float(cand[0][0]), 1), rc=[round(x, 1) for x in cand[0][2]]) if cand else None,
                          second_blob=dict(color=cand[1][1], dist=round(float(cand[1][0]), 1)) if len(cand) > 1 else None,
                          grasp_t=gt, grasp_proj_rc=[round(x, 1) for x in g_rc] if g_rc else None,
                          grasp_nearest=[(round(float(d), 1), c) for d, c in gcand] if gcand else None,
                          seg_max_eef_z=round(maxz, 3), n_named_blobs_in_reveal=len(named_blob),
                          end_color_at_named_cube=exp[0] if exp else None))
    rec['picks'] = picks
    rec['segments'] = [dict(ss=s_['ss'], gs=s_['gs'], t0=s_['t0'], t1=s_['t1'], choices=s_['choices']) for s_ in segs]
    # final frame
    last = ts[-1]; rgb = ep[f'timestep_{last}/obs/front_rgb'][()]
    cv2.imwrite(f"{OUT}/frames/{tier}_ep{epi}_last_t{last:04d}.png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    rec['last_frame_blob_counts'] = {k: len(v) for k, v in blobs(rgb).items()}
    # video frame count
    vinfo = []
    for mp in mp4s:
        cap = cv2.VideoCapture(mp); vinfo.append(dict(file=os.path.basename(mp), frames=int(cap.get(7)), fps=cap.get(5), w=int(cap.get(3)), h=int(cap.get(4)))); cap.release()
    rec['videos'] = vinfo
    return rec

def main():
    os.makedirs(f'{OUT}/frames', exist_ok=True)
    idx = json.load(open(f'{ROOT}/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['ButtonUnmask']
    recs = []
    for e in idx: recs.append(process(e['h5'], e['difficulty'], e['episode'], e['mp4']))
    for d in sorted(glob.glob(f'{ROOT}/artifacts/newtask-v6/v1/base/B/ButtonUnmask_episode_*')):
        h5 = glob.glob(f'{d}/hdf5_files/*.h5')[0]; mp4 = sorted(glob.glob(f'{d}/videos/*.mp4'))
        tier = re.search(r'_(easy|medium|hard)_', os.path.basename(mp4[0])).group(1)
        recs.append(process(h5, tier, int(d.rsplit('_', 1)[1]), mp4))
    json.dump(recs, open(f'{OUT}/records_raw.json', 'w'), indent=1, default=str)
    for r in recs:
        print(r['tier'], r['episode'], r['setup_difficulty'], r['n_steps'], 'done', r['completed_last'], r['completed_first_t'], 'demo', r['demo_steps'], 'vids', [(v['frames'], v['w']) for v in r['videos']])
        print('  goal:', r['task_goal']); print('  reveal:', r['reveal_blob_counts'][16], 't0', r['reveal_blob_counts'][0], 't33', r['reveal_blob_counts'][33], 'last', r['last_frame_blob_counts'])
        for p in r['picks']: print('  pick', p)
        print('  segs:', [(s['ss'], s['t0'], s['t1']) for s in r['segments']])

if __name__ == '__main__':
    main()
