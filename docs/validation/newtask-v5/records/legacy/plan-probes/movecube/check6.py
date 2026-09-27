import sys
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
from mc_layout import simulate
real = {1000177: ("xhard", True, [-0.05871, -0.06894]), 1000442: ("xhard", False, None), 1000446: ("xhard", False, None),
        1000000: ("xhard", True, [-0.05979, 0.07785]), 1000002: ("hard", False, None), 1000042: ("hard", True, [0.0467, 0.07538])}
agree = 0
for s, (diff, ok, ex) in real.items():
    m = simulate(s, bias=0.5 if diff == "xhard" else 0.0, yaw_xhard=(diff == "xhard"), obstacle="trimesh")
    same = (m.ok == ok) and (not ok or np.allclose(m.seg["exec"]["cube"], ex, atol=1e-4))
    agree += same
    print(s, diff, "real_ok", ok, "model_ok", m.ok, m.fail, "exec", None if not m.ok else np.round(m.seg["exec"]["cube"], 5), "AGREE" if same else "DISAGREE")
print(f"SIM_VS_MODEL agree={agree}/6")
