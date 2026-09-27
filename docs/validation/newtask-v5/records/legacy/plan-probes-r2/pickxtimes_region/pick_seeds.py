"""列出 v4-01 PickXtimes 10 个 seed 在两种半宽下的目标/最远方块离基座距离；并从 4100000 往后找半宽 0.25 下目标离基座 >0.75 m 的 seed。"""
import sys, math, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from offline_p1 import v5_layout, BASE
def info(s, hw):
    o = v5_layout(s, cube_half=hw)
    pts = [(x, y) for (_, x, y, _) in o["colored"]] + [(x, y) for (_, x, y, _) in o["distractors"]]
    t = pts[o["target_idx"]]
    return round(math.dist(t, BASE), 3), round(max(math.dist(p, BASE) for p in pts), 3), [round(v, 3) for v in t]
base = [4100000 + 100 * i for i in range(10)]
for s in base:
    print("V4SEED", s, "hw0.2", info(s, 0.2), "hw0.25", info(s, 0.25))
far = []
s = 4100001
while len(far) < 6:
    r = info(s, 0.25)
    if r[0] > 0.75:
        far.append(s); print("FAR", s, r)
    s += 1
print("FAR_SEEDS", ",".join(map(str, far)))
