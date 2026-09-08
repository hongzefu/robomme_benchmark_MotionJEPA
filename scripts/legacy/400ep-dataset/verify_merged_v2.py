#!/usr/bin/env python3
"""校验合并后的 v2 数据集是否满足 dataset-build 的输入契约。

契约来源：/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA/scripts/dataset-build/
build_data_raw_from_h5.py（probe_schema 与 split_episode 的断言），在数据出厂前全量
预演一遍，避免到 greatlakes 上跑一半才 fail-loud。逐项：

1. 结构：每个 record_dataset_{task}.h5 顶层组恰为 episode_0..N-1（0-based 连续）；
   每个 episode 的 timestep_* 同样 0-based 连续。
2. 字段：每个 episode 的 timestep_0 有 obs/front_rgb（(256,256,3) uint8）、
   info/is_video_demo、info/is_completed。
3. 语义（对齐 split_episode）：is_video_demo=True 必须构成严格前缀；
   exec 段（前缀之后）必须存在 is_completed=True，且 demo_prefix + 相对完成位 + 2 <= T。
4. 溯源：episode_N 的 setup/seed 必须等于 train metadata 里该 episode 的 seed。

用法：
    uv run python scripts/legacy/400ep-dataset/verify_merged_v2.py \
      --h5-dir /data/hongzefu/robomme_data_h5_v2_4env400ep \
      --metadata-dir src/robomme/env_metadata/train \
      --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Sequence

import h5py

_NUM = re.compile(r"^(episode|timestep)_(\d+)$")

EXEC_TRUNCATE_TAIL = 2  # 与 build_data_raw_from_h5.py 的常量一致


def _indices(keys: Sequence[str], prefix: str) -> list[int]:
    out = []
    for key in keys:
        match = _NUM.match(key)
        if match and match.group(1) == prefix:
            out.append(int(match.group(2)))
    return sorted(out)


def verify_task(h5_path: Path, metadata_path: Path) -> list[str]:
    """返回问题清单；空列表即通过。"""
    problems: list[str] = []
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    seeds = {int(r["episode"]): int(r["seed"]) for r in payload["records"]}

    with h5py.File(h5_path, "r") as handle:
        episodes = _indices(list(handle.keys()), "episode")
        if episodes != list(range(len(episodes))):
            return [f"episode 组不连续：共 {len(episodes)} 个，前几个 {episodes[:5]}"]
        if len(episodes) != len(seeds):
            problems.append(f"episode 数 {len(episodes)} 与 metadata {len(seeds)} 不符")

        for episode in episodes:
            group = handle[f"episode_{episode}"]
            tag = f"{h5_path.stem}/episode_{episode}"

            actual_seed = int(group["setup"]["seed"][()])
            if actual_seed != seeds.get(episode):
                problems.append(f"{tag}: setup/seed={actual_seed} != metadata {seeds.get(episode)}")

            steps = _indices(list(group.keys()), "timestep")
            total = len(steps)
            if steps != list(range(total)) or total == 0:
                problems.append(f"{tag}: timestep 不连续或为空（共 {total}）")
                continue

            first = group["timestep_0"]
            rgb = first["obs"]["front_rgb"]
            if tuple(rgb.shape) != (256, 256, 3) or str(rgb.dtype) != "uint8":
                problems.append(f"{tag}: front_rgb shape/dtype 异常 {rgb.shape}/{rgb.dtype}")
            for field in ("is_video_demo", "is_completed"):
                if field not in first["info"]:
                    problems.append(f"{tag}: 缺 info/{field}")

            demo = [bool(group[f"timestep_{k}"]["info"]["is_video_demo"][()]) for k in range(total)]
            completed = [bool(group[f"timestep_{k}"]["info"]["is_completed"][()]) for k in range(total)]

            prefix = 0
            while prefix < total and demo[prefix]:
                prefix += 1
            if any(demo[prefix:]):
                problems.append(f"{tag}: is_video_demo 在前缀之后再次出现（非严格前缀）")
                continue
            exec_completed = [i for i, flag in enumerate(completed[prefix:]) if flag]
            if not exec_completed:
                problems.append(f"{tag}: exec 段没有任何 is_completed=True")
                continue
            if prefix + exec_completed[0] + EXEC_TRUNCATE_TAIL > total:
                problems.append(
                    f"{tag}: 完成帧后余量不足（prefix={prefix} first_completed={exec_completed[0]} T={total}）"
                )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 v2 合并数据集是否满足 dataset-build 输入契约")
    parser.add_argument("--h5-dir", required=True)
    parser.add_argument("--metadata-dir", required=True)
    parser.add_argument("--env", default="ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap")
    args = parser.parse_args(argv)

    h5_dir = Path(args.h5_dir)
    metadata_dir = Path(args.metadata_dir)
    tasks = [item.strip() for item in args.env.split(",") if item.strip()]

    failed = False
    for task in tasks:
        started = time.monotonic()
        problems = verify_task(
            h5_dir / f"record_dataset_{task}.h5",
            metadata_dir / f"record_dataset_{task}_metadata.json",
        )
        elapsed = time.monotonic() - started
        if problems:
            failed = True
            print(f"{task}: ✗ {len(problems)} 个问题（{elapsed:.1f}s）", flush=True)
            for item in problems[:20]:
                print(f"  - {item}", flush=True)
        else:
            print(f"{task}: 全部通过（{elapsed:.1f}s）", flush=True)
    print("结论：" + ("存在问题，见上" if failed else "4 个文件全部满足 dataset-build 输入契约"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
