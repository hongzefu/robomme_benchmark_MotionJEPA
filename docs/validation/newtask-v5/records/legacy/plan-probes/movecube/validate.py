"""用 v4-01 specs.jsonl 的 10 条 MoveCube 行核验 mc_layout.simulate 逐位复刻 V4 xhard（bias 0.5）。"""
import json, sys
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
from mc_layout import simulate
rows=[json.loads(l) for l in open('scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
mc=[r for r in rows if r['task']=='MoveCube']
ok_all=0
for r in mc:
    s=r['spec']; L=simulate(r['seed'], bias=0.5)
    errs=[]
    for seg,key in (('demo','demo'),('exec','execution')):
        lay=s['layout'][key]
        e=L.seg[seg]
        errs.append(abs(e['peg_root'][0]-lay['peg_offsets'][1]))
        errs.append(abs(e['peg_root'][1]-(lay['peg_offsets'][0]+lay['peg_offsets'][2])))
        errs.append(abs(e['peg_yaw']-lay['peg_yaw']))
        errs.append(max(abs(e['goal'][0]-lay['goal_xy'][0]),abs(e['goal'][1]-lay['goal_xy'][1])))
        errs.append(max(abs(e['cube'][0]-lay['cube_pose'][0]),abs(e['cube'][1]-lay['cube_pose'][1]),abs(e['cube_yaw']-lay['cube_pose'][2])))
    way_ok = L.way_idx == s['initializations']['0']['way_idx']
    obj_ok = L.obj_sample == s['objects']['obj_sample']
    m=max(errs)
    ok = m<1e-6 and way_ok and obj_ok
    ok_all+=ok
    print(r['seed'], 'maxerr=%.2e'%m, 'way', L.way_idx, s['initializations']['0']['way_idx'], 'obj', obj_ok, 'draws', L.draws, 'OK' if ok else 'MISMATCH')
print(f"REPLICATION_V4 match={ok_all}/{len(mc)}")
