#!/usr/bin/env python3
"""重要对拍⑤：同一 worker 连续生成时配置互不污染（测试侧，产品代码不导入）。

⑤.2 要求「同一实际 worker 执行：用例甲 → 不同任务的用例乙 → 再次用例甲」，
而生成器的 CLI 每个 (task, episode) 只排一次，排不出「甲→乙→甲」。
因此这里**直接用产品自己的 `_run_jobs` 与 `_worker`** 排三条 job：
不改 seed 公式、不另写求解循环、不改判定，只是把 job 顺序与各自的输出根排成这个形状
（`EpisodeJob.output_root` 本来就是逐 job 的字段，所以同一用例跑两次不会互相覆盖）。

乙固定含 VideoRepick，以覆盖它 `__init__` 里那行进程级全局副作用 `np.random.seed(seed)`。

⑤.1 的类级与进程级状态在父进程直接核对：四个任务类的类级 `configs`（含三份难度字典）
在整轮生成前后内容散列不变，父进程持有的配置散列不变。
注意本项**不**验证「改一个副本其他不变」——每次 attempt 都新建环境、`EpisodeJob` 经 pickle
逐条送进 worker，那个断言在多进程链路下恒真，没有鉴别力。

用法（必须带观察器环境变量，否则不产出 ②/④ 证据）::

    PYTHONPATH=tests/_shared/parity_sitecustomize PARITY_OBSERVER_DIR=tests/_shared \\
    PARITY_EVIDENCE_DIR=artifacts/parity-evidence/<run>/S PARITY_LABEL=S \\
    uv run --no-sync python -m tests._shared.parity_worker_isolation --run-id <run>
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = os.environ.get("PARITY_BASELINE") == "1"
RUN_REPO_ROOT = REPO_ROOT / "artifacts" / "native-baseline" if BASELINE else REPO_ROOT
SCRIPTS_DIR = RUN_REPO_ROOT / "scripts" / "data-generation-newSeed" if BASELINE else REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_dataset_newseed as generator  # noqa: E402
import seed_layout  # noqa: E402

CONFIG_PATH = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
SAMPLING_TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")
_PRODUCT_WORKER = generator._worker


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=repr).encode("utf-8")
    ).hexdigest()


def _class_config_hashes() -> dict[str, str]:
    """四个任务类的类级 configs 内容散列（导入仿真，只在父进程做一次）。"""
    if str(RUN_REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(RUN_REPO_ROOT / "src"))
    import importlib

    hashes: dict[str, str] = {}
    for task in SAMPLING_TASKS:
        module = importlib.import_module(f"robomme.robomme_env.{task}")
        task_class = getattr(module, task)
        hashes[task] = _hash(task_class.configs)
    return hashes


def _checked_worker(job):
    """在真实池进程内核对类级配置；只包原 worker，不另写生成循环。"""
    before = _class_config_hashes()
    result = _PRODUCT_WORKER(job)
    after = _class_config_hashes()
    result["worker_class_config_before"] = before
    result["worker_class_config_after"] = after
    result["worker_class_config_unchanged"] = before == after
    return result


def build_jobs(
    output_root: Path,
    with_config: bool,
    first: tuple[str, int, str],
    second: tuple[str, int, str],
) -> tuple[list[Any], dict[str, Any]]:
    """排出「甲 → 乙 → 甲」三条 job，各自独立的输出根。"""
    layout = seed_layout.get_layout("train")
    task_configs = generator.load_sampling_config(CONFIG_PATH, REPO_ROOT) if with_config else {}
    plan = [("first-a", first), ("second-b", second), ("first-again", first)]
    jobs = []
    detail: dict[str, Any] = {"order": [], "sampling_config": bool(with_config)}
    for slot, (task, episode, difficulty) in plan:
        target = output_root / slot
        target.mkdir(parents=True, exist_ok=True)
        seed = layout.seed(task, episode, 0)
        jobs.append(
            generator.EpisodeJob(
                task=task,
                episode=episode,
                attempt=0,
                seed=seed,
                difficulty=difficulty,
                output_root=str(target),
                repo_root=str(RUN_REPO_ROOT),
                **({"sampling_config": copy.deepcopy(task_configs[task]) if task in task_configs else None} if not BASELINE else {}),
            )
        )
        detail["order"].append(
            {"slot": slot, "task": task, "episode": episode, "difficulty": difficulty, "seed": seed,
             "output_dir": str(target)}
        )
    return jobs, detail


def run(
    run_id: str,
    with_config: bool,
    first: tuple[str, int, str],
    second: tuple[str, int, str],
) -> dict[str, Any]:
    if BASELINE and with_config:
        raise ValueError("原基线连续 worker 不接受 sampling_config")
    label = "S-baseline" if BASELINE else ("S-config" if with_config else "S-default")
    output_root = RUN_REPO_ROOT / "artifacts" / "parity" / run_id / "worker-isolation" / label
    output_root.mkdir(parents=True, exist_ok=True)

    before_class = _class_config_hashes()
    jobs, detail = build_jobs(output_root, with_config, first, second)
    before_parent = _hash([getattr(job, "sampling_config", None) for job in jobs])

    generator._worker = _checked_worker
    try:
        succeeded, exhausted = generator._run_jobs(
            jobs=jobs,
            gpu_ids=("0",),
            workers=1,
            layout_name="train",
            jsonl_path=output_root / "episode_results.jsonl",
            max_attempts=1,
            # 固定 8：三条 job 必须落在同一个池进程里。
            max_tasks_per_child=8,
            cpu_plan={"0": None},
        )
    finally:
        generator._worker = _PRODUCT_WORKER
    after_class = _class_config_hashes()
    after_parent = _hash([getattr(job, "sampling_config", None) for job in jobs])

    workers_used = sorted({item.get("bound", {}).get("pid") for item in succeeded if item.get("bound")})
    return {
        "label": label,
        "plan": detail,
        "success_count": len(succeeded),
        "exhausted_count": len(exhausted),
        "worker_pids": workers_used,
        "same_worker": len(workers_used) == 1,
        "class_config_hash_before": before_class,
        "class_config_hash_after": after_class,
        "class_config_unchanged": before_class == after_class,
        "worker_class_config_unchanged": len(succeeded) == 3 and all(item.get("worker_class_config_unchanged") for item in succeeded),
        "parent_config_hash_before": before_parent,
        "parent_config_hash_after": after_parent,
        "parent_config_unchanged": before_parent == after_parent,
        "results": [
            {key: item.get(key) for key in ("task", "episode", "seed", "difficulty", "ok", "wall_s", "h5_path",
                "worker_class_config_before", "worker_class_config_after", "worker_class_config_unchanged")}
            for item in succeeded + exhausted
        ],
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重要对拍⑤：同一 worker 连续生成的隔离性")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--with-config", action="store_true", help="显式传原值配置那一路")
    parser.add_argument("--first", default="BinFill:0:easy", help="用例甲，task:episode:difficulty")
    parser.add_argument("--second", default="VideoRepick:0:easy", help="用例乙，须含 VideoRepick")
    args = parser.parse_args(argv)

    def parse(text: str) -> tuple[str, int, str]:
        task, episode, difficulty = text.split(":")
        return task, int(episode), difficulty

    report = run(args.run_id, args.with_config, parse(args.first), parse(args.second))
    target = (
        REPO_ROOT / "artifacts" / "parity" / args.run_id / "worker-isolation" / f"{report['label']}.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"class_config_hash_before", "class_config_hash_after"}}, ensure_ascii=False, indent=2))
    return 0 if report["success_count"] == 3 and report["same_worker"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
