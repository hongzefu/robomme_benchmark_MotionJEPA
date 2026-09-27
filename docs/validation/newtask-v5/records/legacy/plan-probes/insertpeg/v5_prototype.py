"""V5 prototype of the xhard InsertPeg peg sampler with the exact torch draw order (no simulator).

Draw order per initialization (xhard only):
  box x jitter, box y jitter, box yaw                      (unchanged)
  for i in 0..3 (ONE loop, same rule for every peg):
      repeat <= max_attempts:
          x = rand*0.4-0.2 ; y = rand*0.6-0.3               (unchanged)
          reject if |xy-box| <= radius*6                    (unchanged native rule)
          reject if |xy-root_j| <= length*1.5 for any j     (unchanged native rule)
          yaw = (rand*2-1)*pi                               (lazy: drawn only after the two native checks pass)
          reject if footprint_gap(peg_box) <= box_gap       (NEW, optional)
          reject if footprint_gap(peg, peg_j) <= pair_gap   (NEW, strict >)
          accept
      exhausted -> SceneGenerationError
  obj randint(0,2), dir randint(0,2)                       (unchanged draws; now after all 4 pegs)
Reports per-seed attempts / min gap, failures, and the V4-vs-V5 stream divergence.
"""
import sys, json, argparse
import numpy as np
import torch
D = __file__.rsplit('/', 1)[0]; sys.path.insert(0, D)
import peggeom as G


def v5_init(g, length, radius, pair_gap, box_gap, n=4, max_attempts=512, yaw_half=np.pi):
    xj = (torch.rand(1, generator=g).item() - 0.5) * 0.2
    yj = (torch.rand(1, generator=g).item() - 0.5) * 0.2
    box_yaw = np.pi / 2 + (torch.rand(1, generator=g).item() * 2 - 1) * np.radians(20)
    box_xy = np.array([xj, yj], dtype=np.float32)
    box_r = G.box_rect(box_xy.astype(float), np.float64(box_yaw))
    placed, attempts = [], []
    for i in range(n):
        ok = False
        for a in range(1, max_attempts + 1):
            x = torch.rand(1, generator=g).item() * 0.4 + -0.2
            y = torch.rand(1, generator=g).item() * 0.6 + -0.3
            s = np.array([x, y], dtype=np.float32)
            if np.linalg.norm(s - box_xy) <= radius * 6:
                continue
            if any(np.linalg.norm(s - p[0]) <= length * 1.5 for p in placed):
                continue
            yaw = (torch.rand(1, generator=g).item() * 2 - 1) * yaw_half
            rect = G.peg_rect(s.astype(float), np.float64(yaw))
            if box_gap is not None and G.rect_dist(rect, box_r) <= box_gap:
                continue
            if any(G.rect_dist(rect, G.peg_rect(p[0].astype(float), np.float64(p[1]))) <= pair_gap for p in placed):
                continue
            placed.append((s, yaw)); attempts.append(a); ok = True
            break
        if not ok:
            return None
    obj = int(torch.randint(0, 2, (1,), generator=g).item())
    dr = int(torch.randint(0, 2, (1,), generator=g).item())
    gaps = [float(G.rect_dist(G.peg_rect(placed[i][0].astype(float), np.float64(placed[i][1])),
                              G.peg_rect(placed[j][0].astype(float), np.float64(placed[j][1]))))
            for i in range(n) for j in range(i + 1, n)]
    bgap = min(float(G.rect_dist(G.peg_rect(p[0].astype(float), np.float64(p[1])), box_r)) for p in placed)
    return dict(pegs=placed, attempts=attempts, obj=obj, dir=dr, min_pair_gap=min(gaps), min_box_gap=bgap)


def episode(seed, pair_gap, box_gap):
    g = torch.Generator(); g.manual_seed(int(seed))
    lt = torch.rand(1, generator=g); rt = torch.rand(1, generator=g)
    length = (0.05 + (0.01 - 0.01) * lt).item(); radius = (0.01 + (0.005 - 0.005) * rt).item()
    torch.rand(3, generator=g); torch.randint(0, 4, (1,), generator=g)
    first = v5_init(g, length, radius, pair_gap, box_gap)     # gym.make construction initialization
    second = v5_init(g, length, radius, pair_gap, box_gap)    # reset initialization (effective layout)
    return first, second


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair-gap", type=float, default=0.03)
    ap.add_argument("--box-gap", type=float, default=0.01)
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()
    bg = None if a.box_gap < 0 else a.box_gap
    fails = 0; att = []; mg = []; mb = []; draws_equal_v4_peg0 = 0
    sys.path.insert(0, D)
    from replicate_v4 import draw_v4
    for k in range(a.n):
        seed = 5300000 + 100 * k  # V4 InsertPeg seed formula (offset 4e6 + code*1e5 + ep*100), extended to k<n
        f, s = episode(seed, a.pair_gap, bg)
        if f is None or s is None:
            fails += 1; continue
        att.append(s["attempts"]); mg.append(s["min_pair_gap"]); mb.append(s["min_box_gap"])
        if k < 200:
            v4 = draw_v4(seed)["initializations"]["1"]["pegs"]["0"]
            draws_equal_v4_peg0 += (abs(v4[0][0] - float(s["pegs"][0][0][0])) < 1e-9 and abs(v4[1] - s["pegs"][0][1]) < 1e-12)
    att = np.array(att)
    print(json.dumps({"pair_gap": a.pair_gap, "box_gap": bg, "seeds": a.n, "reset_fail": fails,
                      "attempts_mean_per_peg": np.round(att.mean(0), 2).tolist(), "attempts_max_per_peg": att.max(0).tolist(),
                      "min_pair_gap_min": round(min(mg), 4), "min_box_gap_min": round(min(mb), 4),
                      "effective_peg0_equal_to_V4_first200": int(draws_equal_v4_peg0)}))
