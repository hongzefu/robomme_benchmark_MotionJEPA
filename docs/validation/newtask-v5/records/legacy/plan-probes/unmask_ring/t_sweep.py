import sys, time, math
import numpy as np
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
rng = np.random.default_rng(0)
lay = L.inner_vus(rng)
bins = lay[0]
sw = L.predict_sweeps(bins, L.swap_initiators(rng), 10)
t = time.time(); n = 0; hits = 0
for _ in range(300):
    x, y = rng.uniform(-0.35, 0.35, 2)
    hits += L.sweep_hits([x, y], 30.0, sw); n += 1
print("per candidate ms", 1000 * (time.time() - t) / n, "hit frac", hits / n)
