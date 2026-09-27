"""Monte Carlo of InsertPeg peg placement: V4 (3 uniform + near-target band) vs V5 candidates (4 pegs, one sampler).

Box: jitter U(-0.1,0.1)^2, yaw 90deg +- 20deg. Peg root region x in [-0.2,0.2], y in [-0.3,0.3],
root-to-box-centre > radius*6 (=0.06). max_attempts 512. Yaw U(-180,180) deg (xhard) or +-45 (native).

Vectorised rejection: for each placement step draw K candidates iid; the actual draw = first accepted among
the first 512 (identical in distribution to the sequential loop); acceptance probability of the state is
estimated from all K candidates and P(fail at this step | state) ~ (1-p)^512.
"""
import sys, time, json, argparse
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
import peggeom as G

MAXA = 512
BOX_CLEAR = G.R * 6
BASE = np.array([-0.615, 0.0])


def draw_box(rng, n):
    xy = (rng.random((n, 2)) - 0.5) * 0.2
    yaw = np.pi / 2 + (rng.random(n) * 2 - 1) * np.radians(20)
    return xy, yaw


def accept_mask(kind, param, cand_xy, cand_yaw, placed_xy, placed_yaw, box_xy, root_min=None, box_gap=None, box_yaw=None):
    """cand (n,K,2),(n,K); placed list of (n,2),(n,) ; returns (n,K) bool."""
    ok = np.linalg.norm(cand_xy - box_xy[:, None, :], axis=-1) > BOX_CLEAR
    if root_min is not None:
        for pxy in placed_xy:
            ok &= np.linalg.norm(cand_xy - pxy[:, None, :], axis=-1) > root_min
    if box_gap is not None:
        bxy = np.broadcast_to(box_xy[:, None, :], cand_xy.shape); byw = np.broadcast_to(box_yaw[:, None], cand_yaw.shape)
        near = ok & (np.linalg.norm(cand_xy - bxy, axis=-1) < 0.0757 + 0.0641 + box_gap)
        if near.any():
            good = G.rect_dist(G.peg_rect(cand_xy[near], cand_yaw[near]), G.box_rect(bxy[near], byw[near])) >= box_gap
            sub = ok[near]; sub &= good; ok[near] = sub
    for pxy, pyaw in zip(placed_xy, placed_yaw):
        pxy_b = np.broadcast_to(pxy[:, None, :], cand_xy.shape)
        pyaw_b = np.broadcast_to(pyaw[:, None], cand_yaw.shape)
        if kind == "root":
            ok &= np.linalg.norm(cand_xy - pxy_b, axis=-1) > param
        elif kind == "center":
            ca = cand_xy - G.PEG_CENTER_BACK * G.axis(cand_yaw); cb = pxy_b - G.PEG_CENTER_BACK * G.axis(pyaw_b)
            ok &= np.linalg.norm(ca - cb, axis=-1) > param
        elif kind in ("axis", "rect"):
            # prefilter: each footprint lies in a disk of radius 0.0757 around its root, so pairs with
            # root distance >= 0.1514 + param are certainly separated; evaluate exact metric only on the rest
            near = ok & (np.linalg.norm(cand_xy - pxy_b, axis=-1) < 0.1515 + param)
            if near.any():
                cxy, cyw, qxy, qyw = cand_xy[near], cand_yaw[near], pxy_b[near], pyaw_b[near]
                if kind == "axis":
                    sa = G.peg_segment(cxy, cyw); sb = G.peg_segment(qxy, qyw)
                    good = G.seg_seg_dist(sa[0], sa[1], sb[0], sb[1]) >= 2 * G.R + param
                else:
                    good = G.rect_dist(G.peg_rect(cxy, cyw), G.peg_rect(qxy, qyw)) >= param
                sub = ok[near]; sub &= good; ok[near] = sub
        else:
            raise ValueError(kind)
    return ok


