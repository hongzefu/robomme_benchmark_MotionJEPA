#!/usr/bin/env python3
"""GL 复测批：按统一区域 U（region.py）抽 MoveCube 布局并生成回放规格（格式与探针 C 相同）。"""
import csv
import json
import math
from pathlib import Path

import numpy as np

from region import P, BASE, sample_segment, seg_dist

HERE = Path(__file__).resolve().parent


def seg_spec(s):
    rx, ry = float(s["root"][0]), float(s["root"][1])
    base_y = 0.2 if ry >= 0 else -0.2
    return {
        "peg_offsets": [base_y, rx, ry - base_y],      # 杆根 = (x_jitter, base_y + y_jitter)
        "peg_yaw": float(s["peg_yaw"]),
        "goal_xy": [float(s["goal"][0]), float(s["goal"][1])],
        "cube_pose": [float(s["cube"][0]), float(s["cube"][1]), float(s["cube_yaw"])],
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--n", type=int, default=144)
    ap.add_argument("--ep-base", type=int, default=400)
    ap.add_argument("--specs-header", required=True, help="v5-01 specs.jsonl（取 MoveCube 采样配置块）")
    ap.add_argument("--episodes-root", required=True, help="逐局产物目录（GL 上用节点本地 /tmp）")
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    header = json.loads(Path(a.specs_header).open().readline())
    (out / "sampling.json").write_text(json.dumps({"tasks": {"MoveCube": header["sampling_config"]["MoveCube"]}}, ensure_ascii=False))
    rows, specs, jobs = [], {}, []
    for i in range(a.n):
        way = i % 3
        demo, exe = sample_segment(rng), sample_segment(rng)
        episode = a.ep_base + i
        seed = 7_400_000 + i
        specs[f"MoveCube/{episode}"] = {
            "spec_kind": "native-newvalue/1", "task": "MoveCube",
            "identity": {"task": "MoveCube", "episode": episode, "seed": seed, "difficulty": "xhard", "recovery_mode": None},
            "initializations": {"0": {"way_idx": way}, "1": {"way_idx": way}},
            "layout": {"demo": seg_spec(demo), "execution": seg_spec(exe)},
            "objects": {"obj_sample": 1, "sampling_trace": {"dir_sample": 0}},
        }
        jobs.append({"task": "MoveCube", "episode": episode, "seed": seed, "difficulty": "xhard",
                     "worker_dir": str(Path(a.episodes_root) / f"MoveCube_episode_{episode}")})
        row = {"idx": i, "episode": episode, "seed": seed, "way_idx": way,
               "way": ["peg_push", "gripper_push", "grasp_putdown"][way], "gpu": "0"}
        for tag, s in (("demo", demo), ("exec", exe)):
            row.update({
                f"{tag}_peg_x": s["root"][0], f"{tag}_peg_y": s["root"][1], f"{tag}_peg_yaw": s["peg_yaw"],
                f"{tag}_tail_x": s["tail"][0], f"{tag}_tail_y": s["tail"][1],
                f"{tag}_goal_x": s["goal"][0], f"{tag}_goal_y": s["goal"][1],
                f"{tag}_cube_x": s["cube"][0], f"{tag}_cube_y": s["cube"][1], f"{tag}_cube_yaw": s["cube_yaw"],
                f"{tag}_cube_r": np.linalg.norm(s["cube"]), f"{tag}_goal_r": np.linalg.norm(s["goal"]),
                f"{tag}_cube_base_d": np.linalg.norm(s["cube"] - BASE), f"{tag}_goal_base_d": np.linalg.norm(s["goal"] - BASE),
                f"{tag}_peg_base_d": np.linalg.norm(s["root"] - BASE), f"{tag}_tail_base_d": np.linalg.norm(s["tail"] - BASE),
                f"{tag}_cube_goal_d": np.linalg.norm(s["cube"] - s["goal"]),
                f"{tag}_cube_peg_d": seg_dist(s["cube"], s["root"], s["peg_yaw"]),
                f"{tag}_goal_peg_d": seg_dist(s["goal"], s["root"], s["peg_yaw"]),
                f"{tag}_peg_tries": s["peg_tries"], f"{tag}_goal_tries": s["goal_tries"], f"{tag}_cube_tries": s["cube_tries"],
            })
        row["rng_seed"] = a.seed
        rows.append(row)
    with (out / "layouts.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
    (out / "specs.json").write_text(json.dumps({"specs": specs}, ensure_ascii=False, indent=1))
    (out / "jobs_gpu0.json").write_text(json.dumps(jobs, indent=1))
    (out / "region_params.json").write_text(json.dumps(P, indent=1))
    print(f"写出 {a.n} 局布局到 {out}")


if __name__ == "__main__":
    main()
