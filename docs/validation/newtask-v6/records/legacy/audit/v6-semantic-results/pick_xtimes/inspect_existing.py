"""只读核查 PickXtimes 已有轨迹的任务边界与视觉帧。"""
import json
from pathlib import Path

import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
SNAP = ROOT / 'artifacts/audit/v6-semantic-0a3f989'
OUT = ROOT / 'artifacts/audit/v6-semantic-results/pick_xtimes'
delivery = json.loads((SNAP / 'docs/validation/newtask-v6/records/final-delivery.json').read_text())
rows = [r for r in delivery['successes'] if r['task'] == 'PickXtimes']
specs = {}
for tier in ['xhard1', 'xhard2', 'xhard3', 'xhard4']:
    for line in (SNAP / f'scripts/configs/newtask-v6/v6-01/{tier}/specs.jsonl').read_text().splitlines():
        r = json.loads(line)
        if r.get('task') == 'PickXtimes' and r.get('record') == 'spec':
            specs[(tier, r['episode'])] = r['spec']

reports = []
for row in rows:
    hp = next(f['path'] for f in row['files'] if f['path'].endswith('.h5'))
    spec = specs[(row['difficulty'], row['episode'])]
    obj = spec['objects']
    report = {k: row[k] for k in ['task','difficulty','episode','seed']}
    report.update(h5=hp, expected_repeats=obj['num_repeats'], target_color=obj['target_candidates'][obj['target_cube_idx']])
    with h5py.File(hp, 'r') as h:
        e = h[next(iter(h))]
        steps = sorted(int(k[9:]) for k in e if k.startswith('timestep_'))
        segments = []
        completed = []
        for n in steps:
            g = e[f'timestep_{n}']
            label = g['info/simple_subgoal'][()].decode()
            if not segments or segments[-1]['label'] != label:
                segments.append({'start': n, 'end': n, 'label': label})
            else:
                segments[-1]['end'] = n
            if g['info/is_completed'][()]:
                completed.append(n)
        for seg in segments:
            g = e[f"timestep_{seg['end']}"]
            seg['eef_last'] = g['obs/eef_state'][()].tolist()
            seg['gripper_last'] = g['obs/gripper_state'][()].tolist()
            seg['online_last'] = g['info/simple_subgoal_online'][()].decode()
        report.update(frames=len(steps), segments=segments, completed_frames=completed)
        tiles = [(0,'initial')] + [(seg['end'], seg['label']) for seg in segments]
        width = 256 * 5
        height = ((len(tiles) + 4) // 5) * 292
        canvas = Image.new('RGB', (width,height), 'white')
        dr = ImageDraw.Draw(canvas)
        for idx,(n,label) in enumerate(tiles):
            x,y = idx%5*256,idx//5*292
            canvas.paste(Image.fromarray(e[f'timestep_{n}/obs/front_rgb'][()]), (x,y))
            label = label.replace('pick up the ','pick ').replace(' cube for the ',' ').replace(' time','').replace('place the ','place ').replace(' cube onto the target',' on target')
            dr.text((x+2,y+258), f'{n}: {label[:39]}', fill='black')
        image_path = OUT / f"{row['difficulty']}_ep{row['episode']}_boundaries.jpg"
        canvas.save(image_path, quality=90)
        report['boundary_image'] = str(image_path)
    reports.append(report)
    print(json.dumps({k: report[k] for k in ['difficulty','episode','frames','expected_repeats','target_color']},ensure_ascii=False), 'segments=',len(segments),'completed=',completed[:2],completed[-2:])
(OUT / 'existing_summary.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2))
print('PICK_EXISTING_READ=PASS episodes=' + str(len(reports)))
