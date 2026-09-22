#!/usr/bin/env python3
"""从环境源码提取 `sampling_config` 原值快照（方案步 3，产出 G2 的对照件）。

每个已接口化的环境模块暴露 ``native_blocks(cls) -> (decision, native)``，本脚本把它们
汇成一份 `{"tasks": {<env>: {"decision": ..., "native": ...}}}`，供 C／D 路显式传入。
提取过程**不创建环境、不抽随机数**，只读类属性与模块级常量。

    uv run --no-sync python scripts/parity/train_split_config.py extract \
        --output scripts/configs/newtask-v3/native_sampling.json
    uv run --no-sync python scripts/parity/train_split_config.py extract --verify
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from seed_layout import ALL_TASKS  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "scripts" / "configs" / "newtask-v3" / "native_sampling.json"


def extract_task(task: str):
    """返回该环境的 (decision, native)；未接口化的环境返回 None。"""
    module = importlib.import_module(f"robomme.robomme_env.{task}")
    blocks = getattr(module, "native_blocks", None)
    if blocks is None:
        return None
    cls = getattr(module, task)
    decision, native = blocks(cls)
    return {"decision": decision, "native": native}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提取 sampling_config 原值快照")
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract", help="提取并写出快照")
    extract.add_argument("--env", default="all", help="all 或逗号分隔的环境名")
    extract.add_argument("--output", default=str(DEFAULT_OUTPUT))
    extract.add_argument("--verify", action="store_true", help="只比对既有文件字节，不写盘")
    args = parser.parse_args(argv)

    tasks = list(ALL_TASKS) if args.env == "all" else [t.strip() for t in args.env.split(",")]
    unknown = [t for t in tasks if t not in ALL_TASKS]
    if unknown:
        print(f"ERROR: 未知环境 {unknown}", file=sys.stderr)
        return 2

    payload: dict[str, object] = {}
    pending: list[str] = []
    for task in tasks:
        block = extract_task(task)
        if block is None:
            pending.append(task)
            continue
        payload[task] = block

    document = {
        "schema": "train-parity-sampling-config/1",
        "note": "原值快照：decision 与 native 两块都等于原值，第一轮不启用任何拟修改值",
        "tasks_total": len(ALL_TASKS),
        "tasks_ready": sorted(payload),
        "tasks_pending": pending,
        "tasks": {task: payload[task] for task in ALL_TASKS if task in payload},
    }
    data = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out = Path(args.output)
    if args.verify:
        if not out.exists():
            print(f"ERROR: {out} 不存在", file=sys.stderr)
            return 2
        if out.read_bytes() != data:
            print(f"ERROR: {out} 与源码提取结果不一致", file=sys.stderr)
            return 1
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    print(
        f"SAMPLING_CONFIG_EXTRACT={'VERIFY' if args.verify else 'WRITE'} "
        f"ready={len(payload)} pending={len(pending)} sha256={hashlib.sha256(data).hexdigest()[:16]}"
    )
    if pending:
        print(f"# 尚未接口化：{', '.join(pending)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
