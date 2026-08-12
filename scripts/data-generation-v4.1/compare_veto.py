#!/usr/bin/env python3
"""三栏对比出图入口：veto | noveto | ground truth，全部取 train split 的 episode_0。

对每个任务的 episode_0（train seed，未参与 v4.1 标定——标定集是 val split ep0-9）
逐帧跑三种口径：

- **默认口径（veto）**：归一化似然 argmax + 混合支撑否决 → 四条形态学规则；
- **对照口径（noveto）**：纯归一化似然 argmax（`veto_shared=False`）→ 同样四条规则；
- **ground truth**：GT segmentation 的机械臂像素直接作 mask（理想上界，误差图应全白）。

每个任务出一张三栏大图（每栏 8 帧 ×「原图 | 红遮罩 | 误差图」三联），同时把三口径的
全帧指标写进 metrics.json。GT 只出现在评分与 GT 栏，不参与前两栏的产出。

用法：

    uv run --no-sync python scripts/data-generation-v4.1/compare_veto.py \\
      --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \\
      --model scripts/data-generation-v4.1/outputs/color_model.npz \\
      --out scripts/data-generation-v4.1/outputs/compare_veto
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arm_mask_v4 import MaskParams, apply_red_mask, arm_masks_for_episode  # noqa: E402
from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_OBJECT,
    ColorModel,
    class_ids_from_setup,
    iter_episode_frames,
    labels_from_segmentation,
)
from fit_color_model import resolve_h5  # noqa: E402
from render_outputs import _error_image, _grid  # noqa: E402

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
TITLE_H = 56  # 顶部任务名条
HEAD_H = 44  # 口径标题条
COL_H = 34  # 三联列标签条
LEGEND_H = 46  # 底部图例条
GAP = 16  # 栏与栏之间的竖向留白
PAD = 12  # 四周留白

BG = (24, 24, 28)
FG = (240, 240, 240)

# 三栏的（标题, 颜色）；顺序即出图顺序
COLUMNS = (
    ("默认口径：混合支撑否决", (120, 235, 140)),
    ("对照口径：纯似然 argmax", (250, 170, 90)),
    ("ground truth", (140, 190, 255)),
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def _center_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = FG,
) -> None:
    x0, y0, x1, y1 = box
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((x0 + x1 - (right - left)) / 2 - left, (y0 + y1 - (bottom - top)) / 2 - top),
        text,
        font=font,
        fill=fill,
    )


def _mask_stats(masks: Sequence[np.ndarray], truth: Sequence[np.ndarray]) -> dict[str, Any]:
    """全帧口径的像素级统计（同 render_outputs 的核心三率）。"""
    pred = sum(int(mask.sum()) for mask in masks)
    true_arm = sum(int((mask & (gt == CLASS_ARM)).sum()) for mask, gt in zip(masks, truth))
    gt_arm = sum(int((gt == CLASS_ARM).sum()) for gt in truth)
    false_object = sum(
        int((mask & (gt == CLASS_OBJECT)).sum()) for mask, gt in zip(masks, truth)
    )
    return {
        "pred_pixels": pred,
        "gt_arm_pixels": gt_arm,
        "true_arm_pixels": true_arm,
        "false_object_pixels": false_object,
        "机械臂召回": round(true_arm / gt_arm, 6) if gt_arm else None,
        "标定精确率": round(true_arm / pred, 6) if pred else None,
    }


def _panel_grid(
    frames: Sequence[tuple[str, np.ndarray, np.ndarray, bool]],
    masks: Sequence[np.ndarray],
    truth: Sequence[np.ndarray],
    picks: np.ndarray,
) -> np.ndarray:
    rows = []
    for index in picks:
        rgb = frames[index][1]
        rows.append(
            [rgb, apply_red_mask(rgb, masks[index]), _error_image(masks[index], truth[index])]
        )
    return _grid(rows)


def process_task(
    h5_path: str,
    episode_name: str,
    model_path: str,
    out_dir: str,
    params: MaskParams,
    preview_rows: int,
) -> dict[str, Any]:
    """一个任务出一张三栏图 + 三口径全帧指标。"""
    model = ColorModel.load(model_path)
    task = Path(h5_path).stem.replace("record_dataset_", "")

    with h5py.File(h5_path, "r") as handle:
        episode = handle[episode_name]
        class_ids = class_ids_from_setup(episode["setup"])
        frames = list(iter_episode_frames(episode))
    truth = [labels_from_segmentation(seg, class_ids) for _, _, seg, _ in frames]
    demo_flags = [flag for _, _, _, flag in frames]

    variants: dict[str, list[np.ndarray]] = {}
    for key, veto in (("veto", True), ("noveto", False)):
        predicted = [model.classify(rgb, veto) for _, rgb, _, _ in frames]
        variants[key] = arm_masks_for_episode(predicted, demo_flags, params)
    variants["ground_truth"] = [gt == CLASS_ARM for gt in truth]

    stats = {
        "task": task,
        "episode": episode_name,
        "frames": len(frames),
        **{key: _mask_stats(masks, truth) for key, masks in variants.items()},
    }

    picks = np.unique(np.linspace(0, len(frames) - 1, preview_rows).round().astype(int))
    grids = [
        _panel_grid(frames, variants[key], truth, picks)
        for key in ("veto", "noveto", "ground_truth")
    ]
    height, width = grids[0].shape[:2]
    cell = width // 3

    canvas_w = PAD * 2 + width * 3 + GAP * 2
    canvas_h = PAD * 2 + TITLE_H + HEAD_H + COL_H + height + LEGEND_H
    canvas = Image.new("RGB", (canvas_w, canvas_h), BG)
    draw = ImageDraw.Draw(canvas)

    y = PAD
    _center_text(draw, f"{task}  ·  {episode_name}", (0, y, canvas_w, y + TITLE_H), _font(30))
    y += TITLE_H

    xs = [PAD + i * (width + GAP) for i in range(3)]
    for x, (head, color) in zip(xs, COLUMNS):
        _center_text(draw, head, (x, y, x + width, y + HEAD_H), _font(22), color)
    y += HEAD_H

    for x in xs:
        for i, name in enumerate(("原图", "红遮罩", "误差图")):
            _center_text(
                draw,
                name,
                (x + i * cell, y, x + (i + 1) * cell, y + COL_H),
                _font(20),
                (170, 170, 178),
            )
    y += COL_H

    for x, grid in zip(xs, grids):
        canvas.paste(Image.fromarray(grid), (x, y))
    # 栏间画竖分隔线，避免相邻误差图连成一片分不清边界
    for x in xs[1:]:
        draw.line([(x - GAP // 2, y), (x - GAP // 2, y + height)], fill=(90, 90, 96), width=2)
    y += height

    legend = [
        ((255, 255, 255), "标对的机械臂"),
        ((255, 0, 0), "误标到物体（核心红线）"),
        ((255, 255, 0), "误标到背景"),
        ((0, 0, 255), "漏标的机械臂"),
    ]
    font = _font(19)
    widths = [draw.textlength(text, font=font) + 34 for _, text in legend]
    x = (canvas_w - sum(widths)) / 2
    for (color, text), item_width in zip(legend, widths):
        draw.rectangle([x, y + 15, x + 18, y + 33], fill=color, outline=(120, 120, 126))
        draw.text((x + 26, y + 13), text, font=font, fill=FG)
        x += item_width

    out = Path(out_dir) / f"{task}_veto_compare.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--h5",
        nargs="+",
        default=["artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5"],
        help="h5 路径或 glob（默认 train split 的 v4seg 数据集）",
    )
    parser.add_argument(
        "--model",
        default=str(SCRIPT_DIR / "outputs" / "color_model.npz"),
        help="fit_color_model.py 产出的颜色表",
    )
    parser.add_argument(
        "--episode", type=int, default=0, help="出图用的 episode（默认 train ep0）"
    )
    parser.add_argument(
        "--out", default=str(SCRIPT_DIR / "outputs" / "compare_veto"), help="产物目录"
    )
    parser.add_argument("--preview-rows", type=int, default=8, help="每栏抽帧行数")
    parser.add_argument("--workers", type=int, default=8, help="并行进程数")
    parser.add_argument("--open-iterations", type=int, default=1)
    parser.add_argument("--temporal-window", type=int, default=3)
    parser.add_argument("--final-erode", type=int, default=1)
    args = parser.parse_args(argv)

    paths = resolve_h5(args.h5)
    params = MaskParams(
        open_iterations=args.open_iterations,
        temporal_window=args.temporal_window,
        final_erode=args.final_erode,
    )
    episode_name = f"episode_{args.episode}"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"三栏对比：{len(paths)} 个任务 × {episode_name}，并行 {args.workers}")

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_task,
                str(path),
                episode_name,
                args.model,
                str(out_dir),
                params,
                args.preview_rows,
            ): path
            for path in paths
        }
        for future in as_completed(futures):
            records.append(future.result())
    elapsed = time.perf_counter() - started

    records.sort(key=lambda item: item["task"])
    payload = {
        "参数": {
            "颜色表": args.model,
            "episode": episode_name,
            "开运算次数": params.open_iterations,
            "时间窗": params.temporal_window,
            "最终腐蚀次数": params.final_erode,
        },
        "耗时秒": round(elapsed, 1),
        "逐任务": records,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for record in records:
        print(
            f"{record['task']}: veto 误标物体 {record['veto']['false_object_pixels']} px"
            f" / 召回 {record['veto']['机械臂召回']}；"
            f"noveto 误标物体 {record['noveto']['false_object_pixels']} px"
            f" / 召回 {record['noveto']['机械臂召回']}"
        )
    print(f"共 {len(records)} 张 → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