def run(kind, param, n=5000, K=2048, yaw_mode="joint", half_deg=180.0, n_pegs=4, near=None, seed=0, chunk=250, root_min=None, box_gap=None):
    """near: None or d_max for V4 4th peg in band (0.075, d_max] around peg0 (root criterion 0.075 for all)."""
    rng = np.random.default_rng(seed)
    hs = np.radians(half_deg)
    res = {"fail_direct": 0, "fail_est": [], "attempts": [[] for _ in range(n_pegs)], "p_step": [[] for _ in range(n_pegs)]}
    layouts = []  # (box_xy, box_yaw, roots (n_pegs,2), yaws (n_pegs,), ok)
    t0 = time.time()
    for c0 in range(0, n, chunk):
        m = min(chunk, n - c0)
        box_xy, box_yaw = draw_box(rng, m)
        placed_xy, placed_yaw = [], []
        alive = np.ones(m, bool)
        surv = np.ones(m)  # product of (1 - P(fail at step))
        n_uniform = n_pegs - (1 if near is not None else 0)
        for i in range(n_pegs):
            if near is not None and i == n_pegs - 1:
                r = 0.075 + rng.random((m, K)) * (near - 0.075)
                th = rng.random((m, K)) * 2 * np.pi
                cxy = placed_xy[0][:, None, :] + np.stack([r * np.cos(th), r * np.sin(th)], -1)
                inreg = (cxy[..., 0] >= -0.2) & (cxy[..., 0] <= 0.2) & (cxy[..., 1] >= -0.3) & (cxy[..., 1] <= 0.3)
                cyaw = np.zeros((m, K))
                ok = inreg & accept_mask("root", 0.075, cxy, cyaw, placed_xy, placed_yaw, box_xy)
                yaw_after = (rng.random(m) * 2 - 1) * hs
            else:
                cxy = np.stack([rng.random((m, K)) * 0.4 - 0.2, rng.random((m, K)) * 0.6 - 0.3], -1)
                if yaw_mode == "joint":
                    cyaw = (rng.random((m, K)) * 2 - 1) * hs
                elif yaw_mode == "first":
                    cyaw = np.broadcast_to(((rng.random(m) * 2 - 1) * hs)[:, None], (m, K)).copy()
                else:  # "after": yaw not part of the check, drawn after acceptance
                    cyaw = np.zeros((m, K))
                kk = "root" if near is not None else kind
                pp = 0.075 if near is not None else param
                ok = accept_mask(kk, pp, cxy, cyaw, placed_xy, placed_yaw, box_xy, root_min=root_min, box_gap=box_gap, box_yaw=box_yaw)
                yaw_after = (rng.random(m) * 2 - 1) * hs
            p_hat = ok.mean(1)
            first = np.where(ok[:, :MAXA].any(1), ok[:, :MAXA].argmax(1), -1)
            step_fail = (first < 0)
            surv *= 1 - np.where(ok.any(1), (1 - p_hat) ** MAXA, 1.0)
            idx = np.clip(first, 0, None)
            sel_xy = cxy[np.arange(m), idx]
            sel_yaw = cyaw[np.arange(m), idx] if yaw_mode in ("joint", "first") and not (near is not None and i == n_pegs - 1) else yaw_after
            alive &= ~step_fail
            res["attempts"][i].extend((first[~step_fail] + 1).tolist())
            res["p_step"][i].extend(p_hat.tolist())
            placed_xy.append(sel_xy); placed_yaw.append(sel_yaw)
        res["fail_direct"] += int((~alive).sum())
        res["fail_est"].extend((1 - surv).tolist())
        layouts.append((box_xy[alive], box_yaw[alive], np.stack(placed_xy, 1)[alive], np.stack(placed_yaw, 1)[alive]))
    box_xy = np.concatenate([l[0] for l in layouts]); box_yaw = np.concatenate([l[1] for l in layouts])
    roots = np.concatenate([l[2] for l in layouts]); yaws = np.concatenate([l[3] for l in layouts])
    return res, (box_xy, box_yaw, roots, yaws), time.time() - t0


def layout_stats(box_xy, box_yaw, roots, yaws, rng):
    n, P = yaws.shape
    out = {}
    any_vis = np.zeros(n, bool); tgt_vis = np.zeros(n, bool); any_coll = np.zeros(n, bool); tgt_coll = np.zeros(n, bool)
    tgt_axis_i2 = np.zeros(n, bool); any_axis_i2 = np.zeros(n, bool)
    min_gap = np.full(n, np.inf); tgt_gap = np.full(n, np.inf); tgt_root_nn = np.full(n, np.inf)
    for i in range(P):
        for j in range(i + 1, P):
            pm = G.pair_metrics(roots[:, i], yaws[:, i], roots[:, j], yaws[:, j])
            any_vis |= pm["visual_overlap"]; any_coll |= pm["collision_overlap"]; any_axis_i2 |= pm["axis_dist"] < 0.02
            min_gap = np.minimum(min_gap, pm["rect_gap"])
            if i == 0:
                tgt_vis |= pm["visual_overlap"]; tgt_coll |= pm["collision_overlap"]; tgt_axis_i2 |= pm["axis_dist"] < 0.02
                tgt_gap = np.minimum(tgt_gap, pm["rect_gap"]); tgt_root_nn = np.minimum(tgt_root_nn, pm["root_dist"])
    out.update(any_visual_overlap=any_vis.mean(), target_visual_overlap=tgt_vis.mean(),
               any_collision_overlap=any_coll.mean(), target_collision_overlap=tgt_coll.mean(),
               any_axisdist_lt_0p02=any_axis_i2.mean(), target_axisdist_lt_0p02=tgt_axis_i2.mean(),
               min_pair_gap_p05=np.percentile(min_gap, 5), target_gap_median=np.median(tgt_gap),
               target_nn_root_median=np.median(tgt_root_nn), target_nn_root_p10=np.percentile(tgt_root_nn, 10))
    # finger intrusion at target: head / tail / random end (obj 50/50)
    u0 = G.axis(yaws[:, 0])
    hit = {}
    for end, c in (("head", roots[:, 0]), ("tail", roots[:, 0] - G.L * u0)):
        for zone, pout in (("full", G.FINGER_PERP_OUT), ("tip", G.TIP_PERP_OUT)):
            fl, fr = G.finger_rects(c, yaws[:, 0], pout)
            h = np.zeros(n, bool)
            for j in range(1, P):
                rj = G.peg_rect(roots[:, j], yaws[:, j])
                h |= G.rect_intersect(fl, rj) | G.rect_intersect(fr, rj)
            hit[(end, zone)] = h
    pick_tail = rng.random(n) < 0.5
    for zone in ("full", "tip"):
        out[f"finger_{zone}_random_end"] = np.where(pick_tail, hit[("tail", zone)], hit[("head", zone)]).mean()
        out[f"finger_{zone}_either_end"] = (hit[("tail", zone)] | hit[("head", zone)]).mean()
    br = G.box_rect(box_xy, box_yaw)
    pb_any = np.zeros(n, bool)
    for i in range(P):
        o = G.rect_intersect(G.peg_rect(roots[:, i], yaws[:, i]), br)
        pb_any |= o
        if i == 0:
            out["target_box_overlap"] = o.mean()
    out["any_box_overlap"] = pb_any.mean()
    # reach: horizontal distance robot base -> grasped link centre (random end)
    gc = np.where(pick_tail[:, None], roots[:, 0] - G.L * u0, roots[:, 0])
    dist = np.linalg.norm(gc - BASE, axis=1)
    out["grasp_dist_from_base_p50"] = np.median(dist); out["grasp_dist_gt_0p78"] = (dist > 0.78).mean()
    return out


