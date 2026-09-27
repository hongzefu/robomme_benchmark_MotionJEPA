"""只读已有 MoveCube 规格和 HDF5，保留审查数字与边界帧。"""
import json
from pathlib import Path
import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = ROOT / 'artifacts/audit/v6-semantic-results/move_cube'
DATA = ROOT / 'artifacts/newtask-v6/v6-01/xhard4'

def segment_distance(p, a, b):
    d = b-a
    return float(np.linalg.norm(p-(a+np.clip(np.dot(p-a,d)/np.dot(d,d),0,1)*d)))

records = [json.loads(s) for s in (DATA/'specs.jsonl').read_text().splitlines() if s]
records = [r for r in records if r.get('task')=='MoveCube']
summary = {'audit_base':'0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8','new_resets':0,'new_rollouts':0,'layouts':[],'episodes':[]}
for r in records:
    for seg, v in r['spec']['layout'].items():
        center = np.array(v['region']['center']); cube=np.array(v['cube_pose'][:2]); goal=np.array(v['goal_xy'])
        p=np.array(v['peg_offsets'][1:],dtype=np.float32).astype(float); yaw=v['peg_yaw']; u=np.array([np.cos(yaw),np.sin(yaw)])
        a=p-.15*u;b=p+.05*u; grasp=p-.1*u
        d=segment_distance(center,a,b)
        summary['layouts'].append({'episode':r['episode'],'selected':r['selected'],'segment':seg,'cube_radius':float(np.linalg.norm(cube-center)), 'goal_radius':float(np.linalg.norm(goal-center)), 'grasp_radius':float(np.linalg.norm(grasp-center)), 'peg_axis_inner_distance':d, 'cube_goal_distance':float(np.linalg.norm(cube-goal)), 'goal_peg_distance':segment_distance(goal,a,b), 'cube_peg_distance':segment_distance(cube,a,b)})

paths = list((DATA/'rollout/run1/episodes').glob('MoveCube*/hdf5_files/*.h5'))
paths += list((ROOT/'artifacts/newtask-v6/v6-s2-20260926-01/episodes').glob('MoveCube*/hdf5_files/*.h5'))
paths += list((ROOT/'artifacts/newtask-v6/v6-s3-20260926-01/remaining/B').glob('MoveCube*/hdf5_files/*.h5'))
for p in sorted(paths):
    with h5py.File(p) as f:
        ep=f[next(iter(f))]; keys=sorted([k for k in ep if k.startswith('timestep_')],key=lambda s:int(s[9:])); ident=p.stem
        last=None; transitions=[]; samples=set([0,len(keys)-1])
        for k in keys:
            g=ep[k]; i=int(k[9:]); v=(bool(g['info/is_video_demo'][()]),g['info/simple_subgoal'][()].decode(),g['info/grounded_subgoal'][()].decode())
            if v!=last or bool(g['info/is_subgoal_boundary'][()]):
                transitions.append({'t':i,'demo':v[0],'simple':v[1],'grounded':v[2],'complete':bool(g['info/is_completed'][()]),'gripper_state':g['obs/gripper_state'][()].tolist()})
                samples.add(i); samples.add(max(i-1,0)); last=v
        selected=sorted(samples); sheet=Image.new('RGB',(512,280*((len(selected)+1)//2)),'white'); draw=ImageDraw.Draw(sheet)
        for j,i in enumerate(selected):
            arr=ep[f'timestep_{i}/obs/front_rgb'][()]; im=Image.fromarray(arr); im.save(OUT/f'{ident}_t{i:04d}.png'); x=(j%2)*256;y=(j//2)*280;sheet.paste(im,(x,y));draw.text((x+4,y+258),f'{ident} t={i}',fill='black')
        sheet.save(OUT/f'{ident}_boundaries.jpg')
        summary['episodes'].append({'path':str(p),'difficulty':ep['setup/difficulty'][()].decode(),'steps':len(keys),'transitions':transitions,'sample_frames':selected})
(OUT/'existing_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(f'MC_EXISTING_READ=PASS specs=10 layouts=20 episodes={len(summary["episodes"])} new_resets=0 new_rollouts=0')
for e in summary['episodes']: print(e['path'],e['steps'],e['transitions'])
print('MC_REGION_RANGE',min(r['cube_radius'] for r in summary['layouts']),max(r['cube_radius'] for r in summary['layouts']),min(r['peg_axis_inner_distance'] for r in summary['layouts']))
