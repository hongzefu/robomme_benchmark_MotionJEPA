#!/usr/bin/env python3
"""V6 统一生成区域探针 C：在放宽区域 W 里用 numpy 抽 MoveCube 布局，生成回放规格。

W（桌面坐标，原点即桌面中心）：
  * goal、方块、杆根中心都在环带 0.06 ≤ |c| ≤ 0.24 且 x ≤ 0.20 里按面积均匀抽；
  * 杆 yaw、方块 yaw 全 2π 均匀；
  * 方块与 goal 中心距 ≥ 0.10；方块中心离杆身线段（根沿 -u 0.15、+u 0.05）≥ 0.04；
  * 额外保留 V5 xhard 现有规则：杆轴线段离 (0,0) ≥ 0.05（环境回放时 _assert_peg_outside_zone 会复核，
    不满足直接抛 EpisodeSpecError；这里预先过滤，不做 monkeypatch）。
演示段与执行段各自独立抽一套；way_idx 三种各 1/3。
"""
import csv
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SEED = 20260925
N = 36
R_IN, R_OUT, X_CAP = 0.06, 0.24, 0.20
MIN_CG, PEG_GAP, ZONE_R = 0.10, 0.04, 0.05
EXT = (-0.15, 0.05)
BASE = np.array([-0.615, 0.0])


def seg_dist(p, root, yaw, ext=EXT):
    u = np.array([math.cos(yaw), math.sin(yaw)])
    rel = p - root
    t = float(np.clip(rel @ u, ext[0], ext[1]))
    return float(np.linalg.norm(rel - t * u))


def in_w(rng):
    while True:
        c = rng.uniform(-R_OUT, R_OUT, size=2)
        r = np.linalg.norm(c)
        if R_IN <= r <= R_OUT and c[0] <= X_CAP:
            return c


def sample_segment(rng):
    """一段（演示或执行）：杆根+yaw → goal → 方块；返回 dict 与各级重抽次数。"""
    peg_tries = 0
    while True:
        peg_tries += 1
        root = in_w(rng)
        yaw = float(rng.uniform(-math.pi, math.pi))
        if seg_dist(np.zeros(2), root, yaw) >= ZONE_R:
            break
    goal = in_w(rng)
    cube_tries = 0
    while True:
        cube_tries += 1
        cube = in_w(rng)
        if np.linalg.norm(cube - goal) >= MIN_CG and seg_dist(cube, root, yaw) >= PEG_GAP:
            break
    cube_yaw = float(rng.uniform(0.0, 2 * math.pi))
    return {"root": root, "peg_yaw": yaw, "goal": goal, "cube": cube, "cube_yaw": cube_yaw,
            "peg_tries": peg_tries, "cube_tries": cube_tries}


def seg_spec(s):
    rx, ry = float(s["root"][0]), float(s["root"][1])
    base_y = 0.2 if ry >= 0 else -0.2
    return {
        # [base_y, x_jitter, y_jitter]：杆根 = (x_jitter, base_y + y_jitter)（float32 相加）
        "peg_offsets": [base_y, rx, ry - base_y],
        "peg_yaw": float(s["peg_yaw"]),
        "goal_xy": [float(s["goal"][0]), float(s["goal"][1])],
        # [x, y, yaw]：方块中心与绕 z 转角
        "cube_pose": [float(s["cube"][0]), float(s["cube"][1]), float(s["cube_yaw"])],
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=N)
    ap.add_argument("--ep-base", type=int, default=100)
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args()
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    header = json.loads((REPO / "scripts/configs/newtask-v5/v5-01/specs.jsonl").open().readline())
    sampling = header["sampling_config"]["MoveCube"]
    (out_dir / "sampling.json").write_text(json.dumps({"tasks": {"MoveCube": sampling}}, ensure_ascii=False))
    rows, specs, jobs = [], {}, {"0": [], "1": []}
    for i in range(a.n):
        way = i % 3
        demo, exe = sample_segment(rng), sample_segment(rng)
        episode = a.ep_base + i
        seed = 7_300_000 + (a.ep_base - 100) + i
        spec = {
            "spec_kind": "native-newvalue/1", "task": "MoveCube",
            "identity": {"task": "MoveCube", "episode": episode, "seed": seed, "difficulty": "xhard",
                         "recovery_mode": None},
            "initializations": {"0": {"way_idx": way}, "1": {"way_idx": way}},
            "layout": {"demo": seg_spec(demo), "execution": seg_spec(exe)},
            "objects": {"obj_sample": 1, "sampling_trace": {"dir_sample": 0}},
        }
        specs[f"MoveCube/{episode}"] = spec
        gpu = str(i % 2)
        jobs[gpu].append({"task": "MoveCube", "episode": episode, "seed": seed, "difficulty": "xhard",
                          "worker_dir": str(out_dir / "episodes" / f"MoveCube_episode_{episode}")})
        row = {"idx": i, "episode": episode, "seed": seed, "way_idx": way,
               "way": ["peg_push", "gripper_push", "grasp_putdown"][way], "gpu": gpu}
        for tag, s in (("demo", demo), ("exec", exe)):
            row.update({
                f"{tag}_peg_x": s["root"][0], f"{tag}_peg_y": s["root"][1], f"{tag}_peg_yaw": s["peg_yaw"],
                f"{tag}_goal_x": s["goal"][0], f"{tag}_goal_y": s["goal"][1],
                f"{tag}_cube_x": s["cube"][0], f"{tag}_cube_y": s["cube"][1], f"{tag}_cube_yaw": s["cube_yaw"],
                f"{tag}_cube_r": np.linalg.norm(s["cube"]), f"{tag}_goal_r": np.linalg.norm(s["goal"]),
                f"{tag}_cube_base_d": np.linalg.norm(s["cube"] - BASE),
                f"{tag}_goal_base_d": np.linalg.norm(s["goal"] - BASE),
                f"{tag}_peg_base_d": np.linalg.norm(s["root"] - BASE),
                f"{tag}_cube_goal_d": np.linalg.norm(s["cube"] - s["goal"]),
                f"{tag}_cube_peg_d": seg_dist(s["cube"], s["root"], s["peg_yaw"]),
                f"{tag}_goal_peg_d": seg_dist(s["goal"], s["root"], s["peg_yaw"]),
                f"{tag}_peg_tries": s["peg_tries"], f"{tag}_cube_tries": s["cube_tries"],
            })
        row["rng_seed"] = a.seed
        rows.append(row)
    with (out_dir / "layouts.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
    (out_dir / "specs.json").write_text(json.dumps({"specs": specs}, ensure_ascii=False, indent=1))
    for g, js in jobs.items():
        (out_dir / f"jobs_gpu{g}.json").write_text(json.dumps(js, indent=1))
    print(f"写出 {a.n} 局布局；GPU0 {len(jobs['0'])} 局，GPU1 {len(jobs['1'])} 局")


if __name__ == "__main__":
    main()
