#!/usr/bin/env python3
"""按失败所在段取布局特征，比较成功/失败分布（打印 markdown 片段）。"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

BASE = np.array([-0.615, 0.0])


def seg_feats(L, s):
    c = np.array([L[f"{s}_cube_x"], L[f"{s}_cube_y"]])
    g = np.array([L[f"{s}_goal_x"], L[f"{s}_goal_y"]])
    root = np.array([L[f"{s}_peg_x"], L[f"{s}_peg_y"]])
    yaw = L[f"{s}_peg_yaw"]
    u = np.array([math.cos(yaw), math.sin(yaw)])
    tail = root - 0.1 * u  # 抓杆点（peg_tail 中心）
    d = (g - c) / np.linalg.norm(g - c)
    lat = np.array([-d[1], d[0]])
    direction = 1 if c[1] - g[1] > 0 else -1
    pp_start = c - 0.1 * d - 0.1 * direction * lat
    pp_end = g - 0.03 * d - 0.1 * direction * lat
    gp_start = c - 0.05 * d
    return {
        "cube_base": float(np.linalg.norm(c - BASE)), "goal_base": float(np.linalg.norm(g - BASE)),
        "tail_base": float(np.linalg.norm(tail - BASE)), "tail_x": float(tail[0]),
        "cube_x": float(c[0]), "goal_x": float(g[0]), "cube_r": float(np.linalg.norm(c)), "goal_r": float(np.linalg.norm(g)),
        "push_len": float(np.linalg.norm(g - c)),
        "push_ang_deg": float(np.degrees(math.atan2(d[1], d[0]))),  # 推送方向（0°=+x 远离机器人）
        "pp_reach": float(max(np.linalg.norm(pp_start - BASE), np.linalg.norm(pp_end - BASE))),
        "gp_reach": float(max(np.linalg.norm(gp_start - BASE), np.linalg.norm(g - 0.02 * d - BASE))),
        "peg_yaw_deg": float(np.degrees(yaw)), "cube_yaw_deg": float(np.degrees(L[f"{s}_cube_yaw"]) % 90),
        "peg_root_base": float(np.linalg.norm(root - BASE)),
    }


def main():
    dirs = sys.argv[1:]
    rs = []
    for d in dirs:
        rs += [json.loads(l) for l in (Path(d) / "results.jsonl").open()]
    for r in rs:
        r["f"] = {s: seg_feats(r["layout"], s) for s in ("demo", "exec")}
    json.dump([{k: r[k] for k in ("batch", "episode", "way", "ok", "category", "fail_phase", "fail_subtask", "f")} for r in rs],
              open("features.json", "w"), ensure_ascii=False, indent=0)
    keys = ["cube_base", "goal_base", "tail_base", "pp_reach", "gp_reach", "push_len", "cube_x", "goal_x", "tail_x"]
    for way in ("peg_push", "gripper_push", "grasp_putdown"):
        sub = [r for r in rs if r["way"] == way]
        print(f"\n## {way}  成功 {sum(r['ok'] for r in sub)}/{len(sub)}")
        print(Counter((r["category"], r["fail_phase"], r["fail_subtask"]) for r in sub if not r["ok"]))
        # 成功局两段都算「成功段」；失败局只取失败段；未失败的那一段（若在失败段之前）也算成功段
        okseg, badseg = [], []
        for r in sub:
            if r["ok"]:
                okseg += [r["f"]["demo"], r["f"]["exec"]]
            elif r["fail_phase"] in ("demo", "exec"):
                badseg.append(r["f"][r["fail_phase"]])
                if r["fail_phase"] == "exec":
                    okseg.append(r["f"]["demo"])
        print(f"成功段 n={len(okseg)}  失败段 n={len(badseg)}")
        for k in keys:
            a = np.array([f[k] for f in okseg]); b = np.array([f[k] for f in badseg])
            if len(b):
                print(f"  {k:10s} 成功段 中位 {np.median(a):.3f} [p10 {np.percentile(a,10):.3f}, p90 {np.percentile(a,90):.3f}]   "
                      f"失败段 中位 {np.median(b):.3f} [min {b.min():.3f}, max {b.max():.3f}]")
        for r in sub:
            if not r["ok"] and r["fail_phase"] in ("demo", "exec"):
                f = r["f"][r["fail_phase"]]
                print(f"  失败 ep{r['episode']} {r['category']} {r['fail_phase']}/{r['fail_subtask']}: "
                      + " ".join(f"{k}={f[k]:.3f}" for k in ("cube_base", "goal_base", "tail_base", "tail_x", "pp_reach", "push_len"))
                      + f" push_ang={f['push_ang_deg']:.0f}° peg_yaw={f['peg_yaw_deg']:.0f}° cube_yaw%90={f['cube_yaw_deg']:.0f}°")


if __name__ == "__main__":
    main()
