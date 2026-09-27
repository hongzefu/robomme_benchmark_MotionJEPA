"""Physics settle test (simulator): how much do pegs move in the first 20 control steps after reset?

Mode v4: replay the 10 frozen V4 InsertPeg specs as-is.
Mode v5: same specs (same box pose / obj / dir), but pegs.0..3 in BOTH initializations replaced by a layout
drawn with the proposed V5 sampler (4 pegs, one sampler, root>0.075 AND footprint gap >= GAP, lazy yaw),
injected through the spec-replay path (SpecRecorder returns frozen values), so no repository file is touched.
Robot holds its reset pose (reset_panda 'action'), gripper open.
"""
import sys, json, copy, argparse
import numpy as np
REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
sys.path.insert(0, REPO); sys.path.insert(0, REPO + "/src"); sys.path.insert(0, REPO + "/scripts")
sys.path.insert(0, __file__.rsplit('/', 1)[0])
import peggeom as G


def v5_layout(rng, box_xy, box_yaw, gap, root_min=0.075, n=4, maxa=512):
    placed = []
    for i in range(n):
        for _ in range(maxa):
            x = rng.random() * 0.4 - 0.2; y = rng.random() * 0.6 - 0.3
            xy = np.array([x, y], dtype=np.float32)
            if np.linalg.norm(xy - box_xy) <= G.R * 6: continue
            if any(np.linalg.norm(xy - p[0]) <= root_min for p in placed): continue
            yaw = (rng.random() * 2 - 1) * np.pi
            if any(G.rect_dist(G.peg_rect(xy.astype(float), np.float64(yaw)), G.peg_rect(p[0].astype(float), np.float64(p[1]))) < gap for p in placed): continue
            placed.append((xy, yaw)); break
        else:
            raise RuntimeError("fail")
    return {str(i): [[float(p[0][0]), float(p[0][1])], float(p[1])] for i, p in enumerate(placed)}


def yaw_tilt(q):
    w, x, y, z = q
    # peg local x axis in world
    ax = np.array([1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)])
    return np.degrees(np.arctan2(ax[1], ax[0])), np.degrees(np.arcsin(np.clip(ax[2], -1, 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["v4", "v5"], required=True)
    ap.add_argument("--gap", type=float, default=0.02)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--episodes", default="0,1,2,3,4,5,6,7,8,9")
    a = ap.parse_args()
    import gymnasium as gym
    import robomme.robomme_env  # noqa
    from robomme.robomme_env.utils import reset_panda
    lines = [json.loads(l) for l in open(f"{REPO}/scripts/configs/newtask-v4/v4-01/specs.jsonl")]
    sampling = lines[0]["sampling_config"]["InsertPeg"]
    rows = {r["episode"]: r for r in lines[1:] if r["task"] == "InsertPeg"}
    rng = np.random.default_rng(20260924)
    out = []
    for ep in [int(e) for e in a.episodes.split(",")]:
        row = rows[ep]; spec = copy.deepcopy(row["spec"])
        last = str(max(int(k) for k in spec["initializations"]))
        if a.mode == "v5":
            init = spec["initializations"][last]
            lay = v5_layout(rng, np.array(init["box_jitter"], dtype=np.float32), init["box_yaw"], a.gap)
            for k in spec["initializations"]:
                spec["initializations"][k]["pegs"] = copy.deepcopy(lay)
        env = gym.make("InsertPeg", sampling_config=sampling, native_episode_spec=spec, obs_mode="state",
                       control_mode="pd_joint_pos", reward_mode="dense", seed=row["seed"], difficulty="xhard")
        env.reset()
        base = env.unwrapped
        def poses():
            return [(np.asarray(p.pose.p).reshape(-1).copy(), np.asarray(p.pose.q).reshape(-1).copy()) for p in base.pegs]
        p0 = poses()
        roots = [p[0][:2] for p in p0]; yaws0 = [yaw_tilt(p[1])[0] for p in p0]
        # pre-step geometry
        pair_gap = {}
        for i in range(4):
            for j in range(i + 1, 4):
                pair_gap[f"{i}{j}"] = float(G.rect_dist(G.peg_rect(roots[i].astype(float), np.radians(yaws0[i])), G.peg_rect(roots[j].astype(float), np.radians(yaws0[j]))))
        action = reset_panda.get_reset_panda_param("action")
        action = np.asarray(action.cpu() if hasattr(action, "cpu") else action, dtype=np.float32).reshape(-1)
        for _ in range(a.steps):
            env.step(action)
        p1 = poses()
        rec = {"ep": ep, "min_gap_pre": min(pair_gap.values()), "tgt_gap_pre": min(v for k, v in pair_gap.items() if k[0] == "0"), "pegs": []}
        for i in range(4):
            y0, t0 = yaw_tilt(p0[i][1]); y1, t1 = yaw_tilt(p1[i][1])
            dyaw = (y1 - y0 + 180) % 360 - 180
            rec["pegs"].append({"i": i, "dxy_mm": float(np.linalg.norm(p1[i][0][:2] - p0[i][0][:2]) * 1000),
                                "dyaw_deg": float(dyaw), "tilt_deg": float(t1), "z_mm": float(p1[i][0][2] * 1000)})
        env.close()
        t = rec["pegs"][0]
        mx = max(rec["pegs"], key=lambda r: r["dxy_mm"])
        print(f"mode={a.mode} ep={ep} min_gap_pre={rec['min_gap_pre']:.4f} tgt_gap_pre={rec['tgt_gap_pre']:.4f} "
              f"target: dxy={t['dxy_mm']:.1f}mm dyaw={t['dyaw_deg']:+.1f}deg tilt={t['tilt_deg']:+.1f}deg z={t['z_mm']:.1f}mm | "
              f"max-moved peg {mx['i']}: dxy={mx['dxy_mm']:.1f}mm dyaw={mx['dyaw_deg']:+.1f}", flush=True)
        out.append(rec)
    json.dump(out, open(__file__.rsplit('/', 1)[0] + f"/settle_{a.mode}.json", "w"), indent=1)
    print("SETTLE_DONE", a.mode, len(out))


if __name__ == "__main__":
    main()
