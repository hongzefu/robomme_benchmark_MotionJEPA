"""只读现有 SwingXtimes HDF5，保存小型审查证据；不加载环境。"""
import json
import re
from pathlib import Path

import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-results/swing_xtimes'
BASE = ROOT / 'artifacts/audit/v6-semantic-0a3f989'
manifest = json.loads((BASE / 'docs/validation/newtask-v6/records/final-delivery.json').read_text())
paths = [Path(f['path']) for row in manifest['successes'] if row['task'] == 'SwingXtimes' for f in row['files'] if f['path'].endswith('.h5')]
paths += sorted((ROOT / 'artifacts/newtask-v6/v1/base/B').glob('SwingXtimes_episode_*/hdf5_files/*.h5'))

def scalar(group, key):
    v = group[key][()]
    return v.decode() if isinstance(v, bytes) else v.item() if hasattr(v, 'item') else v

rows = []
panels = {}
for p in paths:
    with h5py.File(p, 'r') as h:
        ep = h[next(iter(h))]
        tier = scalar(ep['setup'], 'difficulty')
        seed = scalar(ep['setup'], 'seed')
        goals = [x.decode() for x in ep['setup/task_goal'][()]]
        keys = sorted((k for k in ep if k.startswith('timestep_')), key=lambda k: int(k[9:]))
        spans = []
        current = None
        eef = []
        closed = []
        for i, key in enumerate(keys):
            g = ep[key]
            label = scalar(g, 'info/simple_subgoal')
            if label != current:
                spans.append({'start': i, 'end': i, 'label': label})
                current = label
            spans[-1]['end'] = i
            eef.append(g['obs/eef_state'][()].tolist())
            closed.append(bool(g['obs/is_gripper_close'][()]))
        swing = [s for s in spans if 'side target' in s['label']]
        right = [s for s in swing if 'right-side' in s['label']]
        left = [s for s in swing if 'left-side' in s['label']]
        r = dict(path=str(p), tier=tier, seed=seed, task_goals=goals, frames=len(keys), terminal_completed=scalar(ep[keys[-1]], 'info/is_completed'), right_segments=len(right), left_segments=len(left), spans=spans)
        if swing:
            lo, hi = swing[0]['start'], swing[-1]['end']
            r['swing_gripper_closed_fraction'] = float(np.mean(closed[lo:hi+1]))
            r['swing_eef_xyz_min'] = np.asarray(eef)[lo:hi+1,:3].min(axis=0).tolist()
            r['swing_eef_xyz_max'] = np.asarray(eef)[lo:hi+1,:3].max(axis=0).tolist()
        rows.append(r)
        picks = [0, right[0]['end'] if right else 0, left[0]['end'] if left else 0, right[-1]['end'] if right else 0, left[-1]['end'] if left else 0, len(keys)-1]
        strip = Image.new('RGB', (6*256, 282), 'white')
        draw = ImageDraw.Draw(strip)
        for j, idx in enumerate(picks):
            strip.paste(Image.fromarray(ep[keys[idx]+'/obs/front_rgb'][()]), (j*256,26))
            draw.text((j*256+3,3), f'{tier} seed {seed} t{idx}',fill='black')
        panels.setdefault(tier, []).append(strip)
        print(tier, seed, 'frames',len(keys),'right',len(right),'left',len(left),'closed',r.get('swing_gripper_closed_fraction'),'done',r['terminal_completed'])
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'existing_summary.json').write_text(json.dumps(rows, ensure_ascii=False,indent=2)+'\n')
for tier, strips in panels.items():
    img=Image.new('RGB',(1536,282*len(strips)),'white')
    for i,strip in enumerate(strips):img.paste(strip,(0,282*i))
    img.save(OUT/f'{tier}.png')
print(f'EXISTING_H5=PASS episodes={len(rows)} tiers={len(panels)} resets=0 rollouts=0')
