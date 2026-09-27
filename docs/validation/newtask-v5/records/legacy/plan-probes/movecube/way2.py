"""有效 way = 第二次 _initialize_episode 的 randint(3)（G3 报告：way 由最后一次 randint 决定）。核验 + 为演示探针选 seed。"""
import sys, json, math
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import torch
import mc_layout
from mc_layout import simulate, CenterCfg
from patch_v5 import V5_DEFAULT
def ways(seed, **kw):
    # 复用 simulate 的 draws 计数：重放同一 generator 到 draws 位置后再抽两次 randint(3)
    L = simulate(seed, **kw)
    g = torch.Generator(); g.manual_seed(seed)
    # simulate 的 draws 含第一次 way；回退 1 次后连抽两次
    for _ in range(L.draws - 1):
        torch.rand(1, generator=g)  # ⚠ randint 与 rand 占用状态是否相同需核验
    w1 = int(torch.randint(0, 3, (1,), generator=g).item()); w2 = int(torch.randint(0, 3, (1,), generator=g).item())
    return L, w1, w2
rows = [json.loads(l) for l in open('scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
ok = 0
for r in rows:
    if r['task'] != 'MoveCube': continue
    L, w1, w2 = ways(r['seed'], bias=0.5)
    i = r['spec']['initializations']
    m = (w1 == i['0']['way_idx'] and w2 == i['1']['way_idx'] and L.way_idx == w1)
    ok += m
    print("WAY2", r['seed'], (w1, w2), (i['0']['way_idx'], i['1']['way_idx']), "OK" if m else "MISMATCH")
print(f"WAY2 match={ok}/10")
V5 = CenterCfg("square", V5_DEFAULT["peg_w"], V5_DEFAULT["goal_w_demo"], V5_DEFAULT["goal_w_exec"], V5_DEFAULT["cube_w"], "both")
names = ["peg_push", "gripper_push", "grasp_putdown"]
for s in [910000, 910101, 910202, 910303, 910404, 910505, 910606, 910707, 910808, 910909, 911010, 911111]:
    L, w1, w2 = ways(s, bias=0.0, center=V5, exec_avoid_demo=False)
    print("V5WAY", s, "ok" if L.ok else L.fail, "way(第一次,第二次)=", names[w1], names[w2])
