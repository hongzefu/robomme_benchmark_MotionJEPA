import json
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
W=['peg_push','gripper_push','grasp_putdown']; out=[]
for l in open(R+'/artifacts/newtask-v6/v6-01/xhard4/specs.jsonl'):
    d=json.loads(l)
    if d.get('task')!='MoveCube': continue
    ini=d['spec']['initializations']; last=ini[str(max(int(k) for k in ini))]['way_idx']
    out.append(dict(episode=d['episode'],seed=d['seed'],selected=d['selected'],way_idx_by_init={k:v['way_idx'] for k,v in ini.items()},effective_way=W[last]))
    print(out[-1])
json.dump(out,open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube/xhard4_candidates_way.json','w'),indent=1)
