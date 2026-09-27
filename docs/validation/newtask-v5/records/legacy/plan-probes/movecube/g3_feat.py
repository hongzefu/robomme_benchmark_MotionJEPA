import sys, math
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
from mc_layout import simulate, _obb, _sat, HS
from joint import peg_boxes
def segdist(root, yaw, p):
    ax = np.array([math.cos(yaw), math.sin(yaw)]); a = root - 0.15*ax; b = root + 0.05*ax
    t = np.clip(np.dot(p-a, b-a)/np.dot(b-a,b-a), 0, 1); return np.linalg.norm(p - (a + t*(b-a)))
fail = {0.25: {910606}, 0.5: {910202, 910404}, 0.75: {910404, 910606}, 1.0: {910404, 910505, 910606}}
for s in (910404, 910505, 910606, 910202):
    for b in (0.0, 0.25, 0.5, 0.75, 1.0):
        L = simulate(s, bias=b)
        out = []
        for seg in ("demo", "exec"):
            e = L.seg[seg]
            cb = _obb(e["cube"][0], e["cube"][1], HS, e["cube_yaw"])
            ov = any(_sat(*cb, *p) for p in peg_boxes(e["peg_root"], e["peg_yaw"]))
            out.append(f"{seg}: peg_root={np.round(e['peg_root'],3)} yaw={math.degrees(e['peg_yaw']):.0f}° 杆轴线-方块中心距={segdist(e['peg_root'], e['peg_yaw'], e['cube']):.3f} 重叠={ov}")
        print(f"G3FEAT seed={s} b={b} {'FAIL' if s in fail.get(b,set()) else 'ok'} | " + " | ".join(out))
