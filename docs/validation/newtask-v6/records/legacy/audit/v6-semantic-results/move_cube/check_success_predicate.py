"""提取固定审查快照的纯成功谓词，以内存对象验证静态漏洞；不创建环境。"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import torch

ROOT=Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
SOURCE=ROOT/'artifacts/audit/v6-semantic-0a3f989/src/robomme/robomme_env/utils/subgoal_evaluate_func.py'
tree=ast.parse(SOURCE.read_text())
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='is_obj_pushed_onto')
namespace={'torch':torch}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),namespace)
env=SimpleNamespace(cube_half_size=.02,agent=SimpleNamespace(robot=SimpleNamespace(get_qpos=lambda:torch.tensor([[0,0,0,0,0,0,0,.04,.04]]))))
target=SimpleNamespace(pose=SimpleNamespace(p=torch.tensor([[0.,0.,.0025]])))
cases=[]
for label,pos in [('空中且无杆接触',[0.,0.,.5]),('地面上但没有推动历史',[0.,0.,.02]),('中心越过半径4厘米的圆盘',[.047,0.,.02])]:
    obj=SimpleNamespace(pose=SimpleNamespace(p=torch.tensor([pos])))
    accepted=bool(namespace['is_obj_pushed_onto'](env,obj,target,distance_threshold=.048,must_gripper_open=True))
    cases.append({'case':label,'position':pos,'accepted':accepted})
result={'audit_base':'0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8','scope':'纯谓词反例，未证明已有生成轨迹发生错误','new_resets':0,'new_rollouts':0,'cases':cases}
(ROOT/'artifacts/audit/v6-semantic-results/move_cube/predicate_counterexample.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
assert all(x['accepted'] for x in cases)
print('MC_METHOD_PREDICATE_COUNTEREXAMPLE=PASS cases=3 new_resets=0 new_rollouts=0')
