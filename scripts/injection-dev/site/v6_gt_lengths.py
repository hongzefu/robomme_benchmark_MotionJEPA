"""统计 ground truth（生成侧 h5）的步数：演示段、执行段与合计，写 ``v6_gt_lengths.json`` 供站点使用。

- 步数 = h5 里 ``timestep_*`` 的个数；演示段 = ``info/is_video_demo`` 为真的时刻，执行段 = 其余时刻。
- 扩展难度 xhard1–4：取 SimpleMemVLA 评估用的每格 20 条（按 (task, seed) 对回生成侧 ``results.jsonl`` 的 h5）。
- 原版难度 hard：取站点原版示例的来源目录 ``artifacts/newtask-v6/v1/base/B`` 下每个 task 的全部 h5。
- 站点每条示例视频（``media-private.json``）另记它自己那条 h5 的三个数，供卡片显示「当前」。

用法：uv run --no-sync python scripts/injection-dev/site/v6_gt_lengths.py --records <SimpleMemVLA records 目录> --site-dir artifacts/newtask-v6/site-v12
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

import h5py

REPO = Path(__file__).resolve().parents[3]
ART = REPO / "artifacts/newtask-v6"
TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")
BASE = {"xhard1": ["xhard1-main-0927", "xhard1-fill-0927"], "xhard2": ["xhard2-0927"],
        "xhard3": ["xhard3-0927"], "xhard4": ["xhard4-0927", "xhard4-fill-0927"]}
RUNS = ["smvla-0927", "smvla-0927-fill"]


def h5_steps(path: Path) -> dict:
    with h5py.File(path, "r") as f:
        ep = f[next(iter(f.keys()))]
        names = [k for k in ep.keys() if k.startswith("timestep_")]
        demo = sum(bool(ep[k]["info/is_video_demo"][()]) for k in names)
    return {"demo": demo, "exec": len(names) - demo, "total": len(names)}


def dist(rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    for key in ("demo", "exec", "total"):
        vals = [r[key] for r in rows]
        out[key] = {"min": min(vals), "median": statistics.median(vals), "max": max(vals),
                    "mean": round(statistics.fmean(vals), 1)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, type=Path)
    ap.add_argument("--site-dir", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("v6_gt_lengths.json"))
    args = ap.parse_args()

    h5_by = {}  # (tier, task, seed) -> h5
    for run in RUNS:
        for tier in TIERS:
            res = ART / run / tier / "rollout/run1/results.jsonl"
            if res.exists():
                for line in res.read_text(encoding="utf-8").splitlines():
                    r = json.loads(line)
                    if r["ok"]:
                        h5_by[(tier, r["task"], r["seed"])] = REPO / r["h5"]

    cells = {}
    for tier in TIERS:
        seen = {}
        for d in BASE[tier]:
            for f in glob.glob(str(args.records / d / "results-*.jsonl")):
                for line in open(f, encoding="utf-8"):
                    r = json.loads(line)
                    seen[(r["task"], r["seed"])] = r
        by_task: dict[str, list] = {}
        for (task, seed) in sorted(seen):
            by_task.setdefault(task, []).append(h5_steps(h5_by[(tier, task, seed)]))
        for task, rows in by_task.items():
            cells[f"{tier}/{task}"] = dist(rows)
    hard: dict[str, list] = {}
    for p in sorted((ART / "v1/base/B").glob("*_episode_*/hdf5_files/*.h5")):
        hard.setdefault(p.parent.parent.name.split("_episode_")[0], []).append(h5_steps(p))
    for task, rows in hard.items():
        cells[f"hard/{task}"] = dist(rows)

    media = {}
    private = json.loads((args.site_dir / "media-private.json").read_text(encoding="utf-8"))
    for mid, video in private.items():
        h5s = sorted((Path(video).parent.parent / "hdf5_files").glob("*.h5"))
        if len(h5s) == 1:
            media[mid] = h5_steps(h5s[0])
    args.out.write_text(json.dumps({"schema": "v6-gt-lengths-1", "cells": cells, "media": media},
                                   ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"GT_LENGTHS=WRITTEN cells={len(cells)} media={len(media)}/{len(private)} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
