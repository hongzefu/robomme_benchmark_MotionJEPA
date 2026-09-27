"""只读既有交付的 PickHighlight 元数据与少量图像，产出局部审查证据。"""
from pathlib import Path
import json
import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
BASE = ROOT / 'artifacts/audit/v6-semantic-0a3f989'
OUT = ROOT / 'artifacts/audit/v6-semantic-results/pick_highlight'
manifest = json.loads((BASE / 'docs/validation/newtask-v6/records/final-delivery.json').read_text())
records = []
sheet = Image.new('RGB', (4 * 256, 3 * 278), 'white')
draw = ImageDraw.Draw(sheet)
for item in manifest['successes']:
    if item['task'] != 'PickHighlight':
        continue
    path = Path(next(x['path'] for x in item['files'] if x['path'].endswith('.h5')))
    trace = json.loads((path.parent.parent / 'rng_trace.json').read_text())
    values = {x['path']: x['drawn'] for x in trace['calls']}
    with h5py.File(path, 'r') as f:
        episode = f[f"episode_{item['episode']}"]
        steps = sorted((k for k in episode if k.startswith('timestep_')), key=lambda k: int(k.split('_')[-1]))
        transitions = []
        previous = None
        for k in steps:
            info = episode[k]['info']
            label = info['simple_subgoal_online'][()].decode()
            if label != previous:
                transitions.append({'frame': int(k.split('_')[-1]), 'label': label})
                previous = label
        last = episode[steps[-1]]
        row = {
            'difficulty': item['difficulty'], 'episode': item['episode'], 'seed': item['seed'],
            'path': str(path), 'frames': len(steps),
            'task_goals': [x.decode() for x in episode['setup/task_goal'][()]],
            'highlight_ids': values['objects.highlight_ids'],
            'highlight_count': values['objects.highlight_count'],
            'n_cubes': values['objects.n_cubes_spawned'],
            'transitions': transitions,
            'last_completed': bool(last['info/is_completed'][()]),
            'last_gripper_closed': bool(last['obs/is_gripper_close'][()]),
            'last_eef': last['obs/eef_state'][()].tolist(),
        }
        visual = {}
        angles = np.linspace(0, 2*np.pi, 180, endpoint=False)
        intrinsic = episode['setup/front_camera_intrinsic'][()]
        for idx in (0, 11, 50, 100, 101):
            frame = episode[f'timestep_{idx}/obs/front_rgb'][()]
            extrinsic = episode[f'timestep_{idx}/obs/front_camera_extrinsic'][()]
            cube_scores = []
            for cube_id in range(values['objects.n_cubes_spawned']):
                cx, cy, _ = values[f'layout.cubes.{cube_id}']
                points = np.concatenate([np.stack((cx+radius*np.cos(angles), cy+radius*np.sin(angles), np.full_like(angles, .01), np.ones_like(angles))) for radius in (.039,.043,.047)], axis=1)
                pix = intrinsic @ extrinsic @ points
                uv = np.rint((pix[:2]/pix[2:]).T).astype(int)
                uv = uv[(uv[:,0]>=0)&(uv[:,0]<256)&(uv[:,1]>=0)&(uv[:,1]<256)]
                rgb = frame[uv[:,1],uv[:,0]].astype(float)
                white = (rgb.min(axis=1)>195)&(np.ptp(rgb,axis=1)<25)
                cube_scores.append(round(float(white.mean()),4))
            visual[str(idx)] = cube_scores
        row['projected_ring_white_fraction'] = visual
        records.append(row)
        col = int(item['difficulty'][-1]) - 1
        rr = [0, 3, 6].index(item['episode'])
        sheet.paste(Image.fromarray(episode['timestep_50/obs/front_rgb'][()]), (col*256, rr*278+22))
        draw.text((col*256+4, rr*278+3), f"{item['difficulty']} ep{item['episode']} t50 targets={values['objects.highlight_ids']}", fill='black')
        if item['episode'] == 0:
            indices = [0, 11, 50, 100, 101, len(steps)-1]
            strip = Image.new('RGB', (6*256, 278), 'white')
            sd = ImageDraw.Draw(strip)
            for i, idx in enumerate(indices):
                strip.paste(Image.fromarray(episode[f'timestep_{idx}/obs/front_rgb'][()]), (i*256, 22))
                sd.text((i*256+4, 3), f"{item['difficulty']} ep0 t{idx}", fill='black')
            strip.save(OUT / f"{item['difficulty']}-ep0-frames.png")
sheet.save(OUT / 'all-12-t50.png')
(OUT / 'existing-summary.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n')
for row in records:
    presses = [x for x in row['transitions'] if x['label'] == 'press the button']
    picks = [x for x in row['transitions'] if x['label'].startswith('pick up')]
    print(row['difficulty'], row['episode'], 'frames', row['frames'], 'button_segments', len(presses),
          'picks', len(picks), 'goals', len(row['task_goals']), 'last', row['transitions'][-1],
          'completed', row['last_completed'], 'closed', row['last_gripper_closed'])
print('PH_EXISTING_READ=PASS episodes='+str(len(records))+' new_resets=0 new_rollouts=0')
for row in records:
    ids = row['highlight_ids']
    visual = row['projected_ring_white_fraction']
    target = [visual['50'][i] for i in ids]
    distractor = [visual['50'][i] for i in range(row['n_cubes']) if i not in ids]
    print('PH_RING',row['difficulty'],row['episode'],'target_min',min(target),'distractor_max',max(distractor),
          'before_max',max(visual['0']),'after_max',max(visual['101']))
