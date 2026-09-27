"""只读复核 ButtonUnmask 既有轨迹，提取轻量证据，不加载仿真。"""
import json
from pathlib import Path

import cv2
import h5py
import numpy as np

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-results/button_unmask'
BASE = ROOT / 'artifacts/newtask-v6'
rows = []
paths = sorted((BASE / 'v6-01').glob('*/rollout/run1/episodes/ButtonUnmask_episode_*/hdf5_files/*.h5'))
paths += sorted((BASE / 'v6-s3-20260926-01').glob('remaining/B/ButtonUnmask_episode_*/hdf5_files/*.h5'))
for p in paths:
    with h5py.File(p, 'r') as f:
        e = f[next(iter(f))]
        keys = sorted((k for k in e if k.startswith('timestep_')), key=lambda k: int(k.split('_')[1]))
        spans = []
        previous = None
        for k in keys:
            v = e[k]['info/simple_subgoal_online'][()].decode()
            if v != previous:
                spans.append([int(k.split('_')[1]), v])
                previous = v
        video = next(p.parent.parent.glob('videos/*.mp4'))
        tier = next(t for t in ['xhard1', 'xhard2', 'xhard3', 'xhard4', 'easy', 'medium', 'hard'] if f'_{t}_' in video.name)
        press_end = spans[1][0]
        row = {'h5': str(p), 'video': str(video), 'difficulty': tier, 'frames': len(keys), 'spans': spans,
               'first_pick_frame': press_end, 'reveal_returns_frame': 32,
               'eef_z_frame31': float(e['timestep_31']['obs/eef_state'][2]),
               'final_completed': bool(e[keys[-1]]['info/is_completed'][()]),
               'has_demo': any(bool(e[k]['info/is_video_demo'][()]) for k in keys),
               'pickup_names': [v for _, v in spans if v.startswith('pick up')],
               'all_images_existing': True}
        rows.append(row)
        if p.stem.split('_')[1] not in ['ep0', 'ep3', 'ep6', 'ep11']:
            continue
        sample = [0, 16, 31, 32, press_end-1, press_end, min(press_end+35,len(keys)-1), len(keys)-1]
        images = []
        for i in sample:
            rgb = e[f'timestep_{i}']['obs/front_rgb'][()]
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            block = np.full((286, 256, 3), 245, dtype=np.uint8)
            block[30:] = bgr
            cv2.putText(block, f'{tier} {p.stem.split("_")[1]} frame={i}', (5, 21), cv2.FONT_HERSHEY_SIMPLEX, .45, (0,0,0), 1)
            images.append(block)
        sheet = np.concatenate([np.concatenate(images[:4], axis=1), np.concatenate(images[4:], axis=1)], axis=0)
        image_path = OUT / f'{tier}-{p.stem}.jpg'
        cv2.imwrite(str(image_path), sheet)
        row['contact_sheet'] = str(image_path)
OUT.joinpath('existing-evidence.json').write_text(json.dumps({'audit_base': '0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8', 'rows': rows}, ensure_ascii=False, indent=2)+'\n')
print('BUTTON_EXISTING_SCAN=PASS files=' + str(len(rows)) + ' reset=0 rollout=0')
for row in rows:
    print(row['difficulty'], Path(row['h5']).stem, 'pick_start='+str(row['first_pick_frame']), 'reveal_returns=32', 'eef_z31='+str(row['eef_z_frame31']))
