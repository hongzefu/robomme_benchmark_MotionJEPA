"""Split finger hazard at the target's grasped link into:
  pinch   : a neighbour footprint inside the closing span (perp 0.01..0.04 from target axis, |along|<=8.75 mm)
            -> fingers can close on the neighbour (wrong peg lifted => is_any_obj_pickup failure)
  land    : a neighbour under the open finger pads/diagonal part (perp 0.04..0.0648)
            -> finger lands on / shoves the neighbour
Random grasped end (obj_sample 50/50)."""
import sys, json
import numpy as np
D = __file__.rsplit('/', 1)[0]; sys.path.insert(0, D)
import peggeom as G
from mc import run


def zone_hit(link_c, yaw, lo, hi, roots, yaws):
    u = G.axis(yaw); v = np.stack([-u[..., 1], u[..., 0]], -1)
    mid = (lo + hi) / 2; half = np.array([G.FINGER_ALONG, (hi - lo) / 2])
    zl = G.rect_corners(link_c + mid * v, u, half); zr = G.rect_corners(link_c - mid * v, u, half)
    h = np.zeros(len(yaw), bool)
    for j in range(1, roots.shape[1]):
        rj = G.peg_rect(roots[:, j], yaws[:, j])
        h |= G.rect_intersect(zl, rj) | G.rect_intersect(zr, rj)
    return h


CFGS = [("V4_near0.085", dict(kind="root", param=0.075, yaw_mode="after", n_pegs=4, near=0.085))]
for g in (0.005, 0.01, 0.02, 0.025, 0.03, 0.04, 0.045, 0.055):
    CFGS.append((f"V5_root0.075&gap{g}", dict(kind="rect", param=g, yaw_mode="joint", root_min=0.075)))
rng = np.random.default_rng(11)
for i, (label, kw) in enumerate(CFGS):
    res, (bxy, byaw, roots, yaws), dt = run(n=6000, K=512, seed=700 + i, **kw)
    n = len(yaws)
    tail = rng.random(n) < 0.5
    u0 = G.axis(yaws[:, 0])
    link = np.where(tail[:, None], roots[:, 0] - G.L * u0, roots[:, 0])
    pinch = zone_hit(link, yaws[:, 0], 0.0101, 0.04, roots, yaws)
    land = zone_hit(link, yaws[:, 0], 0.04, G.FINGER_PERP_OUT, roots, yaws)
    tip = zone_hit(link, yaws[:, 0], 0.04, G.TIP_PERP_OUT, roots, yaws)
    print(json.dumps({"label": label, "n": n, "pinch": round(float(pinch.mean()), 4), "land_full": round(float(land.mean()), 4),
                      "land_tip": round(float(tip.mean()), 4), "any": round(float((pinch | land).mean()), 4),
                      "p_acc_mean": res["p_step"] and [round(float(np.mean(p)), 3) for p in res["p_step"]]}))
