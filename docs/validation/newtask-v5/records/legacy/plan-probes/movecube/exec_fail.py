"""执行段方块被演示段方块挡死（spawn_random_cube 256 次耗尽）的发生率：障碍物两种模型 × 方案 × 是否修复。"""
import sys, math
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
from mc_layout import simulate, CenterCfg
SQ = math.sqrt(0.3)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
B = CenterCfg("square", SQ*0.05, SQ*0.11, SQ*0.06, SQ*0.1, "both")
rows = [("原三档 hard（b=0, ±45°）", 0.0, None, False), ("V4 xhard b=0.5（现行）", 0.5, None, True),
        ("V5-b（bias 0 + 30%面积中心方，方块候选+最终都判）", 0.0, B, True)]
for name, bias, cfg, yx in rows:
    for obst in ("square", "trimesh"):
        for avoid in (True, False):
            if not avoid and cfg is None and not yx:
                continue
            fails = 0; draws = []
            for s in range(2_000_000, 2_000_000 + N):
                L = simulate(s, bias=bias, center=cfg, yaw_xhard=yx, obstacle=obst, exec_avoid_demo=avoid)
                if not L.ok: fails += 1
                else: draws.append(L.draws)
            d = np.array(draws)
            print(f"EXECFAIL {name:<44} 障碍={obst:<7} 执行段避让演示方块={'是' if avoid else '否(修复)'}  失败 {fails}/{N} = {fails/N:.2%}  随机调用 均值={d.mean():.2f} p99={np.percentile(d,99):.0f} max={d.max()}", flush=True)
