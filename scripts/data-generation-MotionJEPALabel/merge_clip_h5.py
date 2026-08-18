#!/usr/bin/env python3
"""把逐条 clip h5 合并成官方格式的 `record_dataset_{Task}.h5`，episode 重编号为密集 0..M-1。

为什么要重编号：生成期用 staging_episode = src_episode*1000 + variant_idx 做文件名，
但下游（MotionJEPA `build_data_raw_from_h5`）断言 episode 必须 0-based 密集连续。
重编号是信息无损的 —— `episode_map_{Task}.json` 记下 dense ↔ staging ↔ seed ↔ 槽位序列
的完整映射，`h5` 内 `setup/swap_gt` 也自带全部字段。

产物：
* `record_dataset_{Task}.h5`（`raw.copy` 整组拷贝，逐帧 swap_gt 自动带走）
* `record_dataset_{Task}_metadata.json`（官方同构；seed 字段 = variant_seed）
* `episode_map_{Task}.json`（完整映射 + 事件标签 + 质量指标）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from clip_plan import CLIP_LEN, EVAL_TASKS  # noqa: E402
from clip_worker import CLIP_IS_DEMO, segment_lengths, sorted_timesteps  # noqa: E402


class MergeError(RuntimeError):
    pass


def _load_manifest(input_dir: Path) -> list[dict]:
    path = input_dir / "clips_manifest.json"
    if not path.is_file():
        raise MergeError(f"缺少 {path} —— 先跑 generate_swap_clips.py")
    return json.loads(path.read_text(encoding="utf-8"))["records"]


def verify_merged(path: Path, task: str) -> dict:
    """合并后结构校验：episode 密集连续、每条恰 CLIP_LEN 帧、scope 段 == 整段 clip。"""
    problems: list[str] = []
    with h5py.File(path, "r") as handle:
        names = [name for name in handle if name.startswith("episode_")]
        indices = sorted(int(name.rsplit("_", 1)[1]) for name in names)
        if indices != list(range(len(indices))):
            problems.append(f"episode 编号不密集连续：{indices[:5]}…")
        for index in indices:
            group = handle[f"episode_{index}"]
            timesteps = sorted_timesteps(group)
            numbers = [int(name.rsplit("_", 1)[1]) for name in timesteps]
            if numbers != list(range(len(numbers))):
                problems.append(f"episode_{index}: timestep 不连续")
            if len(timesteps) != CLIP_LEN:
                problems.append(f"episode_{index}: {len(timesteps)} 帧 ≠ {CLIP_LEN}")
            total, demo_prefix, exec_len = segment_lengths(group)
            scope = demo_prefix if CLIP_IS_DEMO[task] else exec_len
            if scope != CLIP_LEN:
                problems.append(
                    f"episode_{index}: scope 段 {scope} 帧 ≠ 整段 clip {CLIP_LEN}"
                )
            if "swap_gt" not in group["setup"]:
                problems.append(f"episode_{index}: setup 缺 swap_gt")
            if "swap_gt" not in group[timesteps[0]]:
                problems.append(f"episode_{index}: timestep_0 缺 swap_gt")
    return {"episode_count": len(indices), "structure_problems": problems}


def merge_task(input_dir: Path, output_dir: Path, task: str, delete_source: bool) -> dict:
    records = [item for item in _load_manifest(input_dir) if item["task"] == task]
    if not records:
        raise MergeError(f"{task}: manifest 里没有任何成功 clip")
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
                event_pair = tuple(sorted(record["event_slots"]))
                geometry = record.get("geometry") or {}
                pair_info = (geometry.get("pairs") or {}).get(f"{event_pair[0]}{event_pair[1]}", {})
                episode_map.append(
                    {
                        "dense_episode": dense,
                        "staging_episode": record["staging_episode"],
                        "src_episode": record["src_episode"],
                        "variant_idx": record["variant_idx"],
                        "variant_seed": record["variant_seed"],
                        "env_seed": record["env_seed"],
                        "difficulty": record["difficulty"],
                        # ★ 事件标签
                        "event_slots": record["event_slots"],
                        "topo_class": record["topo_class"],
                        "pair_distance": pair_info.get("distance"),
                        "pair_azimuth": pair_info.get("azimuth"),
                        "pair_azimuth_local": pair_info.get("azimuth_local"),
                        "slot_xy": geometry.get("slot_xy"),
                        "reference_axis_deg": geometry.get("reference_axis_deg"),
                        # 完整交换序列（槽位口径为主，bin 口径供复现注入）
                        "slot_pairs": record["slot_pairs"],
                        "bin_pairs": record["bin_pairs"],
                        "signature": record["signature"],
                        "net_permutation": record["net_permutation"],
                        "is_original": record["is_original"],
                        "n_timesteps": record["n_timesteps"],
                        "demo_prefix": record["demo_prefix"],
                        "exec_len": record["exec_len"],
                        # 质量指标与协变量
                        "min_clearance": record["min_clearance"],
                        "bystander_net_max": record["bystander_net_max"],
                        "bystander_path_max": record["bystander_path_max"],
                        "disturbed_bins": record["disturbed_bins"],
                        "contacts": record.get("contacts"),
                        "buttons": record.get("buttons"),
                        "attempt": record.get("attempt", 0),
                        "last_env_step": record.get("last_env_step"),
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
                "clip_len": CLIP_LEN,
                "note": (
                    "每条 episode 是一段 110 帧 clip（env step [34,144)）：第一次 swap 窗口"
                    "（clip 帧 30-79）前后各 30 帧。事件标签是 event_slots/topo_class；"
                    "seed 字段 = variant_seed = env_seed*1000 + variant_idx（可反解）；"
                    "复现须用 env_seed 建环境并按 bin_pairs 注入，直接用 variant_seed 复现不了"
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

    verification = verify_merged(target, task)
    if delete_source:
        for record in records:
            Path(record["h5_path"]).unlink(missing_ok=True)

    return {
        "task": task,
        "target": str(target),
        "bytes": target.stat().st_size,
        "source_deleted": delete_source,
        **verification,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并 clip h5 并重编号为密集 episode")
    parser.add_argument("--input-dir", required=True, help="generate_swap_clips.py 的输出目录")
    parser.add_argument("--output-dir", default=None, help="默认与 --input-dir 相同")
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    parser.add_argument("--delete-source", action="store_true", help="合并成功后删除逐条 clip h5")
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    problems = 0
    for task in (item.strip() for item in args.tasks.split(",") if item.strip()):
        try:
            result = merge_task(input_dir, output_dir, task, args.delete_source)
        except MergeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            problems += 1
            continue
        size_gib = result["bytes"] / (1024 ** 3)
        print(
            f"{task}: {result['episode_count']} 条 → {result['target']}（{size_gib:.2f} GiB）"
            + ("，源已删除" if result["source_deleted"] else "")
        )
        for line in result["structure_problems"]:
            print(f"  结构问题：{line}", file=sys.stderr)
            problems += 1
    if problems:
        print(f"ERROR: 共 {problems} 处问题", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
