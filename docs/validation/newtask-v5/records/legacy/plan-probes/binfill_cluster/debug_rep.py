import json, sys
sys.path.insert(0, '/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster')
from binfill_sampler import sample_layout
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
rows=[json.loads(l) for l in open(f'{ROOT}/scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
b=[r for r in rows if r.get('task')=='BinFill']
for r in b:
    L=r['spec']['layout']
    out=sample_layout(r['seed'], exact=True, return_trials=True)
    for c,t in zip(out['cubes'],out['trials']):
        v=L['cubes'][f"{c['color']}_{c['idx']}"]
        d=max(abs(v[0]-c['x']),abs(v[1]-c['y']))
        if d>0:
            print(r['seed'],'first diverge at spawn_idx',c['spawn_idx'],c['color'],c['idx'],'mine',(round(c['x'],4),round(c['y'],4)),'spec',[round(z,4) for z in v],'trials',t)
            # 距离按钮/孔板
            print('   button',[round(z,4) for z in out['button']],'board',[round(z,4) for z in out['board']])
            break
