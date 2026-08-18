#!/usr/bin/env python3
"""把官方合并格式的 record_dataset_{task}.h5 拆成逐 episode 文件。

用于 400ep 数据集的 ep0–99 段：按用户口径，这一段不重新生成、不做数值验证，
直接拼接官方数据副本（HuggingFace Yinpei/robomme_data_h5 的本地拷贝）。
拆分是 merge_episode_h5.py 的严格逆操作：episode_N 组逐个 h5py copy 进单独文件，
文件名 `{task}_ep{N}_seed{M}.h5` 与生成链路一致，seed 取自 train metadata。

唯一的防错检查（不属于数值验证）：每个 episode 组的 `setup/seed` 标量必须等于
train metadata 里该 episode 的 seed，防止拼错来源或错位。

用法：
    uv run python scripts/400ep-dataset/split_official_h5.py \
      --official-dir /data/hongzefu/robomme_data_h5 \
      --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask \
      --episodes 100 \
      --output-dir scripts/data-generation-newSeed/outputs/train-ep0-99-official
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import h5py

SCRIPT_DIR = Path(__file__).resolve().parent          # .../scripts/400ep-dataset
CONTRACT_DIR = SCRIPT_DIR.parent / "data-generation"
if str(CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(CONTRACT_DIR))

from validate_generated_dataset_contract import METADATA_ROOT, parse_tasks  # noqa: E402


class SplitError(RuntimeError):
    """来源文件或 metadata 不满足拆分前提。"""


def _metadata_seeds(task: str, episodes: int) -> dict[int, int]:
    path = METADATA_ROOT / f"record_dataset_{task}_metadata.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    seeds = {int(item["episode"]): int(item["seed"]) for item in payload["records"]}
    missing = [episode for episode in range(episodes) if episode not in seeds]
    if missing:
        raise SplitError(f"{task}: train metadata 缺 episode {missing[:5]} 等")
    return {episode: seeds[episode] for episode in range(episodes)}


def split_task(official_dir: Path, output_dir: Path, task: str, episodes: int) -> dict[str, int]:
    source_path = official_dir / f"record_dataset_{task}.h5"
    if not source_path.is_file():
        raise SplitError(f"找不到官方文件：{source_path}")
    seeds = _metadata_seeds(task, episodes)

    hdf5_dir = output_dir / "hdf5_files"
    hdf5_dir.mkdir(parents=True, exist_ok=True)

    written = skipped = 0
    with h5py.File(source_path, "r") as source:
        for episode in range(episodes):
            name = f"episode_{episode}"
            if name not in source:
                raise SplitError(f"{source_path.name}: 缺 {name} 组")
            seed = seeds[episode]
            actual = int(source[name]["setup"]["seed"][()])
            if actual != seed:
                raise SplitError(
                    f"{task}/{name}: 官方 setup/seed={actual} 与 train metadata seed={seed} 不符"
                )
            target = hdf5_dir / f"{task}_ep{episode}_seed{seed}.h5"
            if target.is_file():
                skipped += 1
                continue
            temporary = target.with_name(f".{target.name}.tmp")
            try:
                with h5py.File(temporary, "w") as handle:
                    source.copy(source[name], handle, name=name)
                temporary.replace(target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            written += 1
            if (episode + 1) % 20 == 0:
                print(f"{task}: {episode + 1}/{episodes}", flush=True)
    return {"written": written, "skipped": skipped}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把官方合并 h5 拆成逐 episode 文件")
    parser.add_argument("--official-dir", required=True, help="官方 record_dataset_{task}.h5 所在目录")
    parser.add_argument("--output-dir", required=True, help="输出目录（h5 落在其 hdf5_files/ 下）")
    parser.add_argument("--env", "--environment", default="all", help="all 或逗号分隔的环境名")
    parser.add_argument("--episodes", type=int, default=100, help="从 episode 0 起拆多少条")
    args = parser.parse_args(argv)

    official_dir = Path(args.official_dir)
    output_dir = Path(args.output_dir)
    tasks = parse_tasks(args.env)

    started = time.monotonic()
    try:
        for task in tasks:
            result = split_task(official_dir, output_dir, task, args.episodes)
            print(
                f"{task}: 新写 {result['written']} 条、已存在跳过 {result['skipped']} 条",
                flush=True,
            )
    except SplitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"全部完成，耗时 {time.monotonic() - started:.1f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
