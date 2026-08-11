#!/usr/bin/env python3
"""拟合入口：在拟合集 episode 上统计三类像素分布，落成一张颜色表。

这是整条 v4 链路里**唯一**读 ground truth segmentation 的地方（验证入口另算，
那是拿 GT 当尺子量结果，不参与产出）。

用法：

    uv run --no-sync python scripts/data-generation-v4/fit_color_model.py \\
      --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \\
      --episodes 0-9 --out scripts/data-generation-v4/outputs/color_model.npz

`--episodes` 只接受拟合集，验证集必须留出来不参与拟合，否则后面的数字没有说服力。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from color_model import CLASS_NAMES, fit_color_model  # noqa: E402


def parse_episodes(value: str) -> list[int]:
    """解析 `0-9` / `0,1,2` / `0-4,7` 这类 episode 选择串。"""
    selected: set[int] = set()
    for piece in value.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if "-" in piece:
            low, high = piece.split("-", 1)
            selected.update(range(int(low), int(high) + 1))
        else:
            selected.add(int(piece))
    if not selected:
        raise ValueError(f"没解析出任何 episode：{value}")
    return sorted(selected)


def resolve_h5(patterns: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        if not matched:
            raise FileNotFoundError(f"没有匹配到任何 h5：{pattern}")
        paths.extend(Path(item) for item in matched)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h5", nargs="+", required=True, help="h5 路径或 glob")
    parser.add_argument(
        "--episodes", default="0-9", help="拟合集 episode，如 0-9（默认前 10 个）"
    )
    parser.add_argument(
        "--out",
        default=str(SCRIPT_DIR / "outputs" / "color_model.npz"),
        help="颜色表落盘路径",
    )
    args = parser.parse_args(argv)

    paths = resolve_h5(args.h5)
    episodes = parse_episodes(args.episodes)
    print(f"拟合集：{len(paths)} 个 h5 × episode {episodes[0]}..{episodes[-1]}")

    started = time.perf_counter()
    model = fit_color_model(paths, episodes, verbose=True)
    elapsed = time.perf_counter() - started

    target = model.save(args.out)
    totals = model.class_pixel_totals
    per_class_colors = [int((model.counts[:, index] > 0).sum()) for index in range(3)]
    # 一种颜色同时出现在两类以上，就是「外观上不可分」的那部分，先量出来
    ambiguous = int((np.count_nonzero(model.counts, axis=1) > 1).sum())
    ambiguous_pixels = int(
        model.counts[np.count_nonzero(model.counts, axis=1) > 1].sum()
    )

    summary = {
        "颜色表落点": str(target),
        "拟合耗时秒": round(elapsed, 1),
        "唯一颜色数": int(model.colors.size),
        "各类像素数": {name: int(totals[i]) for i, name in enumerate(CLASS_NAMES)},
        "各类颜色数": {name: per_class_colors[i] for i, name in enumerate(CLASS_NAMES)},
        "跨类共享的颜色数": ambiguous,
        "落在共享色上的像素数": ambiguous_pixels,
        "共享色像素占比": round(ambiguous_pixels / max(1, int(totals.sum())), 6),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (target.parent / "color_model_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
