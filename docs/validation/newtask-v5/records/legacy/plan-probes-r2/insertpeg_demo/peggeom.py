"""Exact 2D footprint geometry of InsertPeg pegs / box / Panda finger zone (numpy, vectorised).

Peg (build_peg, length L=0.05, radius r=0.01): root = head link centre (sampled xy), axis u=(cos yaw, sin yaw).
  head visual box centre root, half (L/2, r); tail link centre root - L*u, half (L/2, r)
  => whole visual footprint: rectangle centre root - 0.025u, half (0.05, 0.01)  [span 0.1 m]
  collision boxes: half (0.9*L/2=0.0225, r) at root and at root-0.05u (0.005 m gap between them)
  axis segment: root-0.075u .. root+0.025u
Box (build_box_with_hole, inner 1.7r, outer 4r, depth L): footprint rectangle half (0.05, 0.04), yaw box_yaw.
Panda (panda_v3.urdf, fingers fully open q=0.04): rubber tip box y in [q, q+0.0152] (17.5 mm wide along peg axis),
  diagonal finger outer y up to q+0.0248 and bottom ~4.7 mm above TCP. With TCP at the grasped link centre the
  finger footprint is |along| <= 0.00875, |perp| in [0.04, 0.0648] (tip only: [0.04, 0.0552]).
"""
import numpy as np

L = 0.05000000074505806
R = 0.009999999776482582
PEG_HALF = np.array([0.05, 0.01])
PEG_CENTER_BACK = 0.025  # visual centre = root - 0.025u
COLL_HALF = np.array([0.0225, 0.01])
BOX_HALF = np.array([0.05, 0.04])
FINGER_ALONG = 0.00875
FINGER_PERP_OUT = 0.0648
FINGER_PERP_IN = 0.04
TIP_PERP_OUT = 0.0552


def axis(yaw):
    return np.stack([np.cos(yaw), np.sin(yaw)], -1)


def rect_corners(c, u, half):
    """c (...,2), u (...,2) unit axis, half (2,) -> (...,4,2)."""
    v = np.stack([-u[..., 1], u[..., 0]], -1)
    a = u * half[0]
    b = v * half[1]
    return np.stack([c + a + b, c + a - b, c - a - b, c - a + b], -2)


def _proj_overlap(cA, cB, axes):
    # cA, cB (...,4,2), axes (...,k,2)
    pA = np.einsum('...vd,...kd->...kv', cA, axes)
    pB = np.einsum('...vd,...kd->...kv', cB, axes)
    sep = (pA.max(-1) < pB.min(-1)) | (pB.max(-1) < pA.min(-1))
    return ~sep.any(-1)


def rect_intersect(cA, cB):
    """SAT for two rectangles given corners (...,4,2)."""
    eA = cA[..., 1, :] - cA[..., 0, :]
    eA2 = cA[..., 2, :] - cA[..., 1, :]
    eB = cB[..., 1, :] - cB[..., 0, :]
    eB2 = cB[..., 2, :] - cB[..., 1, :]
    axes = np.stack([eA, eA2, eB, eB2], -2)
    axes = np.stack([-axes[..., 1], axes[..., 0]], -1)
    return _proj_overlap(cA, cB, axes)


def point_seg_dist(p, a, b):
    ab = b - a
    t = np.clip(np.einsum('...d,...d->...', p - a, ab) / np.maximum(np.einsum('...d,...d->...', ab, ab), 1e-18), 0, 1)
    proj = a + t[..., None] * ab
    return np.linalg.norm(p - proj, axis=-1)


def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def seg_intersect(a1, b1, a2, b2):
    d1 = _cross(b2 - a2, a1 - a2); d2 = _cross(b2 - a2, b1 - a2)
    d3 = _cross(b1 - a1, a2 - a1); d4 = _cross(b1 - a1, b2 - a1)
    return (d1 * d2 < 0) & (d3 * d4 < 0)


def seg_seg_dist(a1, b1, a2, b2):
    d = np.minimum.reduce([point_seg_dist(a1, a2, b2), point_seg_dist(b1, a2, b2),
                           point_seg_dist(a2, a1, b1), point_seg_dist(b2, a1, b1)])
    return np.where(seg_intersect(a1, b1, a2, b2), 0.0, d)


def rect_dist(cA, cB):
    """Exact min distance between two convex quads (0 if intersecting)."""
    inter = rect_intersect(cA, cB)
    ds = []
    for i in range(4):
        for j in range(4):
            a2 = cB[..., j, :]; b2 = cB[..., (j + 1) % 4, :]
            ds.append(point_seg_dist(cA[..., i, :], a2, b2))
            a1 = cA[..., j, :]; b1 = cA[..., (j + 1) % 4, :]
            ds.append(point_seg_dist(cB[..., i, :], a1, b1))
    d = np.minimum.reduce(ds)
    return np.where(inter, 0.0, d)


def peg_rect(root, yaw):
    u = axis(yaw)
    return rect_corners(root - PEG_CENTER_BACK * u, u, PEG_HALF)


def peg_coll_rects(root, yaw):
    u = axis(yaw)
    return rect_corners(root, u, COLL_HALF), rect_corners(root - L * u, u, COLL_HALF)


def peg_segment(root, yaw):
    u = axis(yaw)
    return root - 0.075 * u, root + 0.025 * u


def box_rect(box_xy, box_yaw):
    return rect_corners(box_xy, axis(box_yaw), BOX_HALF)


def finger_rects(link_c, yaw, perp_out=FINGER_PERP_OUT):
    """Two finger footprints (each side) around a grasped link centre."""
    u = axis(yaw)
    v = np.stack([-u[..., 1], u[..., 0]], -1)
    mid = (FINGER_PERP_IN + perp_out) / 2
    half = np.array([FINGER_ALONG, (perp_out - FINGER_PERP_IN) / 2])
    return (rect_corners(link_c + mid * v, u, half), rect_corners(link_c - mid * v, u, half))


def pair_metrics(root_a, yaw_a, root_b, yaw_b):
    """Dict of pairwise spacing metrics between two pegs."""
    ra, rb = peg_rect(root_a, yaw_a), peg_rect(root_b, yaw_b)
    sa, sb = peg_segment(root_a, yaw_a), peg_segment(root_b, yaw_b)
    ha, ta = peg_coll_rects(root_a, yaw_a)
    hb, tb = peg_coll_rects(root_b, yaw_b)
    coll = rect_intersect(ha, hb) | rect_intersect(ha, tb) | rect_intersect(ta, hb) | rect_intersect(ta, tb)
    ca = root_a - PEG_CENTER_BACK * axis(yaw_a); cb = root_b - PEG_CENTER_BACK * axis(yaw_b)
    return {
        "root_dist": np.linalg.norm(root_a - root_b, axis=-1),
        "center_dist": np.linalg.norm(ca - cb, axis=-1),
        "axis_dist": seg_seg_dist(sa[0], sa[1], sb[0], sb[1]),
        "rect_gap": rect_dist(ra, rb),
        "visual_overlap": rect_intersect(ra, rb),
        "collision_overlap": coll,
    }
