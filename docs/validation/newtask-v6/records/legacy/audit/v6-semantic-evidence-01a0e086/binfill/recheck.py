"""只读既有交付 HDF5，复核 BinFill 孔上方悬空消失；不导入或启动仿真。"""
import json
from pathlib import Path
import h5py
import numpy as np

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
manifest = json.loads((ROOT / 'artifacts/newtask-v6/s4-launch/verification/final-delivery.json').read_text())
all_events = []
for row in manifest['successes']:
    if row['task'] != 'BinFill':
        continue
    paths = [item['path'] for item in row['files']]
    trace = json.loads(Path(next(p for p in paths if p.endswith('rng_trace.json'))).read_text())
    offsets = next(x['drawn'] for x in trace['calls'] if x['path'] == 'layout.board.offsets')
    board = np.array([0.15 + offsets[0], offsets[1]])
    events = []
    with h5py.File(next(p for p in paths if p.endswith('.h5')), 'r') as f:
        e = f[f"episode_{row['episode']}"]
        ki = np.linalg.inv(e['setup/front_camera_intrinsic'][()])
        changes, prev = [], None
        for i in range(len(e) - 1):
            s = e[f'timestep_{i}/info/simple_subgoal_online'][()].decode()
            if s != prev:
                changes.append((i, s))
                prev = s
        for j in range(1, len(changes) - 1):
            if changes[j][1] != 'put it into the bin':
                continue
            color = next(c for c in ['red', 'blue', 'green'] if c in changes[j - 1][1])
            ch = {'red': 0, 'green': 1, 'blue': 2}[color]
            end = changes[j + 1][0]
            samples = []
            for ti in range(max(0, end - 12), end + 1):
                g = e[f'timestep_{ti}/obs']
                rgb = g['front_rgb'][()].astype(float)
                depth = g['front_depth'][()][:, :, 0].astype(float) / 1000
                ext = g['front_camera_extrinsic'][()]
                other = np.max(rgb[:, :, [c for c in range(3) if c != ch]], axis=2)
                v, u = np.nonzero((rgb[:, :, ch] > 45) & (rgb[:, :, ch] > other * 1.6))
                cam = (ki @ np.vstack([u, v, np.ones(len(u))])) * depth[v, u]
                world = (ext[:, :3].T @ (cam - ext[:, 3, None])).T
                selected = (np.linalg.norm(world[:, :2] - board, axis=1) < 0.07) & (world[:, 2] > 0.07) & (world[:, 2] < 0.35)
                visible = world[selected]
                samples.append((ti, len(visible), float(np.median(visible[:, 2])) if len(visible) else None))
            hits = [k for k in range(len(samples) - 1) if samples[k][1] >= 8 and samples[k + 1][1] < samples[k][1] * 0.2]
            events.append(samples[hits[-1]] if hits else None)
    print(row['difficulty'], row['episode'], '投放', len(events), '悬空像素突降', sum(x is not None for x in events))
    all_events.extend(events)
heights = [x[2] for x in all_events if x is not None]
print(f'BINFILL_AIR_DISAPPEAR=CONFIRMED drops={len(all_events)} matched={len(heights)} surface_median_z_min={min(heights):.9f} surface_median_z_max={max(heights):.9f} board_top_z=0.05')