def summarize(label, res, lay, dt, rng):
    n_total = len(res["fail_est"])
    fe = np.mean(res["fail_est"])
    att = [np.array(a) if a else np.array([0]) for a in res["attempts"]]
    pst = [np.array(p) for p in res["p_step"]]
    s = {"label": label, "n": n_total, "fail_direct": res["fail_direct"], "fail_est": fe,
         "p_accept_mean": [round(float(p.mean()), 4) for p in pst],
         "p_accept_min": [round(float(p.min()), 5) for p in pst],
         "attempts_mean": [round(float(a.mean()), 2) for a in att],
         "attempts_p95": [int(np.percentile(a, 95)) for a in att],
         "attempts_max": [int(a.max()) for a in att], "sec": round(dt, 1)}
    s.update({k: (round(float(v), 4)) for k, v in layout_stats(*lay, rng).items()})
    print(json.dumps(s), flush=True)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--K", type=int, default=2048)
    ap.add_argument("--configs", default="all")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rng = np.random.default_rng(1)
    CONFIGS = []
    CONFIGS.append(("native3_root0.075_yaw45_after", dict(kind="root", param=0.075, yaw_mode="after", half_deg=45, n_pegs=3)))
    CONFIGS.append(("V4_3uniform+near0.085_yaw180", dict(kind="root", param=0.075, yaw_mode="after", n_pegs=4, near=0.085)))
    for d in (0.075, 0.10, 0.12, 0.15, 0.152):
        CONFIGS.append((f"V5_root>{d}_after", dict(kind="root", param=d, yaw_mode="after")))
    for d in (0.10, 0.11):
        CONFIGS.append((f"V5_center>{d}_joint", dict(kind="center", param=d, yaw_mode="joint")))
    for g in (0.0, 0.01, 0.02, 0.03, 0.04):
        CONFIGS.append((f"V5_axis>=2r+{g}_joint", dict(kind="axis", param=g, yaw_mode="joint")))
    for g in (0.0, 0.005, 0.01, 0.02, 0.03, 0.04, 0.055):
        CONFIGS.append((f"V5_rectgap>={g}_joint", dict(kind="rect", param=g, yaw_mode="joint")))
    for g in (0.0, 0.02, 0.04, 0.055):
        CONFIGS.append((f"V5_rectgap>={g}_yawfirst", dict(kind="rect", param=g, yaw_mode="first")))
    for g in (0.0, 0.01, 0.02, 0.03, 0.04, 0.055):
        CONFIGS.append((f"V5_root>0.075&rectgap>={g}_joint", dict(kind="rect", param=g, yaw_mode="joint", root_min=0.075)))
    for g, bg in ((0.02, 0.0), (0.02, 0.01), (0.03, 0.01), (0.04, 0.01)):
        CONFIGS.append((f"V5_root>0.075&rectgap>={g}&boxgap>={bg}_joint", dict(kind="rect", param=g, yaw_mode="joint", root_min=0.075, box_gap=bg)))
    if a.configs == "list":
        for i, c in enumerate(CONFIGS):
            print(i, c[0])
        sys.exit(0)
    idx = range(len(CONFIGS)) if a.configs == "all" else [int(t) for t in a.configs.split(",")]
    allres = []
    for i in idx:
        label, kw = CONFIGS[i]
        res, lay, dt = run(n=a.n, K=a.K, seed=1000 + i, **kw)
        allres.append(summarize(label, res, lay, dt, rng))
    if a.out:
        json.dump(allres, open(a.out, "w"), indent=1)
