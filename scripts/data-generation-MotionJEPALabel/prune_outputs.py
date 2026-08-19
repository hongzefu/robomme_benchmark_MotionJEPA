#!/usr/bin/env python3
"""清理链路的过程产物，把 outputs 收敛成「三类产物 + 两份凭据」。

用户 2026-08-19 拍板的目标形态：

```
outputs/event1/
  record_dataset_{Task}.h5              ← 三类之一
  record_dataset_{Task}_metadata.json   ← 随 h5（官方格式配套）
  videos/                               ← 三类之一
  diagrams/                             ← 三类之一
  episode_map_{Task}.json               ← 映射 + 全部派生标签（唯一标签载体）
  verification_report.md                ← 验收唯一产物
outputs/phase0/
  original_index.json                   ← 只留它
```

⚠ **删除前必须确认「可再次跑生成」**（`--check-only` 单独跑这一步）：

* `outputs/phase0/original_index.json` 是全链路里**唯一不可静态重算**的东西 —— 第二次
  及以后的 swap 换的是哪一对，只能实跑读回。它必须存在且字段完整，phase0 的其余产物
  （2.1 GiB h5、录像、trace）才可以删；
* event1 的过程产物（clips/、hdf5_files/、traces/、clip_results.jsonl、
  clips_manifest.json、run_*.json）只在**全链路重跑成功、验收退出码 0** 之后才删 ——
  合并阶段已 `--delete-source`，这些是断点续跑与排查用的残留。

默认 dry-run 只列不删，`--yes` 才真删。不在清单里的条目一律**报告但不动**。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Sequence

# event1：跑完即可删的过程产物（合并已 --delete-source，这些是残留与断点续跑记录）
GEN_PRUNE = (
    "clips",                # 逐条 clip h5 的落点（merge --delete-source 后恒为空）
    "hdf5_files",           # 截断 rollout 的 raw h5（裁剪后即删，恒为空）
    "traces",               # clip 区间位姿 npz（质量指标已进 episode_map）
    "clip_results.jsonl",   # 逐 attempt 记录，断点续跑用
    "clips_manifest.json",  # 成功 clip 总账，merge 的输入
    "run_parameters.json",
    "run_summary.json",
    "clip_events.json",        # 2026-08-19 起不再产出；老目录里可能还有
    "swap_labels_clip.json",
    "swap_events_clip.json",
    "verification_report.json",
)
GEN_KEEP = ("videos", "diagrams", "record_dataset_", "episode_map_", "verification_report.md")

# phase0：索引产出后即可删（重跑 probe_original.py 可完整再生，实测逐位相同）
PHASE0_PRUNE = ("hdf5_files", "videos", "traces", "episode_results.jsonl")
PHASE0_KEEP = ("original_index.json",)


def check_regenerable(phase0_dir: Path) -> list[str]:
    """确认 phase0 索引完整 —— 它在，链路才能重跑，其余产物才敢删。"""
    problems: list[str] = []
    index_path = phase0_dir / "original_index.json"
    if not index_path.is_file():
        return [f"{index_path} 不存在 —— 先跑 probe_original.py，否则第二次 swap 换谁将无从得知"]
    records = json.loads(index_path.read_text(encoding="utf-8")).get("records") or []
    if not records:
        problems.append(f"{index_path} 里没有任何记录")
    for record in records:
        tag = f"{record.get('task')}/ep{record.get('episode')}"
        for field in ("original_slot_pairs", "original_bin_pairs", "original_idx1", "geometry"):
            if not record.get(field):
                problems.append(f"{tag}: 索引缺 {field}")
        if not (record.get("geometry") or {}).get("slot_xy"):
            problems.append(f"{tag}: 索引缺 geometry.slot_xy")
    return problems


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def prune(directory: Path, prune_names: Sequence[str], keep_prefixes: Sequence[str],
          apply: bool) -> int:
    if not directory.is_dir():
        print(f"跳过 {directory}（不存在）")
        return 0
    freed = 0
    for name in sorted(prune_names):
        path = directory / name
        if not path.exists():
            continue
        size = _size(path)
        freed += size
        print(f"  {'删除' if apply else '待删'} {path.relative_to(directory.parent)}"
              f"（{size / 1024 ** 2:.1f} MiB）")
        if apply:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    unknown = [
        item.name for item in sorted(directory.iterdir())
        if item.name not in prune_names
        and not any(item.name.startswith(prefix) for prefix in keep_prefixes)
    ]
    if unknown:
        print(f"  ⚠ 不在清单里、未处理：{'、'.join(unknown)}")
    return freed


def main(argv: Sequence[str] | None = None) -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="把 outputs 收敛成三类产物 + 两份凭据")
    parser.add_argument("--gen-dir", default=str(script_dir / "outputs" / "event1"))
    parser.add_argument("--phase0-dir", default=str(script_dir / "outputs" / "phase0"))
    parser.add_argument("--check-only", action="store_true", help="只做「可再次跑生成」确认")
    parser.add_argument("--yes", action="store_true", help="真的删除（默认只列不删）")
    args = parser.parse_args(argv)

    phase0_dir = Path(args.phase0_dir).resolve()
    problems = check_regenerable(phase0_dir)
    if problems:
        print("「可再次跑生成」确认未通过：", file=sys.stderr)
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"「可再次跑生成」确认通过：{phase0_dir / 'original_index.json'} 字段完整")
    if args.check_only:
        return 0

    freed = 0
    print(f"\n生成目录 {args.gen_dir}：")
    freed += prune(Path(args.gen_dir).resolve(), GEN_PRUNE, GEN_KEEP, args.yes)
    print(f"\nPhase 0 目录 {phase0_dir}：")
    freed += prune(phase0_dir, PHASE0_PRUNE, PHASE0_KEEP, args.yes)
    verb = "已释放" if args.yes else "可释放"
    print(f"\n{verb} {freed / 1024 ** 3:.2f} GiB" + ("" if args.yes else "；加 --yes 真的删除"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
