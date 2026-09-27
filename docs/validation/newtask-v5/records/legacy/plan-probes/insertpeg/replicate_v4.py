"""Pure-torch replication of InsertPeg xhard draw order (V4), compared with frozen spec rows.

Reproduces: _load_scene (length rand, radius rand, head_rgb rand(3), randint(0,peg_count))
then _initialize_episode twice (gym.make construction + reset): box jitter x/y, box yaw,
3 uniform pegs (x,y per attempt; yaw after acceptance), obj randint, dir randint,
near-target peg (r, theta per attempt; yaw after acceptance).
"""
import json, sys
import numpy as np
import torch

REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
SPECS = f"{REPO}/scripts/configs/newtask-v4/v4-01/specs.jsonl"


def draw_v4(seed, n_init=2, peg_count=4, yaw_half_deg=180, d_max=0.085, native=False):
    g = torch.Generator(); g.manual_seed(int(seed))
    lt = torch.rand(1, generator=g); rt = torch.rand(1, generator=g)
    length = (0.05 + (0.01 - 0.01) * lt).item()
    radius = (0.01 + (0.005 - 0.005) * rt).item()
    head = torch.rand(3, generator=g).tolist()
    rp = int(torch.randint(0, peg_count, (1,), generator=g).item())
    out = {"objects": {"head_rgb": head, "sampling_trace": {"random_peg_idx": rp}}, "initializations": {}}
    for k in range(n_init):
        xj = (torch.rand(1, generator=g).item() - 0.5) * 0.2
        yj = (torch.rand(1, generator=g).item() - 0.5) * 0.2
        box_yaw = np.pi / 2 + (torch.rand(1, generator=g).item() * 2 - 1) * np.radians(20)
        box_xy = np.array([0 + xj, 0 + yj], dtype=np.float32)
        placed = []; pegs = {}
        n_uniform = 3 if not native else 3
        for i in range(n_uniform):
            cand = None
            for _ in range(512):
                x = torch.rand(1, generator=g).item() * 0.4 + -0.2
                y = torch.rand(1, generator=g).item() * 0.6 + -0.3
                s = np.array([x, y], dtype=np.float32)
                if np.linalg.norm(s - box_xy) <= radius * 6:
                    continue
                if any(np.linalg.norm(s - p) <= length * 1.5 for p in placed):
                    continue
                cand = s; break
            if cand is None:
                raise RuntimeError("fail")
            yaw = (torch.rand(1, generator=g).item() * 2 - 1) * np.radians(yaw_half_deg)
            pegs[str(i)] = [[float(cand[0]), float(cand[1])], yaw]
            placed.append(cand)
        obj = int(torch.randint(0, 2, (1,), generator=g).item())
        dr = int(torch.randint(0, 2, (1,), generator=g).item())
        init = {"box_jitter": [xj, yj], "box_yaw": box_yaw, "obj_sample": obj, "dir_sample": dr, "pegs": pegs}
        if not native:
            anchor = np.asarray(placed[0], dtype=np.float32)
            d_min = length * 1.5
            cand = None; att = 0
            for att in range(1, 513):
                r = d_min + torch.rand(1, generator=g).item() * (d_max - d_min)
                th = torch.rand(1, generator=g).item() * 2 * np.pi
                s = anchor + np.array([r * np.cos(th), r * np.sin(th)], dtype=np.float32)
                if not (-0.2 <= s[0] <= 0.2 and -0.3 <= s[1] <= 0.3):
                    continue
                if np.linalg.norm(s - box_xy) <= radius * 6:
                    continue
                if any(np.linalg.norm(s - p) <= d_min for p in placed):
                    continue
                cand = s; break
            yaw = (torch.rand(1, generator=g).item() * 2 - 1) * np.radians(yaw_half_deg)
            pegs["3"] = [[float(cand[0]), float(cand[1])], yaw]
            init["near_target_distance"] = float(np.linalg.norm(np.array(pegs["3"][0], dtype=np.float32) - anchor))
            init["near_target_attempts"] = att
            init["peg_placement"] = {"requested": 4, "placed": 4}
        out["initializations"][str(k)] = init
    return out


def main():
    rows = [json.loads(l) for l in open(SPECS)][1:]
    rows = [r for r in rows if r["task"] == "InsertPeg"]
    ok = 0
    for r in rows:
        spec = r["spec"]
        mine = draw_v4(r["seed"])
        same = (mine["objects"] == spec["objects"] and mine["initializations"] == spec["initializations"])
        if not same:
            # find first diff
            for k in spec["initializations"]:
                for key, v in spec["initializations"][k].items():
                    if mine["initializations"][k].get(key) != v:
                        print("DIFF", r["episode"], k, key, v, mine["initializations"][k].get(key))
        ok += same
        print(f"episode={r['episode']} seed={r['seed']} exact_match={same}")
    print(f"REPLICATION={'PASS' if ok == len(rows) else 'FAIL'} rows={len(rows)} exact={ok}")


if __name__ == "__main__":
    main()
