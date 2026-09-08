#!/usr/bin/env python3
"""把每 episode 的 h5 合并成与官方一致的 record_dataset_{task}.h5。

生成入口不做合并（避免生成期就把体量翻倍，也让单条失败不牵连其余产物），
需要合并时单独跑本脚本。

源文件按生成期写出的 ``record_dataset_{task}_metadata.json`` 逐条定位，而不是 glob ——
这样即便目录里混有失败 attempt 的残留也不会被误吸，缺文件时能明确指出是哪一条。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import h5py


SCRIPT_DIR = Path(__file__).resolve().parent
CONTRACT_DIR = SCRIPT_DIR.parent / "data-generation"
for _extra in (str(SCRIPT_DIR), str(CONTRACT_DIR)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from validate_generated_dataset_contract import parse_tasks  # noqa: E402


class MergeError(RuntimeError):
    """合并的输入不完整或结构不符。"""


def _sources(input_dir: Path, task: str) -> list[tuple[int, Path]]:
    metadata_path = input_dir / f"record_dataset_{task}_metadata.json"
    if not metadata_path.is_file():
        raise MergeError(f"缺少 metadata：{metadata_path}")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    records = sorted(payload["records"], key=lambda item: int(item["episode"]))
    sources: list[tuple[int, Path]] = []
    missing: list[str] = []
    for record in records:
        episode = int(record["episode"])
        seed = int(record["seed"])
        path = input_dir / "hdf5_files" / f"{task}_ep{episode}_seed{seed}.h5"
        if not path.is_file():
            missing.append(f"episode_{episode}(seed={seed}) → {path.name}")
            continue
        sources.append((episode, path))
    if missing:
        raise MergeError(f"{task}: 有 {len(missing)} 条源文件缺失：" + "; ".join(missing[:10]))
    return sources


def merge_task(input_dir: Path, output_dir: Path, task: str, delete_source: bool) -> dict[str, Any]:
    """合并逻辑与骨架 generate_dataset.py 的 _merge 一致：临时文件 + 原子替换。"""
    sources = _sources(input_dir, task)
    target = output_dir / f"record_dataset_{task}.h5"
    temporary = output_dir / f".record_dataset_{task}.h5.tmp"
    try:
        with h5py.File(temporary, "w") as merged:
            for episode, path in sources:
                name = f"episode_{episode}"
                with h5py.File(str(path), "r") as raw:
                    if name not in raw:
                        raise MergeError(f"{path}: 缺少 {name}")
                    raw.copy(raw[name], merged, name=name)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    if delete_source:
        for _, path in sources:
            path.unlink(missing_ok=True)

    return {
        "task": task,
        "episode_count": len(sources),
        "target": str(target),
        "bytes": target.stat().st_size,
        "source_deleted": delete_source,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把每 episode 的 h5 合并成 record_dataset_{task}.h5")
    parser.add_argument("--input-dir", required=True, help="generate_dataset_newseed.py 的输出目录")
    parser.add_argument("--output-dir", default=None, help="合并结果的落点，默认与 --input-dir 相同")
    parser.add_argument("--env", "--environment", default="all", help="all 或逗号分隔的环境名")
    parser.add_argument(
        "--delete-source",
        action="store_true",
        help="合并成功后删除每 episode 的源 h5（默认保留；合并期间两份并存，需要双倍空间）",
    )
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_dir
    if not input_dir.is_dir():
        print(f"ERROR: 输入目录不存在：{input_dir}", file=sys.stderr)
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for task in parse_tasks(args.env):
        try:
            result = merge_task(input_dir, output_dir, task, args.delete_source)
        except MergeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        results.append(result)
        print(
            f"{task}: 合并 {result['episode_count']} 个 episode → "
            f"{result['target']}（{result['bytes'] / 2**30:.1f} GiB）",
            flush=True,
        )
    print(json.dumps({"merged": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
