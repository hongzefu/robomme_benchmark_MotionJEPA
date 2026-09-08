#!/usr/bin/env python3
"""把无 seed 生成的 metadata 追加进 ``src/robomme/env_metadata/train``。

用于接续生成场景（如既有 ep0–99、新生成 ep100–399）：读输出目录里的
``record_dataset_{task}_metadata.json``，与 train 现有记录合并后原样写回。
三条硬性断言，任一不满足即整体拒绝、不落盘：

1. 新旧 episode 集合无重叠（不允许覆盖既有记录——ep0–99 一字不动是本工具的前提）；
2. 合并后 episode 连续（0..N-1，消费侧按 episode 号索引，不允许出现空洞）；
3. 输入 json 的 ``env_id`` 与目标文件一致。

序列化口径与现有文件逐字对齐：indent=2、ensure_ascii=False、结尾无换行符，
保证 git diff 呈现为纯追加。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent          # .../data-generation-newSeed/utils
NEWSEED_DIR = SCRIPT_DIR.parent                       # .../data-generation-newSeed
CONTRACT_DIR = SCRIPT_DIR.parents[1] / "data-generation"
for _extra in (str(NEWSEED_DIR), str(CONTRACT_DIR)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from validate_generated_dataset_contract import METADATA_ROOT, parse_tasks  # noqa: E402
from write_generation_report import write_text_atomic  # noqa: E402


class AppendMetadataError(RuntimeError):
    """输入不满足追加前提。"""


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AppendMetadataError(f"找不到 metadata 文件：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("env_id", "records"):
        if key not in payload:
            raise AppendMetadataError(f"{path} 缺少 {key} 字段")
    return payload


def merge_records(
    task: str,
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """合并两份 metadata payload，返回可直接落盘的新 payload。"""
    for payload, origin in ((existing, "train"), (incoming, "输入")):
        if str(payload["env_id"]) != task:
            raise AppendMetadataError(
                f"{task}: {origin}侧 env_id 为 {payload['env_id']!r}，与任务名不符"
            )

    old_records = {int(item["episode"]): item for item in existing["records"]}
    new_records = {int(item["episode"]): item for item in incoming["records"]}
    if not new_records:
        raise AppendMetadataError(f"{task}: 输入 metadata 没有任何 records")

    overlap = sorted(old_records.keys() & new_records.keys())
    if overlap:
        raise AppendMetadataError(
            f"{task}: 新记录与既有记录的 episode 重叠（前几个：{overlap[:5]}），"
            "本工具只做纯追加，不允许覆盖"
        )

    merged = {**old_records, **new_records}
    expected = list(range(len(merged)))
    actual = sorted(merged)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))[:5]
        raise AppendMetadataError(
            f"{task}: 合并后 episode 不连续（应为 0..{len(merged) - 1}，缺 {missing} 等）"
        )

    return {
        "env_id": task,
        "record_count": len(merged),
        "records": [
            {
                "task": str(item["task"]),
                "episode": int(item["episode"]),
                "seed": int(item["seed"]),
                "difficulty": str(item["difficulty"]),
            }
            for _, item in sorted(merged.items())
        ],
    }


def plan_task(input_dir: Path, metadata_dir: Path, task: str) -> dict[str, Any]:
    """校验并算出该 task 的合并结果，不落盘。"""
    target = metadata_dir / f"record_dataset_{task}_metadata.json"
    existing = _load_payload(target)
    incoming = _load_payload(input_dir / f"record_dataset_{task}_metadata.json")
    merged = merge_records(task, existing, incoming)

    new_episodes = sorted(int(item["episode"]) for item in incoming["records"])
    return {
        "task": task,
        "target": target,
        "merged": merged,
        "old_count": len(existing["records"]),
        "appended": len(new_episodes),
        "new_count": merged["record_count"],
        "appended_range": f"{new_episodes[0]}..{new_episodes[-1]}",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把无 seed 生成的 metadata 追加进 src/robomme/env_metadata/train"
    )
    parser.add_argument("--input-dir", required=True, help="generate_dataset_newseed.py 的输出目录")
    parser.add_argument("--env", "--environment", default="all", help="all 或逗号分隔的环境名")
    parser.add_argument(
        "--metadata-dir",
        default=str(METADATA_ROOT),
        help="要写回的 metadata 目录（默认 src/robomme/env_metadata/train）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将发生的变化，不落盘")
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir)
    metadata_dir = Path(args.metadata_dir)
    tasks = parse_tasks(args.env)

    # 两阶段：先把全部 task 校验合并完，任一失败即整体拒绝；全部通过后才统一落盘。
    try:
        plans = [plan_task(input_dir, metadata_dir, task) for task in tasks]
    except AppendMetadataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("未写入任何文件。", file=sys.stderr)
        return 1

    if not args.dry_run:
        for item in plans:
            # 与现有文件逐字同口径：indent=2、结尾无换行
            write_text_atomic(item["target"], json.dumps(item["merged"], ensure_ascii=False, indent=2))

    mode = "dry-run，未落盘" if args.dry_run else "已写入"
    for item in plans:
        print(
            f"{item['task']}: {item['old_count']} 条 + 追加 {item['appended']} 条"
            f"（ep{item['appended_range']}）→ {item['new_count']} 条（{mode}）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
