"""诊断：离线模型里每段第一次／第二次 screw 的帧数与失败位置（5x5@0.1，300 条 V4 同公式种子）。"""
import sys, os, collections, logging, torch, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "src")
logging.disable(logging.CRITICAL)
from robomme.robomme_env.utils.adjacent import find_path_0_to_8
from screw_model import make_planner, screw_len, node_xy_grid, tcp_pose_world, Q0
p = make_planner(); quat = tcp_pose_world(p, Q0)[3:]
A, B = [], []; fails = collections.Counter()
for k in range(100):
    g = torch.Generator(); g.manual_seed(5500000 + 100 * k)
    for _ in range(1000):
        a, b = torch.randperm(25, generator=g)[:2].tolist()
        path, *_ = find_path_0_to_8(start=a, target=b, R=5, C=5, diagonals=True, generator=g)
        if 20 <= len(path) <= 24: break
    q = Q0.copy()
    for i, n in enumerate(path):
        xy = node_xy_grid(n, 5, 5)
        a_, q1 = screw_len(p, q, xy, quat)
        if a_ is None:
            fails["first" + ("_from_Q0" if i == 0 else "")] += 1; q = q; continue
        b_, q2 = screw_len(p, q1, xy, quat)
        if b_ is None: fails["second"] += 1
        else: B.append(b_)
        if i > 0: A.append(a_)
        q = q1
print("first-call frames: mean", np.mean(A), "min", min(A), "max", max(A))
print("second-call frames:", collections.Counter(B))
print("fails:", dict(fails))
