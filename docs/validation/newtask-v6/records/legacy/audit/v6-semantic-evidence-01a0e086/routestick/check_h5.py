"""只读核验现有 RouteStick 数据，不导入仿真源码。"""
import json
from pathlib import Path
import h5py
import numpy as np
from PIL import Image, ImageDraw

root = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
base = root / 'artifacts/newtask-v6'
out = Path(__file__).parent
cat = json.loads((base / 'site-v9/catalog.json').read_text())
media = json.loads((base / 'site-v9/media-private.json').read_text())
rows, pics = [], []
for tier in next(t for t in cat['tasks'] if t['id'] == 'RouteStick')['tiers']:
    for video in tier['videos']:
        path = Path(media[video['id']])
        files = list((path.parent.parent / 'hdf5_files').glob('*.h5'))
        assert len(files) == 1
        with h5py.File(files[0], 'r') as handle:
            ep = handle[next(iter(handle))]
            n = sum(k.startswith('timestep_') for k in ep)
            xyz, labels, demos, boundaries = [], [], [], []
            for i in range(n):
                t = ep[f'timestep_{i}']
                xyz.append(t['obs/eef_state'][()][:3])
                labels.append(t['info/grounded_subgoal'][()].decode())
                demos.append(bool(t['info/is_video_demo'][()]))
                if bool(t['info/is_subgoal_boundary'][()]) and not bool(t['info/is_completed'][()]):
                    boundaries.append(i)
            xyz = np.array(xyz)
            segments = []
            for j, a in enumerate(boundaries):
                b = boundaries[j + 1] if j + 1 < len(boundaries) else n
                pts = xyz[a:b]
                vec = pts[-1, :2] - pts[0, :2]
                rel = pts[:, :2] - pts[0, :2]
                cross = vec[0] * rel[:, 1] - vec[1] * rel[:, 0]
                direction = 'counterclockwise' if cross.mean() < 0 else 'clockwise'
                segments.append(dict(start=a, end=b, n=b-a, demo=demos[a], label=labels[a], direction=direction,
                    direction_match=direction == labels[a].split()[-1],
                    side_match=bool(('left' in labels[a]) == (vec[1] > 0)),
                    cross_mean=float(cross.mean()), peak_lateral=float(np.max(np.abs(cross)) / np.linalg.norm(vec)),
                    z_min=float(pts[:, 2].min()), z_max=float(pts[:, 2].max())))
            ds = [s for s in segments if s['demo']]
            es = [s for s in segments if not s['demo']]
            row = dict(tier=tier['id'], h5=str(files[0]), video=str(path), frames=n,
                demo_segments=len(ds), exec_segments=len(es), all_50=all(s['n'] == 50 for s in segments),
                direction_all=all(s['direction_match'] for s in segments), side_all=all(s['side_match'] for s in segments),
                paired_labels=[s['label'] for s in ds] == [s['label'] for s in es],
                z_min=float(xyz[:, 2].min()), z_max=float(xyz[:, 2].max()), segments=segments)
            rows.append(row)
            if video == tier['videos'][0]:
                for frame in (0, 24, 49, n // 2, n // 2 + 24, n // 2 + 49):
                    rgb = ep[f'timestep_{frame}']['obs/front_rgb'][()]
                    pic = Image.new('RGB', (256, 280), 'white')
                    pic.paste(Image.fromarray(rgb), (0, 24))
                    ImageDraw.Draw(pic).text((4, 4), f'{tier["id"]} frame={frame}', fill='black')
                    pics.append(pic)
(out / 'offline-h5.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
canvas = Image.new('RGB', (256 * 6, 280 * 5), 'white')
for i, pic in enumerate(pics):
    canvas.paste(pic, (i % 6 * 256, i // 6 * 280))
canvas.save(out / 'frames.jpg')
print('ROUTE_H5=PASS', 'episodes=', len(rows), 'segments=', sum(len(r['segments']) for r in rows),
      'all_checks=', all(r['all_50'] and r['direction_all'] and r['side_all'] and r['paired_labels'] for r in rows),
      'z_min=', min(r['z_min'] for r in rows), 'z_max=', max(r['z_max'] for r in rows))
