#!/usr/bin/env python3
"""拟合入口：在标定集 episode 上统计两分布 + 臂的像素颜色表（= 像素表）。

这是整条链路里**唯一**读 ground truth segmentation 来产出模型的地方（实测入口另算，
那是拿 GT 当尺子量结果，不参与产出）。三列 =（纯背景，背景∪物体混合，机械臂），
背景像素重叠计入前两列，物体在混合列中的占比（类先验）对模型不可见。

⚠ **标定集必须与实测集零 seed 重叠**。现行口径：像素表在 **val split ep0-9** 上拟合，
实测走 **train split ep0-9**（官方同 seed 重放），两者零重叠，故实测数字是干净的泛化
数字。拿实测集自己拟合会让一切指标偏乐观、不可当泛化性能读。

用法（在仓库根）：

    uv run --no-sync python scripts/data-generation/gt-data/fit_color_model.py \\
      --h5 'artifacts/generated/<标定集目录>/record_dataset_*.h5' \\
      --episodes 0-9 \\
      --out scripts/data-generation/gt-data/outputs/color_model.npz
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

from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_MIX,
    CLASS_NAMES,
    fit_color_model,
)


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
    # 重叠计数下「出现在两列以上」不再是共享的判据（背景像素天然同时进列 0 与列 1），
    # 有判读价值的是臂列与另外两列的支撑交叠。⚠ 这几个量不是附带统计——判别规则本身
    # 就是纯支撑判据（判臂 = 臂列见过且混合列没见过），所以「臂独有颜色数」逐字等于
    # 最终的判臂色数，「臂与混合共享的颜色数」逐字等于颜色阶段漏标代价的来源色数。
    # 键名里的「否决」是历史措辞（判臂被混合列支撑否决），含义即上面的纯支撑判据。
    arm_support = model.counts[:, CLASS_ARM] > 0
    mix_support = model.counts[:, CLASS_MIX] > 0
    bg_support = model.counts[:, CLASS_BACKGROUND] > 0
    arm_total = int(model.counts[:, CLASS_ARM].sum())
    vetoed = arm_support & mix_support
    # 总像素数：混合列每个背景/物体像素恰记一次，臂列每个臂像素恰记一次，相加即全量
    total_pixels = int(model.counts[:, CLASS_MIX].sum()) + arm_total

    summary = {
        "颜色表落点": str(target),
        "拟合耗时秒": round(elapsed, 1),
        "唯一颜色数": int(model.colors.size),
        "各列像素数": {name: int(totals[i]) for i, name in enumerate(CLASS_NAMES)},
        "各列颜色数": {name: per_class_colors[i] for i, name in enumerate(CLASS_NAMES)},
        "臂与混合共享的颜色数": int(vetoed.sum()),
        "臂与纯背景共享的颜色数": int((arm_support & bg_support).sum()),
        "被混合支撑否决带走的臂像素占比": round(
            int(model.counts[vetoed, CLASS_ARM].sum()) / max(1, arm_total), 6
        ),
        "臂独有颜色数": int((arm_support & ~mix_support).sum()),
        "总像素数": total_pixels,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    json_dir = target.parent / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "color_model_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
