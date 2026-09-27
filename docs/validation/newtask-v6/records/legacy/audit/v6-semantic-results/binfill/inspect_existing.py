"""只读核对固定版本 BinFill 现有正式产物，不导入环境、不重跑仿真。"""
from pathlib import Path
import json
import re
import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-results/binfill'
BASE = '0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8'
SNAP = ROOT / 'artifacts/audit/v6-semantic-0a3f989'
manifest = json.loads((SNAP / 'docs/validation/newtask-v6/records/final-delivery.json').read_text())
selected = [r for r in manifest['successes'] if r['task'] == 'BinFill']
specs = {}
candidate_checks = []
for tier in range(1, 5):
    path = ROOT / f'artifacts/newtask-v6/v6-01/xhard{tier}/specs.jsonl'
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row.get('task') != 'BinFill':
            continue
        specs[(row['difficulty'], row['episode'])] = row['spec']
        obj = row['spec']['objects']
        candidate_checks.append(dict(tier=row['difficulty'], episode=row['episode'],
                                     targets=obj['target_numbers'], spawn=obj['spawn_numbers'],
                                     actual=obj['spawn_actual'], dynamic=row['spec']['layout']['dynamic'],
                                     mix_max=obj['color_mix_max_component'], fallback=obj['color_mix_fallback']))

report = dict(audit_base=BASE, candidate_checks=candidate_checks, episodes=[])
panels = []
for row in selected:
    spec = specs[(row['difficulty'], row['episode'])]
    h5path = Path(next(f['path'] for f in row['files'] if f['path'].endswith('.h5')))
    board = np.asarray(spec['layout']['board']['offsets'][:2]) + [.15, 0]
    drops = []
    with h5py.File(h5path, 'r') as f:
        ep = f[f'episode_{row["episode"]}']
        names = sorted((n for n in ep if n.startswith('timestep_')), key=lambda n:int(n[9:]))
        phrases = [s.decode() for s in ep['setup/task_goal'][()]]
        K = ep['setup/front_camera_intrinsic'][()]
        ki = np.linalg.inv(K)
        phases = []
        demo_count = 0
        for name in names:
            t = ep[name]
            sg = t['info/simple_subgoal'][()].decode()
            demo_count += int(t['info/is_video_demo'][()])
            if not phases or phases[-1]['subgoal'] != sg:
                phases.append(dict(start=int(name[9:]), subgoal=sg))
        for n, phase in enumerate(phases):
            if phase['subgoal'] != 'put it into the bin':
                continue
            previous = phases[n-1]['subgoal']
            color = re.search(r'(red|blue|green) cube', previous).group(1)
            channel = dict(red=0, green=1, blue=2)[color]
            stop = phases[n+1]['start'] if n+1<len(phases) else len(names)
            visible = []
            last_points = None
            for i in range(phase['start'], stop):
                t = ep[f'timestep_{i}']
                rgb = t['obs/front_rgb'][()].astype(np.float32)
                others = [c for c in range(3) if c != channel]
                mask = (rgb[:,:,channel] > 45) & (rgb[:,:,channel] > 1.8*rgb[:,:,others[0]]) & (rgb[:,:,channel] > 1.8*rgb[:,:,others[1]])
                yy,xx = np.nonzero(mask)
                depth = t['obs/front_depth'][()][:,:,0][yy,xx].astype(np.float64)/1000
                E = t['obs/front_camera_extrinsic'][()]
                pts = (np.linalg.inv(E[:,:3]) @ ((ki @ np.stack([xx,yy,np.ones_like(xx)]))*depth - E[:,3,None])).T
                at_bin = (np.linalg.norm(pts[:,:2] - board,axis=1)<.065) & (pts[:,2]>.07)
                count = int(at_bin.sum())
                visible.append([i,count])
                if count >= 15:
                    last_points = pts[at_bin]
            positive = [a for a in visible if a[1]>=15]
            last = positive[-1][0] if positive else None
            disappeared = last is not None and last<stop-2 and all(count<15 for i,count in visible if i>last)
            item = dict(subgoal_before=previous, start=phase['start'], stop=stop, color=color,
                        last_visible=last, disappeared=disappeared,
                        last_surface_z_minmax=None if last_points is None else [float(last_points[:,2].min()),float(last_points[:,2].max())],
                        visible_counts=visible)
            drops.append(item)
            if len(drops)==1 and last is not None:
                panels.append((row['difficulty'],row['episode'],last, ep[f'timestep_{last}']['obs/front_rgb'][()], ep[f'timestep_{last+1}']['obs/front_rgb'][()]))
        report['episodes'].append(dict(difficulty=row['difficulty'], episode=row['episode'],seed=row['seed'],path=str(h5path),
            target_counts=spec['objects']['target_numbers'],phrases=phrases, frames=len(names),demo_frames=demo_count,
            final_complete=bool(ep[names[-1]]['info/is_completed'][()]), phases=phases, drops=drops))

canvas=Image.new('RGB',(512,280*len(panels)), 'white')
draw=ImageDraw.Draw(canvas)
for i,(tier,ep,t,before,after) in enumerate(panels):
    canvas.paste(Image.fromarray(before),(0,i*280))
    canvas.paste(Image.fromarray(after),(256,i*280))
    draw.text((5,i*280+257),f'{tier} ep{ep}: t={t} -> t={t+1}',fill='black')
canvas.save(OUT/'all-first-drops.png')
(OUT/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
all_drops=[d for e in report['episodes'] for d in e['drops']]
print('BINFILL_EXISTING_SCAN=PASS episodes='+str(len(selected))+' candidates='+str(len(candidate_checks))+' drops='+str(len(all_drops)))
print('BINFILL_EARLY_DISAPPEAR=FAIL observed='+str(sum(d['disappeared'] for d in all_drops))+'/'+str(len(all_drops)))
print('surface_z_min_range=',min(d['last_surface_z_minmax'][0] for d in all_drops if d['disappeared']),max(d['last_surface_z_minmax'][0] for d in all_drops if d['disappeared']))
for e in report['episodes']:
    print(e['difficulty'],e['episode'],e['frames'],len(e['drops']),sum(d['disappeared'] for d in e['drops']), e['demo_frames'], e['final_complete'])
