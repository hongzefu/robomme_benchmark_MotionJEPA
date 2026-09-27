"""Point-choice ambiguity: pixel distance (front camera 256x256, K=[[128,0,128],[0,128,128]], extrinsic from V4 h5)
between the target peg's grasped link centre and the nearest NON-target link centre (select_target_with_pixel picks
the nearest projected link centre)."""
import sys, json
import numpy as np
D = __file__.rsplit('/', 1)[0]; sys.path.insert(0, D)
import peggeom as G
from mc import run
K = np.array([[128., 0, 128], [0, 128, 128], [0, 0, 1]])
E = np.array([[0., 1, 0, 0], [0.8944272, 0, -0.44721365, -0.08944264], [-0.44721377, 0, -0.8944272, 0.491935]])


def proj(xy):
    p = np.concatenate([xy, np.full(xy.shape[:-1] + (1,), 0.01), np.ones(xy.shape[:-1] + (1,))], -1)
    c = p @ E.T
    uv = c @ K.T
    return uv[..., :2] / uv[..., 2:3]


CFGS = [("native3_yaw45", dict(kind="root", param=0.075, yaw_mode="after", half_deg=45, n_pegs=3)),
        ("V4_near0.085", dict(kind="root", param=0.075, yaw_mode="after", n_pegs=4, near=0.085)),
        ("V5_root0.075&gap0.02", dict(kind="rect", param=0.02, yaw_mode="joint", root_min=0.075)),
        ("V5_root0.075&gap0.04", dict(kind="rect", param=0.04, yaw_mode="joint", root_min=0.075)),
        ("V5_root0.075&gap0.055", dict(kind="rect", param=0.055, yaw_mode="joint", root_min=0.075))]
rng = np.random.default_rng(7)
for i, (label, kw) in enumerate(CFGS):
    res, (bxy, byaw, roots, yaws), dt = run(n=4000, K=512, seed=500 + i, **kw)
    n, P = yaws.shape
    tail = rng.random(n) < 0.5
    u = G.axis(yaws)
    heads = roots; tails = roots - G.L * u
    tgt = np.where(tail[:, None], tails[:, 0], heads[:, 0])
    tgt_px = proj(tgt)
    others = np.concatenate([heads[:, 1:], tails[:, 1:]], 1)
    oth_px = proj(others)
    dpx = np.linalg.norm(oth_px - tgt_px[:, None], axis=-1).min(1)
    dw = np.linalg.norm(others - tgt[:, None], axis=-1).min(1)
    # also: the target's own other end (should be distinguishable; fixed 0.05 m)
    print(json.dumps({"label": label, "n": int(n), "nn_nontarget_link_world_m_p05": round(float(np.percentile(dw, 5)), 4),
                      "nn_world_median": round(float(np.median(dw)), 4),
                      "nn_px_p05": round(float(np.percentile(dpx, 5)), 2), "nn_px_median": round(float(np.median(dpx)), 2),
                      "frac_nn_px_lt_5": round(float((dpx < 5).mean()), 4), "frac_nn_px_lt_10": round(float((dpx < 10).mean()), 4)}))
