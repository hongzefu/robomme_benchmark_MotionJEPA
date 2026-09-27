"""P6 离线估计：V5 规则下抓取点离基座水平距离 > 阈值的比例，以及收窄杆区后的变化（只估计，不改规则）。

抽样顺序与 V5 原型相同（torch 生成器、lazy yaw、0.03 / 0.01 轮廓间隔），只把杆区 x/y 范围参数化。
抓取点：obj_sample==0 → obj_flag=-1 → 抓 head（= root）；否则抓 tail（= root − L·u）。
另外输出 V4 正式 10 局（冻结规格）的抓取点距离，供与演示结果对照。
"""
import sys, json
import numpy as np
import torch
D = __file__.rsplit('/', 1)[0]; sys.path.insert(0, D)
import peggeom as G

BASE = np.array([-0.615, 0.0])
REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"


def v5_init(g, x_lo, x_hi, y_lo, y_hi, pair_gap=0.03, box_gap=0.01, n=4, maxa=512):
    xj = (torch.rand(1, generator=g).item() - 0.5) * 0.2
    yj = (torch.rand(1, generator=g).item() - 0.5) * 0.2
    box_yaw = np.pi / 2 + (torch.rand(1, generator=g).item() * 2 - 1) * np.radians(20)
    box_xy = np.array([xj, yj], dtype=np.float32)
    box_r = G.box_rect(box_xy.astype(float), np.float64(box_yaw))
    placed = []
    for i in range(n):
        for a in range(maxa):
            x = torch.rand(1, generator=g).item() * (x_hi - x_lo) + x_lo
            y = torch.rand(1, generator=g).item() * (y_hi - y_lo) + y_lo
            s = np.array([x, y], dtype=np.float32)
            if np.linalg.norm(s - box_xy) <= G.R * 6: continue
            if any(np.linalg.norm(s - p[0]) <= G.L * 1.5 for p in placed): continue
            yaw = (torch.rand(1, generator=g).item() * 2 - 1) * np.pi
            r = G.peg_rect(s.astype(float), np.float64(yaw))
            if G.rect_dist(r, box_r) <= box_gap: continue
            if any(G.rect_dist(r, G.peg_rect(p[0].astype(float), np.float64(p[1]))) <= pair_gap for p in placed): continue
            placed.append((s, yaw)); break
        else:
            return None
    obj = int(torch.randint(0, 2, (1,), generator=g).item())
    torch.randint(0, 2, (1,), generator=g)
    root, yaw = placed[0]
    grasp = root.astype(float) if obj == 0 else root.astype(float) - G.L * G.axis(np.float64(yaw))
    return float(np.linalg.norm(grasp - BASE)), placed


def episode(seed, region):
    g = torch.Generator(); g.manual_seed(int(seed))
    torch.rand(1, generator=g); torch.rand(1, generator=g); torch.rand(3, generator=g); torch.randint(0, 4, (1,), generator=g)
    if v5_init(g, *region) is None:
        return None
    return v5_init(g, *region)


REGIONS = {
    "当前 x[-0.2,0.2] y[-0.3,0.3]": (-0.2, 0.2, -0.3, 0.3),
    "x[-0.2,0.15] y[-0.3,0.3]": (-0.2, 0.15, -0.3, 0.3),
    "x[-0.2,0.2] y[-0.25,0.25]": (-0.2, 0.2, -0.25, 0.25),
    "x[-0.2,0.15] y[-0.25,0.25]": (-0.2, 0.15, -0.25, 0.25),
    "x[-0.2,0.1] y[-0.25,0.25]": (-0.2, 0.1, -0.25, 0.25),
    "x[-0.2,0.1] y[-0.2,0.2]": (-0.2, 0.1, -0.2, 0.2),
}

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    out = {}
    for name, reg in REGIONS.items():
        ds = []; fail = 0
        for k in range(n):
            r = episode(7300000 + 100 * k, reg)
            if r is None: fail += 1; continue
            ds.append(r[0])
        ds = np.array(ds)
        out[name] = {"n": n, "layout_fail": fail, "p50": round(float(np.median(ds)), 3), "p95": round(float(np.quantile(ds, .95)), 3),
                     "gt_0.74": round(float((ds > 0.74).mean()), 3), "gt_0.76": round(float((ds > 0.76).mean()), 3),
                     "gt_0.78": round(float((ds > 0.78).mean()), 3), "gt_0.80": round(float((ds > 0.80).mean()), 3)}
        print(name, json.dumps(out[name], ensure_ascii=False), flush=True)
    # V4 正式 10 局冻结规格的抓取点距离
    rows = [json.loads(l) for l in open(f"{REPO}/scripts/configs/newtask-v4/v4-01/specs.jsonl")][1:]
    v4 = {}
    for r in rows:
        if r["task"] != "InsertPeg": continue
        init = r["spec"]["initializations"][str(max(int(k) for k in r["spec"]["initializations"]))]
        (x, y), yaw = init["pegs"]["0"]
        root = np.array([x, y]); obj = init["obj_sample"]
        grasp = root if obj == 0 else root - G.L * G.axis(np.float64(yaw))
        v4[r["episode"]] = round(float(np.linalg.norm(grasp - BASE)), 3)
    out["V4_grasp_dist_by_episode"] = v4
    print("V4", json.dumps(v4))
    json.dump(out, open(D + "/reach_offline.json", "w"), ensure_ascii=False, indent=1)
