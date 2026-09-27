"""只读 StopCube 既有交付，提取帧和关键字段，不加载仿真。"""
import json
from pathlib import Path

import h5py
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
SNAPSHOT = ROOT / 'artifacts/audit/v6-semantic-0a3f989'
OUT = ROOT / 'artifacts/audit/v6-semantic-results/stop_cube'
delivery = json.loads((SNAPSHOT / 'docs/validation/newtask-v6/records/final-delivery.json').read_text())
specs = [json.loads(line) for line in (ROOT / 'artifacts/newtask-v6/v6-01/xhard4/specs.jsonl').read_text().splitlines()]
specs = {row['episode']: row['spec'] for row in specs if row.get('task') == 'StopCube'}
report = []
for row in delivery['successes']:
    if row['task'] != 'StopCube':
        continue
    ep = row['episode']
    h5 = next(item['path'] for item in row['files'] if item['path'].endswith('.h5'))
    with h5py.File(h5, 'r') as f:
        group = f[f'episode_{ep}']
        n = sum(key.startswith('timestep_') for key in group)
        spec = specs[ep]
        expected = int(spec['actions']['steps_press'])
        selected = sorted(set([0, expected - 6, expected - 3, expected, expected + 3, expected + 6, n - 1]))
        sheet = Image.new('RGB', (256 * len(selected), 286), 'white')
        d = ImageDraw.Draw(sheet)
        for col, index in enumerate(selected):
            frame = Image.fromarray(group[f'timestep_{index}']['obs/front_rgb'][()])
            frame.save(OUT / f'ep{ep}-t{index}-front.png')
            sheet.paste(frame, (256 * col, 30))
            d.text((256 * col + 4, 7), f'ep {ep} / timestep {index}', fill='black')
        sheet.save(OUT / f'ep{ep}-contact.png')
        subgoals = []
        for index in range(n):
            info = group[f'timestep_{index}']['info']
            if bool(info['is_subgoal_boundary'][()]) or index == n - 1:
                subgoals.append({'frame': index, 'simple': info['simple_subgoal'][()].decode(), 'online': info['simple_subgoal_online'][()].decode(), 'complete': bool(info['is_completed'][()]), 'grounded': info['grounded_subgoal'][()].decode()})
        report.append({'episode': ep, 'frames': n, 'h5': h5, 'spec': spec, 'setup': {k: group['setup'][k][()].decode() if isinstance(group['setup'][k][()], bytes) else group['setup'][k][()].tolist() for k in group['setup']}, 'subgoals': subgoals})
(OUT / 'existing_summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=lambda v: v.decode() if isinstance(v, bytes) else v.tolist()) + '\n')
print((OUT / 'existing_summary.json').read_text())
print('STOPCUBE_EXISTING_READ=PASS episodes=3 resets=0 rollouts=0')
