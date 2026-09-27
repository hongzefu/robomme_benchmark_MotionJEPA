import sys
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
from mc_layout import simulate
xf, nf, xp = [], [], []
for s in range(1_000_000, 1_003_000):
    a = simulate(s, bias=0.5)
    if not a.ok and len(xf) < 3: xf.append((s, a.fail))
    if a.ok and len(xp) < 2: xp.append(s)
    b = simulate(s, bias=0.0, yaw_xhard=False)
    if not b.ok and len(nf) < 2: nf.append((s, b.fail))
    if len(xf) >= 3 and len(nf) >= 2 and len(xp) >= 2: break
print("xhard_b0.5_fail", xf); print("xhard_pass", xp); print("native_fail", nf)
