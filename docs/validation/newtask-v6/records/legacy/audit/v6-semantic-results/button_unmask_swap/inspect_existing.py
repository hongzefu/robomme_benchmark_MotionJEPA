"""只读检查既有 ButtonUnmaskSwap 数据；不导入环境、不生成轨迹。"""
import json
import pathlib
import re

import h5py
from PIL import Image, ImageDraw

ROOT = pathlib.Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = pathlib.Path(__file__).parent
SNAP = ROOT / 'artifacts/audit/v6-semantic-0a3f989'
manifest = json.loads((SNAP / 'docs/validation/newtask-v6/records/final-delivery.json').read_text())
items = [r for r in manifest['successes'] if r['task'] == 'ButtonUnmaskSwap']
specs = {}
for tier in range(1, 5):
    for line in (ROOT / f'artifacts/newtask-v6/v6-01/xhard{tier}/specs.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row.get('record') == 'spec' and row.get('task') == 'ButtonUnmaskSwap':
            specs[(row['difficulty'], row['episode'])] = row

paths = [(r['difficulty'], r['episode'], pathlib.Path(next(f['path'] for f in r['files'] if f['path'].endswith('.h5')))) for r in items]
for p in sorted((ROOT / 'artifacts/newtask-v6/v6-s3-20260926-01/combined/B').glob('ButtonUnmaskSwap_episode_*/hdf5_files/*.h5')):
    with h5py.File(p, 'r') as h:
        e = h[next(iter(h))]
        difficulty = e['setup/difficulty'][()].decode()
        episode = int(next(iter(h)).split('_')[-1])
    paths.append((difficulty, episode, p))

results = []
for difficulty, episode, path in paths:
    with h5py.File(path, 'r') as h:
        e = h[next(iter(h))]
        ts = sorted(int(x.split('_')[1]) for x in e if x.startswith('timestep_'))
        transitions = []
        prev = None
        for t in ts:
            text = e[f'timestep_{t}/info/simple_subgoal'][()].decode()
            if text != prev:
                transitions.append({'t': t, 'text': text, 'grounded': e[f'timestep_{t}/info/grounded_subgoal'][()].decode()})
                prev = text
        goal = [x.decode() for x in e['setup/task_goal'][()]]
        last = e[f'timestep_{ts[-1]}']
        row = {'difficulty': difficulty, 'episode': episode, 'path': str(path), 'seed': int(e['setup/seed'][()]), 'steps': len(ts), 'goal': goal, 'transitions': transitions, 'completed': bool(last['info/is_completed'][()])}
        spec = specs.get((difficulty, episode))
        if spec:
            s = spec['spec']
            row['spec'] = s
            expected = [ ['red','green','blue'][i] for i in s['objects']['color_order'][:s['objects']['n_picks']] ]
            actual = [re.search(r'hides the (\w+) cube', t['text']).group(1) for t in transitions if 'hides the' in t['text']]
            row['pick_expected'] = expected
            row['pick_actual'] = actual
            row['pick_language_match'] = expected == actual
            row['swap_end'] = s['actions']['swap_window']['start_step'] + s['actions']['swap_window']['duration_steps'] * s['objects']['n_swaps']
        else:
            # 原档没有复用新档规格；只将 214 作为原档最长交换窗附近抽帧，不当作实测终点。
            row['swap_end'] = None
        end_sample = row['swap_end'] or 214
        sample_frames = sorted(set([0, 1, 16, 31, 32, 40, 63, 64, end_sample-1, end_sample] + [min(t['t']+25,ts[-1]) for t in transitions] + [ts[-1]]))
        sample_frames = [t for t in sample_frames if t in ts]
        sheet = Image.new('RGB', (4*256, ((len(sample_frames)+3)//4)*280), 'white')
        draw = ImageDraw.Draw(sheet)
        for idx, t in enumerate(sample_frames):
            x, y = (idx%4)*256, (idx//4)*280
            sheet.paste(Image.fromarray(e[f'timestep_{t}/obs/front_rgb'][()]), (x,y+24))
            draw.text((x+5,y+4), f'{difficulty} ep{episode} t={t}', fill='black')
        name = f'{difficulty}-ep{episode}.jpg'
        sheet.save(OUT/name, quality=88)
        row['sheet'] = str(OUT/name)
        picks = [(tr, transitions[i+1]['t'] if i+1<len(transitions) else ts[-1]) for i,tr in enumerate(transitions) if 'hides the' in tr['text']]
        pick_sheet = Image.new('RGB',(3*256,len(picks)*282),'white')
        pd = ImageDraw.Draw(pick_sheet)
        for i,(tr,end) in enumerate(picks):
            color = re.search(r'hides the (\w+) cube',tr['text']).group(1)
            for j,t in enumerate([max(tr['t'],end-12),end-1,min(end+2,ts[-1])]):
                pick_sheet.paste(Image.fromarray(e[f'timestep_{t}/obs/front_rgb'][()]),(j*256,i*282+26))
                pd.text((j*256+3,i*282+4),f'{difficulty} ep{episode} {color} t{t}',fill='black')
        pick_sheet.save(OUT/f'{difficulty}-ep{episode}-pick.jpg',quality=90)
        results.append(row)
(OUT/'inspection.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
for row in results:
    print(json.dumps({k:v for k,v in row.items() if k not in ('spec','sheet')}, ensure_ascii=False))
print(f'BUS_EXISTING_READ=PASS episodes={len(results)} generated=0')
