#!/usr/bin/env python3
"""合并 + 密集重编号：把 staging 编号的逐变体 h5 合并成官方格式。

* 读 `variants_manifest.json`（generate_swap_variants.py 的成功总账），按
  (src_episode, variant_idx) 排序，对成功变体连续分配 dense 0..M-1；
* `record_dataset_{Task}.h5` 内组名 `episode_{dense}`（staging 号只活在生成期文件名里，
  这样满足下游「episode 号 0-based 密集连续」的通用假设）；
* `record_dataset_{Task}_metadata.json` 与 env_metadata 同构，seed 字段用
  **variant_seed**（派生 episode ↔ seed 一一对应；注意直接拿它 gym.make 复现不了，
  须 episode_map 里的 env_seed + 注入）；
* `episode_map_{Task}.json`：dense ↔ staging ↔ seed ↔ 交换序列的完整映射（信息无损）。

合并后就地校验：episode 连续、timestep 连续、末帧 is_completed 为真、
swap_gt 组存在。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from variant_worker import _segment_lengths, _sorted_timesteps  # noqa: E402


class MergeError(RuntimeError):
    """合并输入不完整或结构不符。"""


def _load_manifest(input_dir: Path) -> list[dict]:
    path = input_dir / "variants_manifest.json"
    if not path.is_file():
        raise MergeError(f"缺少 {path} —— 先跑 generate_swap_variants.py")
    return json.loads(path.read_text(encoding="utf-8"))["records"]


def merge_task(input_dir: Path, output_dir: Path, task: str, delete_source: bool) -> dict:
    records = [item for item in _load_manifest(input_dir) if item["task"] == task]
    if not records:
        raise MergeError(f"{task}: manifest 里没有任何成功变体")
    records.sort(key=lambda item: (item["src_episode"], item["variant_idx"]))

    target = output_dir / f"record_dataset_{task}.h5"
    temporary = output_dir / f".record_dataset_{task}.h5.tmp"
    episode_map = []
    metadata_records = []
    try:
        with h5py.File(temporary, "w") as merged:
            for dense, record in enumerate(records):
                source = Path(record["h5_path"])
                if not source.is_file():
                    raise MergeError(f"{task}: 源文件缺失 {source}")
                staging_name = f"episode_{record['staging_episode']}"
                with h5py.File(source, "r") as raw:
                    if staging_name not in raw:
                        raise MergeError(f"{source}: 缺少 {staging_name}")
                    raw.copy(raw[staging_name], merged, name=f"episode_{dense}")
                episode_map.append(
                    {
                        "dense_episode": dense,
                        "staging_episode": record["staging_episode"],
                        "src_episode": record["src_episode"],
                        "variant_idx": record["variant_idx"],
                        "variant_seed": record["variant_seed"],
                        "env_seed": record["env_seed"],
                        "difficulty": record["difficulty"],
                        "pairs": record["pairs"],
                        "signature": record["signature"],
                        "net_permutation": record["net_permutation"],
                        "is_original": record["is_original"],
                        "n_timesteps": record["n_timesteps"],
                        "demo_prefix": record["demo_prefix"],
                        "exec_len": record["exec_len"],
                        "min_clearance": record["min_clearance"],
                        "bystander_net_max": record["bystander_net_max"],
                        "bystander_path_max": record["bystander_path_max"],
                        "disturbed_bins": record["disturbed_bins"],
                        "attempt": record.get("attempt", 0),
                        "pickup_hold_step": record.get("pickup_hold_step"),
                    }
                )
                metadata_records.append(
                    {
                        "task": task,
                        "episode": dense,
                        "seed": record["variant_seed"],
                        "difficulty": record["difficulty"],
                    }
                )
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    (output_dir / f"record_dataset_{task}_metadata.json").write_text(
        json.dumps(
            {"env_id": task, "record_count": len(metadata_records), "records": metadata_records},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / f"episode_map_{task}.json").write_text(
        json.dumps(
            {
                "task": task,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "intended_use": "eval-only",
                "note": (
                    "seed 字段是 variant_seed = env_seed*1000 + variant_idx（一一对应、可反解）；"
                    "复现场景须用 env_seed 建环境并按 pairs 注入，直接用 variant_seed 复现不了"
                ),
                "record_count": len(episode_map),
                "records": episode_map,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    verification = verify_merged(target)

    if delete_source:
        for record in records:
            Path(record["h5_path"]).unlink(missing_ok=True)

    return {
        "task": task,
        "episode_count": len(records),
        "target": str(target),
        "bytes": target.stat().st_size,
        "source_deleted": delete_source,
        **verification,
    }


def verify_merged(path: Path) -> dict:
    """episode 密集连续、timestep 连续、末帧 is_completed 真、swap_gt 齐全。"""
    with h5py.File(path, "r") as handle:
        names = [name for name in handle if name.startswith("episode_")]
        indices = sorted(int(name.rsplit("_", 1)[1]) for name in names)
        if indices != list(range(len(indices))):
            raise MergeError(f"{path}: episode 非 0-based 连续（{indices[:5]}…）")
        missing_gt = []
        bad_terminal = []
        for index in indices:
            episode = handle[f"episode_{index}"]
            timesteps = _sorted_timesteps(episode)
            ts_indices = [int(name.rsplit("_", 1)[1]) for name in timesteps]
            if ts_indices != list(range(len(ts_indices))):
                raise MergeError(f"{path}/episode_{index}: timestep 非 0-based 连续")
            last = episode[timesteps[-1]]
            if not bool(np.asarray(last["info"]["is_completed"])):
                bad_terminal.append(index)
            if "swap_gt" not in episode["setup"] or "swap_gt" not in last:
                missing_gt.append(index)
        if bad_terminal:
            raise MergeError(f"{path}: 末帧 is_completed 不为真的 episode：{bad_terminal[:10]}")
        if missing_gt:
            raise MergeError(f"{path}: 缺 swap_gt 标注的 episode：{missing_gt[:10]}")
        return {"episodes_verified": len(indices)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并 swap 变体 h5 并密集重编号")
    parser.add_argument("--input-dir", required=True, help="generate_swap_variants.py 的输出目录")
    parser.add_argument("--output-dir", default=None, help="默认与 --input-dir 相同")
    parser.add_argument("--tasks", default="VideoUnmaskSwap,ButtonUnmaskSwap")
    parser.add_argument("--delete-source", action="store_true", help="合并成功后删除逐变体源 h5")
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for task in (item.strip() for item in args.tasks.split(",") if item.strip()):
        try:
            result = merge_task(input_dir, output_dir, task, args.delete_source)
        except MergeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        results.append(result)
        print(
            f"{task}: 合并 {result['episode_count']} 条变体 → {result['target']}"
            f"（{result['bytes'] / 2**30:.1f} GiB，校验通过）",
            flush=True,
        )
    print(json.dumps({"merged": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
