import json, sys, numpy as np
sys.path.insert(0, '/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster')
from binfill_sampler import sample_layout, placed_cube_obb
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
rows=[json.loads(l) for l in open(f'{ROOT}/scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
b={r['seed']:r for r in rows if r.get('task')=='BinFill'}
for seed in [4400100, 4400500, 4400800]:
    out=sample_layout(seed, exact=True, return_trials=True)
    L=b[seed]['spec']['layout']
    for c in out['cubes']:
        v=L['cubes'][f"{c['color']}_{c['idx']}"]
        d=max(abs(v[0]-c['x']),abs(v[1]-c['y']))
        print(seed, c['spawn_idx'], c['color'], c['idx'], 'mine', np.round([c['x'],c['y'],c['yaw']],4), 'spec', np.round(v,4), 'OK' if d==0 else 'DIFF')
        if d>0:
            pts=[(cc['x'],cc['y']) for cc in out['cubes'][:c['spawn_idx']]]
            print('   dist to prev', [round(float(np.hypot(c['x']-p[0],c['y']-p[1])),3) for p in pts])
            for cc in out['cubes'][:c['spawn_idx']]:
                cA=placed_cube_obb(cc['x'],cc['y'],cc['yaw'])
                print('    obb', np.round(cA[0],4), np.round(cA[1],3).tolist(), np.round(cA[2],4))
            break
