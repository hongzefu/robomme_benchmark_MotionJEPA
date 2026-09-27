"""只读核对固定交付清单中的 VideoUnmask 既有轨迹，并抽取真实观测证据。"""
import json
from pathlib import Path
import re

import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-results/video_unmask'
BASE = ROOT / 'artifacts/audit/v6-semantic-0a3f989'
delivery = json.loads((BASE / 'docs/validation/newtask-v6/records/final-delivery.json').read_text())
paths = [(next(Path(f['path']) for f in row['files'] if f['path'].endswith('.h5')), '正式交付')
         for row in delivery['successes'] if row['task'] == 'VideoUnmask']
paths += [(p, '原三档对照') for p in sorted((ROOT / 'artifacts/newtask-v6/v6-s3-20260926-01/remaining/B').glob('VideoUnmask_episode_*/hdf5_files/*.h5'))]
specs = {}
for f in (ROOT / 'artifacts/newtask-v6/v6-01').glob('*/specs.jsonl'):
    for line in f.read_text().splitlines():
        row = json.loads(line)
        if row.get('task') == 'VideoUnmask':
            specs[(row['difficulty'], row['seed'])] = row['spec']

def val(dataset):
    x = dataset[()]
    if isinstance(x, bytes):
        return x.decode()
    if isinstance(x, np.ndarray):
        return [v.decode() if isinstance(v, bytes) else v.item() if hasattr(v, 'item') else v for v in x]
    return x.item() if hasattr(x, 'item') else x

results = []
for path, kind in paths:
    with h5py.File(path, 'r') as h:
        ep = h[next(iter(h))]
        difficulty = val(ep['setup/difficulty'])
        seed = val(ep['setup/seed'])
        goal = val(ep['setup/task_goal'])
        keys = sorted([k for k in ep if k.startswith('timestep_')], key=lambda k:int(k.split('_')[-1]))
        changes, last = [], None
        for key in keys:
            t = ep[key]
            state = (val(t['info/simple_subgoal']), val(t['info/is_video_demo']))
            if state != last:
                changes.append({'frame': int(key.split('_')[-1]), 'subgoal': state[0], 'demo': state[1],
                                'grounded': val(t['info/grounded_subgoal'])})
                last = state
        indices = sorted(set([0, 1, 16, 31, 32, 33, 64, 65, len(keys)-1] +
                             [max(0,c['frame']-1) for c in changes[1:]] + [c['frame'] for c in changes[1:]]))
        indices = [i for i in indices if i < len(keys)]
        title = f'{difficulty} seed={seed} T={len(keys)}'
        cols = 6
        board = Image.new('RGB', (cols*256, ((len(indices)+cols-1)//cols)*284+35), 'white')
        draw = ImageDraw.Draw(board)
        draw.text((5,5), title, fill='black')
        for n,i in enumerate(indices):
            t=ep[f'timestep_{i}']
            arr=t['obs/front_rgb'][()]
            x,y=(n%cols)*256,(n//cols)*284+35
            board.paste(Image.fromarray(arr),(x,y+22))
            draw.text((x+3,y), f't={i} demo={int(val(t["info/is_video_demo"]))}', fill='black')
        imagepath = OUT / f'{difficulty}_{seed}_front.png'
        board.save(imagepath)
        target_sequence = [re.search(r'hides the (\w+) cube', c['subgoal']).group(1)
                           for c in changes if 'hides the ' in c['subgoal']]
        goal_sequence = re.findall(r'hiding the (\w+) cube', str(goal))
        record = {'h5':str(path), 'kind':kind,'difficulty':difficulty,'seed':seed,'frames':len(keys),
                  'goal':goal,'subgoal_changes':changes,'goal_colors':goal_sequence,'pick_colors':target_sequence,
                  'goal_binding_equal':target_sequence==goal_sequence, 'terminal_success':val(ep[keys[-1]]['info/is_completed']),
                  'keyframe_indices':indices, 'image':str(imagepath)}
        spec=specs.get((difficulty,seed))
        if spec:
            record['spec_colors']=[['red','green','blue'][i] for i in spec['objects']['color_order']]
            record['distractor_colors']=spec['objects']['distractors']['cube_colors']
            record['layout_bins']=spec['layout']['bins']
        results.append(record)
        print(title,'goal_binding_equal=',record['goal_binding_equal'],'complete=',record['terminal_success'],flush=True)
(OUT/'evidence.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print('VIDEO_UNMASK_EXISTING=PASS episodes='+str(len(results))+' new_reset=0 new_rollout=0')
