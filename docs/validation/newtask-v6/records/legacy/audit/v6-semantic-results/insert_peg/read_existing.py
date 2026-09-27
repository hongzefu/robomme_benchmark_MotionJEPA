"""只读取已有 InsertPeg HDF5，导出阶段边界与原始图像拼图。"""
from pathlib import Path
import json
import h5py
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-results/insert_peg'
ROOTS = [
    ROOT / 'artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes',
    ROOT / 'artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes',
    ROOT / 'artifacts/newtask-v6/v6-s3-20260926-01/remaining/B',
]
rows = []
for root in ROOTS:
    for path in sorted(root.glob('InsertPeg_episode_*/hdf5_files/*.h5')):
        with h5py.File(path, 'r') as h:
            if not list(h):
                rows.append({'path': str(path), 'empty': True})
                continue
            g = h[next(iter(h))]
            frames = sorted((int(k[9:]) for k in g if k.startswith('timestep_')))
            segments = []
            previous = None
            for idx in frames:
                t = g[f'timestep_{idx}']
                state = (bool(t['info/is_video_demo'][()]), t['info/simple_subgoal'][()].decode())
                if state != previous:
                    segments.append({'start': idx, 'demo': state[0], 'subgoal': state[1]})
                    previous = state
            for n, segment in enumerate(segments):
                segment['end'] = segments[n+1]['start']-1 if n+1 < len(segments) else frames[-1]
            chosen = [0, segments[0]['end'], segments[1]['end'], segments[2]['start'], segments[3]['start']+(segments[3]['end']-segments[3]['start'])//2, frames[-1]]
            sheet = Image.new('RGB', (768, 580), 'white')
            draw = ImageDraw.Draw(sheet)
            for n, idx in enumerate(chosen):
                image = Image.fromarray(g[f'timestep_{idx}/obs/front_rgb'][()])
                x, y = (n%3)*256, (n//3)*290
                sheet.paste(image, (x,y+32))
                draw.text((x+4,y+4), f'{path.stem} t={idx}', fill='black')
            image_path = OUT / f'{path.stem}.png'
            sheet.save(image_path)
            rows.append({'path':str(path),'difficulty':g['setup/difficulty'][()].decode(),'seed':int(g['setup/seed'][()]),'frames':len(frames),'completed':bool(g[f'timestep_{frames[-1]}/info/is_completed'][()]),'segments':segments,'image':str(image_path),'chosen_frames':chosen})
(OUT / 'existing-h5-summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(f'INSERTPEG_H5_SCAN=PASS files={len(rows)} nonempty={sum(not r.get("empty",False) for r in rows)} empty={sum(r.get("empty",False) for r in rows)}')
