# 复刻正确性校验：对 specs.jsonl 里 10 条 BinFill 候选，逐位比较复刻出的全部取值
import json, sys
sys.path.insert(0, '/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster')
from binfill_sampler import sample_layout
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
rows=[json.loads(l) for l in open(f'{ROOT}/scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
b=[r for r in rows if r.get('task')=='BinFill']
for exact in (True, False):
    ok=0
    for r in b:
        s=r['spec']; o=s['objects']; L=s['layout']
        out=sample_layout(r['seed'], exact=exact)
        same = (list(out['button'])==L['button_xy'] and out['color_pool']==o['color_pool'] and out['spawn']==o['spawn_numbers']
                and out['target']==o['target_numbers'] and out['order']==o['spawn_order'])
        maxd=0.0
        for c in out['cubes']:
            v=L['cubes'][f"{c['color']}_{c['idx']}"]
            maxd=max(maxd, abs(v[0]-c['x']), abs(v[1]-c['y']), abs(v[2]-c['yaw']))
        good = same and maxd==0.0
        ok+=good
        print('exact' if exact else 'fast', r['seed'], 'meta_same', same, 'max|d|', maxd)
    print('exact' if exact else 'fast', 'REPLICATION', ok, '/', len(b))
