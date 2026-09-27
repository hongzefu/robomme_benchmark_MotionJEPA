"""副本校验：无新规则（R=None、bias 0.5、执行段避让演示方块）下与 v4-01 specs.jsonl 的 MoveCube 行逐位一致。"""
import json, sys
sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/movecube_circle")
from mc_v5 import simulate
rows = [json.loads(l) for l in open('/data/hongzefu/robomme_v5_probe_wt/scripts/configs/newtask-v4/v4-01/specs.jsonl')]
mc = [r for r in rows if r.get('task') == 'MoveCube']
ok_all = 0
for r in mc:
    s = r['spec']; L = simulate(r['seed'], bias=0.5, R=None)
    errs = []
    for seg, key in (('demo', 'demo'), ('exec', 'execution')):
        lay = s['layout'][key]; e = L.seg[seg]
        errs += [abs(e['peg_root'][0] - lay['peg_offsets'][1]),
                 abs(e['peg_root'][1] - (lay['peg_offsets'][0] + lay['peg_offsets'][2])),
                 abs(e['peg_yaw'] - lay['peg_yaw']),
                 max(abs(e['goal'][0] - lay['goal_xy'][0]), abs(e['goal'][1] - lay['goal_xy'][1])),
                 max(abs(e['cube'][0] - lay['cube_pose'][0]), abs(e['cube'][1] - lay['cube_pose'][1]), abs(e['cube_yaw'] - lay['cube_pose'][2]))]
    way_ok = L.way_idx == s['initializations']['0']['way_idx']
    obj_ok = L.obj_sample == s['objects']['obj_sample']
    m = max(errs); ok = m < 1e-6 and way_ok and obj_ok; ok_all += ok
    print(r['seed'], r.get('difficulty'), 'maxerr=%.2e' % m, 'way', L.way_idx, s['initializations']['0']['way_idx'], 'obj', obj_ok, 'draws', L.draws, 'OK' if ok else 'MISMATCH')
print(f"REPLICATION_V4 match={ok_all}/{len(mc)}")
