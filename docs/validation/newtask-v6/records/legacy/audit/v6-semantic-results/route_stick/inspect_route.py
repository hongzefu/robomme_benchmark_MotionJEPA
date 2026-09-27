"""只读既有 RouteStick 规格与 HDF5，检查轨迹与文本语义，不创建仿真。"""
import json
import math
from pathlib import Path

import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-results/route_stick'
OUT.mkdir(parents=True, exist_ok=True)
rows = []
frames = []
spec_summary = []
for tier in ('xhard1', 'xhard2', 'xhard3', 'xhard4'):
    base = ROOT / 'artifacts/newtask-v6/v6-01' / tier
    specs = [json.loads(x) for x in (base / 'specs.jsonl').read_text().splitlines()]
    specs = {x['episode']: x for x in specs if x.get('task') == 'RouteStick'}
    spec_summary.append({'tier': tier, 'candidates': len(specs), 'L': [x['spec']['objects']['L'] for x in specs.values()]})
    for file in sorted((base / 'rollout/run1/episodes').glob('RouteStick_episode_*/hdf5_files/*.h5')):
        ep = int(file.parent.parent.name.rsplit('_', 1)[-1])
        spec = specs[ep]['spec']
        n = spec['objects']['L']
        nodes = spec['actions']['nodes']
        directions = [spec['actions']['directions'][str(i)] for i in range(n)]
        angle = math.radians(spec['layout']['rotation_deg'])
        rot = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        targets = np.array([[-0.1, (i-4)*0.07] for i in range(9)]) @ rot.T
        with h5py.File(file, 'r') as f:
            g = f[f'episode_{ep}']
            count = len(g) - 1
            xyz = np.array([g[f'timestep_{i}/obs/eef_state'][()][:3] for i in range(count)])
            demo = np.array([g[f'timestep_{i}/info/is_video_demo'][()] for i in range(count)])
            bounds = [i for i in range(count) if g[f'timestep_{i}/info/is_subgoal_boundary'][()]]
            labels = [g[f'timestep_{i}/info/grounded_subgoal'][()].decode() for i in range(count)]
            completed = bool(g[f'timestep_{count-1}/info/is_completed'][()])
            intrinsic = g['setup/front_camera_intrinsic'][()]
            ext = g['timestep_0/obs/front_camera_extrinsic'][()]
            projected = (xyz @ ext[:, :3].T + ext[:, 3]) @ intrinsic.T
            projected = projected[:, :2] / projected[:, 2:]
            segments = []
            for phase in (0, 1):
                for i in range(n):
                    a, b = (phase*n+i)*50, (phase*n+i+1)*50
                    points = xyz[a:b]
                    start, end = targets[nodes[i]], targets[nodes[i+1]]
                    vec = end-start
                    rel = points[:, :2] - start
                    cross = vec[0]*rel[:, 1]-vec[1]*rel[:, 0]
                    got = 'clockwise' if cross.mean() > 0 else 'counterclockwise'
                    left = 'left' if end[1] > start[1] else 'right'
                    expected = f'move to the nearest {left} target by circling around the stick {directions[i]}'
                    center = (start+end)/2
                    polar = np.unwrap(np.arctan2(points[:, 1]-center[1], points[:, 0]-center[0]))
                    # 障碍杆在未旋转坐标系中的半长为 x=0.03、y=0.015；此处仅计算 TCP 点，不代替杆身碰撞。
                    local = (points[:, :2]-center) @ rot
                    tcp_inside_box = (np.abs(local[:, 0]) < .03) & (np.abs(local[:, 1]) < .015) & (points[:, 2] < .1)
                    segments.append({'phase': 'demo' if phase == 0 else 'execute', 'segment': i, 'frames': [a,b-1], 'nodes': nodes[i:i+2], 'expected': directions[i], 'actual_cross_direction': got, 'polar_delta': float(polar[-1]-polar[0]), 'label_mismatch_frames': sum(x != expected for x in labels[a:b]), 'target_end_error_m': float(np.linalg.norm(points[-1,:2]-end)), 'target_start_error_m': float(np.linalg.norm(points[0,:2]-start)), 'cross_mean': float(cross.mean()), 'tcp_inside_obstacle_frames': int(tcp_inside_box.sum()), 'z_min': float(points[:,2].min()), 'z_max': float(points[:,2].max())})
            row = {'tier': tier, 'episode': ep, 'file': str(file), 'L': n, 'frames': count, 'expected_frames': 100*n, 'demo_frames': int(demo.sum()), 'boundary_count': len(bounds), 'boundary_frames': bounds, 'completed': completed, 'image_tcp_bounds': [projected.min(axis=0).tolist(), projected.max(axis=0).tolist()], 'segments': segments}
            rows.append(row)
            if ep == 0:
                for index in (0, 12, 24, 36, 49, 50, n*50, n*50+24):
                    image = Image.fromarray(g[f'timestep_{index}/obs/front_rgb'][()])
                    frames.append((tier, index, labels[index], image))
                # 单独保留首段原始观测，不做图片修改。
                for index in (0, 12, 24, 36, 49):
                    Image.fromarray(g[f'timestep_{index}/obs/front_rgb'][()]).save(OUT / f'{tier}_ep0_f{index}.png')

summary = {'sha': '0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8', 'candidate_coverage': spec_summary, 'episode_count': len(rows), 'segment_count': sum(len(x['segments']) for x in rows), 'direction_mismatches': sum(s['expected'] != s['actual_cross_direction'] for r in rows for s in r['segments']), 'label_mismatch_frames': sum(s['label_mismatch_frames'] for r in rows for s in r['segments']), 'tcp_inside_obstacle_frames': sum(s['tcp_inside_obstacle_frames'] for r in rows for s in r['segments']), 'max_target_end_error_m': max(s['target_end_error_m'] for r in rows for s in r['segments']), 'episodes': rows}
(OUT / 'route_observations.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n')
sheet = Image.new('RGB', (256*8, 298*4), 'white')
draw = ImageDraw.Draw(sheet)
for j,(tier,index,label,pic) in enumerate(frames):
    x,y = (j%8)*256, (j//8)*298
    sheet.paste(pic,(x,y)); draw.text((x+4,y+259),f'{tier} ep0 frame={index}',fill='black')
    draw.text((x+4,y+275),label.replace('move to the nearest ','').replace(' target by circling around the stick ',' / '),fill='black')
sheet.save(OUT/'route_front_samples.png')
print(json.dumps({k:v for k,v in summary.items() if k!='episodes'},ensure_ascii=False,indent=2))
for r in rows:
    print(r['tier'],r['episode'],'L=',r['L'],'frames=',r['frames'],'demo=',r['demo_frames'],'boundary=',r['boundary_count'],'completed=',r['completed'],'end_error=',max(s['target_end_error_m'] for s in r['segments']))
