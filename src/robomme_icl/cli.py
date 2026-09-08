"""robomme-ICL 独立配置、认证、生成与回放入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def _task_list(value: str) -> list[str]:
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names or len(names) != len(set(names)):
        raise argparse.ArgumentTypeError("tasks 必须是无重复的逗号分隔任务名")
    return names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="robomme-ICL：认证冻结套件，再生成和严格回放")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="配置配额与位置，实跑两次严格认证后生成新 seed 套件")
    prepare.add_argument("--task-config", type=Path)
    prepare.add_argument("--position-config", type=Path)
    prepare.add_argument("--output", dest="output_dir", type=Path, required=True)
    prepare.add_argument("--max-candidates", type=int, help="诊断时缩小每个配额槽的候选上限")
    generate = commands.add_parser("generate", help="消费已认证套件；断点续跑不会改变 seed")
    generate.add_argument("--suite", type=Path, required=True)
    generate.add_argument("--output-dir", type=Path, required=True)
    for command in (prepare, generate):
        command.add_argument("--tasks", type=_task_list)
        command.add_argument("--episodes-per-task", type=int)
        command.add_argument("--workers", type=int, default=1)
        command.add_argument("--timeout-seconds", type=float, default=240)
    replay = commands.add_parser("replay", help="从新版 HDF5 独立重建规格并逐帧严格回放")
    replay.add_argument("--h5", dest="input", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--timeout-seconds", type=float, default=240)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout_seconds <= 0:
        raise ValueError("timeout-seconds 必须大于零")
    from .io.pipeline import generate_suite, prepare_suite, replay_episode

    if args.command == "prepare":
        result = prepare_suite(
            args.output_dir, task_config=args.task_config, position_config=args.position_config,
            tasks=args.tasks, episodes_per_task=args.episodes_per_task, workers=args.workers,
            max_candidates=args.max_candidates, timeout_seconds=args.timeout_seconds,
        )
        print(f"已发布认证套件：{result}")
    elif args.command == "generate":
        result = generate_suite(
            args.suite, args.output_dir, tasks=args.tasks, episodes_per_task=args.episodes_per_task,
            workers=args.workers, timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = replay_episode(args.input, args.output, timeout_seconds=args.timeout_seconds)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
