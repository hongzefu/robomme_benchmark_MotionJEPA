"""按 metadata 里的死 seed 实跑 test split，绝不让 seed 漂移。

为什么不用 `generate_dataset_newseed.py --layout test`：那是**生成型**入口，seed 按公式从
attempt=0 起算、失败才 +1。而 test metadata 里有一批 seed 尾号非 0（当年 attempt=0 失败过），
例如 BinFill test ep{1,2,3,7,16,18,20,35}、PickXtimes test ep15。当前环境代码比 2025-12 更容易通过，
这些 episode 很可能在 attempt=0 就成功 —— 于是拿到的是**另一个场景**，参数与时长都对不上原版。

本脚本改为逐条锁死 metadata 的 (seed, difficulty)，并把 max_attempts 设成 1：
失败即放弃、绝不 bump seed。复用 generate_dataset_newseed 的 worker 与进程池，不改那边任何代码。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parents[2] / "patternlock-routestick-params"
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "legacy" / "data-generation-newSeed"))

import generate_dataset_newseed as gen  # noqa: E402

METADATA_ROOT = REPO_ROOT / "src" / "robomme" / "env_metadata"


def build_jobs(
    tasks: list[str], split: str, output: Path, episodes: list[int] | None
) -> list[gen.EpisodeJob]:
    jobs: list[gen.EpisodeJob] = []
    for task in tasks:
        path = METADATA_ROOT / split / f"record_dataset_{task}_metadata.json"
        for record in json.loads(path.read_text(encoding="utf-8"))["records"]:
            episode = int(record["episode"])
            if episodes is not None and episode not in episodes:
                continue
            seed = int(record["seed"])
            jobs.append(
                gen.EpisodeJob(
                    task=task,
                    episode=episode,
                    # attempt 照抄 metadata 的 seed 尾号，纯粹为留痕；max_attempts=1 保证它不会被 bump
                    attempt=seed % 100,
                    seed=seed,
                    difficulty=record["difficulty"],
                    output_root=str(output),
                    repo_root=str(REPO_ROOT),
                )
            )
    return jobs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按 metadata 死 seed 实跑指定 split")
    parser.add_argument("--output-dir", required=True, help="仓库内的输出目录")
    parser.add_argument("--env", "--environment", dest="env", required=True, help="逗号分隔的环境名")
    parser.add_argument("--split", default="test", choices=("train", "test", "val"))
    parser.add_argument("--episodes", default="all", help="all 或逗号分隔的 episode 号")
    parser.add_argument("--workers", type=int, default=gen.DEFAULT_WORKERS)
    parser.add_argument("--gpus", "--gpu", dest="gpus", default="0")
    parser.add_argument("--max-tasks-per-child", type=int, default=gen.DEFAULT_MAX_TASKS_PER_CHILD)
    parser.add_argument("--affinity", default="none", choices=("none", "per-gpu"))
    args = parser.parse_args(argv)

    gen._ensure_layout()
    output = gen._prepare_output(args.output_dir)
    tasks = [item.strip() for item in args.env.split(",") if item.strip()]
    gpu_ids = gen._parse_gpus(args.gpus)
    episodes = None if args.episodes == "all" else [int(x) for x in args.episodes.split(",")]

    os.environ[gen.LIMIT_THREADS_ENV] = "1"
    gen._apply_thread_env("1")

    jobs = build_jobs(tasks, args.split, output, episodes)
    if not jobs:
        raise SystemExit("没有匹配到任何 episode")
    fixed = [j for j in jobs if j.attempt]
    print(
        f"共 {len(jobs)} 条 job（split={args.split}），其中 seed 尾号非 0 的 {len(fixed)} 条："
        + ", ".join(f"{j.task}/ep{j.episode}=seed {j.seed}" for j in fixed),
        flush=True,
    )

    parameters = {
        "output_dir": str(output),
        "env": args.env,
        "tasks": tasks,
        "split": args.split,
        "seed_source": "env_metadata（死 seed，锁死不重试）",
        "episodes": "all" if episodes is None else episodes,
        "workers": args.workers,
        "gpus": list(gpu_ids),
        "max_attempts": 1,
        "max_tasks_per_child": args.max_tasks_per_child,
        "affinity": args.affinity,
    }
    gen.write_text_atomic(
        output / "run_parameters.json",
        json.dumps(parameters, ensure_ascii=False, indent=2) + "\n",
    )

    started = time.monotonic()
    succeeded, exhausted = gen._run_jobs(
        jobs=jobs,
        gpu_ids=gpu_ids,
        workers=args.workers,
        # layout 只在 bump seed 时被用到；max_attempts=1 使那条分支永不触发，这里给谁都不影响结果
        layout_name=args.split if args.split in gen.LAYOUTS else "test",
        jsonl_path=output / "episode_results.jsonl",
        max_attempts=1,
        max_tasks_per_child=args.max_tasks_per_child,
        cpu_plan=gen._cpu_plan(gpu_ids, args.affinity),
    )
    elapsed = time.monotonic() - started

    summary: dict[str, Any] = {
        "parameters": parameters,
        "requested_count": len(jobs),
        "success_count": len(succeeded),
        "failed_count": len(exhausted),
        "failed": [
            {
                "task": item["task"],
                "episode": item["episode"],
                "seed": item["seed"],
                "failure_class": item.get("failure_class"),
                "error_type": item.get("error_type"),
            }
            for item in exhausted
        ],
        "elapsed_s": round(elapsed, 1),
    }
    gen.write_text_atomic(
        output / "run_summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
