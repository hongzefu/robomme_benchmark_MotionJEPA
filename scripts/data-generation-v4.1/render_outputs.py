#!/usr/bin/env python3
"""推理 + 验证 + 出图入口。

对验证集 episode 逐帧跑「颜色表分类（v4.1 两分布 + 臂口径）→ 四条形态学规则」得到
机械臂 mask，涂成纯红，再拿 ground truth segmentation 当尺子把结果量化。
**GT 只出现在评分环节，不参与产出**。

用法：

    uv run --no-sync python scripts/data-generation-v4.1/render_outputs.py \\
      --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \\
      --model scripts/data-generation-v4.1/outputs/color_model.npz \\
      --episodes 10-19 --out scripts/data-generation-v4.1/outputs/holdout

产物：

- `<Task>_ep<k>_preview.png`：均匀抽帧的三联网格——原图 | 红遮罩 | 误差图。
  误差图配色：**白 = 标对的机械臂、红 = 误标到物体（必须为零）、黄 = 误标到背景、
  蓝 = 漏标的机械臂**（漏标按口径是可接受代价，所以给冷色，一眼与红区分）。
- `metrics.json`：逐任务 + 全局的像素级统计，全帧口径（不是抽样帧）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

import cv2
import h5py
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arm_mask_v4 import MaskParams, apply_red_mask, arm_masks_for_episode  # noqa: E402
from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_OBJECT,
    CLASS_UNKNOWN,
    ColorModel,
    class_ids_from_setup,
    episode_names,
    iter_episode_frames,
    labels_from_segmentation,
    uncovered_mask,
)
from fit_color_model import parse_episodes, resolve_h5  # noqa: E402


# 误差图配色（BGR 顺序留给 cv2 写文件时再转，这里统一按 RGB 存）
COLOR_TRUE_ARM = (255, 255, 255)  # 标对的机械臂
COLOR_FALSE_OBJECT = (255, 0, 0)  # 误标到物体：核心红线
COLOR_FALSE_BACKGROUND = (255, 255, 0)  # 误标到背景：可容忍的多删
COLOR_MISSED_ARM = (0, 0, 255)  # 漏标的机械臂：按口径可接受


def _error_image(mask: np.ndarray, gt: np.ndarray) -> np.ndarray:
    image = np.zeros((*mask.shape, 3), np.uint8)
    image[mask & (gt == CLASS_ARM)] = COLOR_TRUE_ARM
    image[mask & (gt == CLASS_OBJECT)] = COLOR_FALSE_OBJECT
    image[mask & (gt == CLASS_BACKGROUND)] = COLOR_FALSE_BACKGROUND
    image[~mask & (gt == CLASS_ARM)] = COLOR_MISSED_ARM
    return image


def _grid(rows: Sequence[Sequence[np.ndarray]]) -> np.ndarray:
    return np.concatenate([np.concatenate(row, axis=1) for row in rows], axis=0)


def _write_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image[:, :, ::-1]):
        raise RuntimeError(f"写图失败：{path}")


def process_episode(
    h5_path: str,
    episode_name: str,
    model_path: str,
    out_dir: str,
    params: MaskParams,
    preview_rows: int,
    veto_shared: bool = True,
) -> dict[str, Any]:
    """跑完一个 episode：全帧算指标，抽帧出 preview。"""
    model = ColorModel.load(model_path)
    task = Path(h5_path).stem.replace("record_dataset_", "")

    with h5py.File(h5_path, "r") as handle:
        episode = handle[episode_name]
        class_ids = class_ids_from_setup(episode["setup"])
        frames = list(iter_episode_frames(episode))
        predicted = [model.classify(rgb, veto_shared) for _, rgb, _, _ in frames]
        truth = [
            labels_from_segmentation(segmentation, class_ids)
            for _, _, segmentation, _ in frames
        ]
        # setup 快照没覆盖的 seg id（运行中新建的目标 / 路径标记物）已经并进「物体」，
        # 这里把它们单独数出来，兜底口径不许静默
        uncovered = [
            uncovered_mask(segmentation, class_ids) for _, _, segmentation, _ in frames
        ]
        demo_flags = [flag for _, _, _, flag in frames]
        masks = arm_masks_for_episode(predicted, demo_flags, params)

        stats = {
            "task": task,
            "episode": episode_name,
            "frames": len(frames),
            "pred_pixels": 0,
            "gt_arm_pixels": 0,
            "gt_object_pixels": 0,
            "gt_background_pixels": 0,
            "true_arm_pixels": 0,
            "false_object_pixels": 0,
            "false_background_pixels": 0,
            "unknown_color_pixels": 0,
            "frames_touching_object": 0,
            "uncovered_gt_pixels": 0,
            "false_uncovered_pixels": 0,
        }
        for mask, gt, pred_label, uncovered_map in zip(
            masks, truth, predicted, uncovered
        ):
            false_object = int((mask & (gt == CLASS_OBJECT)).sum())
            stats["pred_pixels"] += int(mask.sum())
            stats["gt_arm_pixels"] += int((gt == CLASS_ARM).sum())
            stats["gt_object_pixels"] += int((gt == CLASS_OBJECT).sum())
            stats["gt_background_pixels"] += int((gt == CLASS_BACKGROUND).sum())
            stats["true_arm_pixels"] += int((mask & (gt == CLASS_ARM)).sum())
            stats["false_object_pixels"] += false_object
            stats["false_background_pixels"] += int(
                (mask & (gt == CLASS_BACKGROUND)).sum()
            )
            stats["unknown_color_pixels"] += int((pred_label == CLASS_UNKNOWN).sum())
            stats["frames_touching_object"] += 1 if false_object else 0
            stats["uncovered_gt_pixels"] += int(uncovered_map.sum())
            stats["false_uncovered_pixels"] += int((mask & uncovered_map).sum())

        if preview_rows > 0 and frames:
            picks = np.unique(
                np.linspace(0, len(frames) - 1, preview_rows).round().astype(int)
            )
            rows = []
            for index in picks:
                rgb = frames[index][1]
                rows.append(
                    [
                        rgb,
                        apply_red_mask(rgb, masks[index]),
                        _error_image(masks[index], truth[index]),
                    ]
                )
            _write_png(
                Path(out_dir) / f"{task}_{episode_name}_preview.png", _grid(rows)
            )
    return stats


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def summarize(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "frames",
        "pred_pixels",
        "gt_arm_pixels",
        "gt_object_pixels",
        "gt_background_pixels",
        "true_arm_pixels",
        "false_object_pixels",
        "false_background_pixels",
        "unknown_color_pixels",
        "frames_touching_object",
        "uncovered_gt_pixels",
        "false_uncovered_pixels",
    ]
    total = {key: int(sum(item[key] for item in records)) for key in keys}
    total["物体误标率"] = _ratio(total["false_object_pixels"], total["gt_object_pixels"])
    total["背景误标率"] = _ratio(
        total["false_background_pixels"], total["gt_background_pixels"]
    )
    total["机械臂召回"] = _ratio(total["true_arm_pixels"], total["gt_arm_pixels"])
    total["标定精确率"] = _ratio(total["true_arm_pixels"], total["pred_pixels"])
    total["未见颜色占比"] = _ratio(
        total["unknown_color_pixels"], total["frames"] * 256 * 256
    )
    total["碰到物体的帧占比"] = _ratio(total["frames_touching_object"], total["frames"])
    return total


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h5", nargs="+", required=True, help="h5 路径或 glob")
    parser.add_argument(
        "--model",
        default=str(SCRIPT_DIR / "outputs" / "color_model.npz"),
        help="fit_color_model.py 产出的颜色表",
    )
    parser.add_argument(
        "--episodes", default="10-19", help="验证集 episode（默认后 10 个）"
    )
    parser.add_argument(
        "--out", default=str(SCRIPT_DIR / "outputs" / "holdout"), help="产物目录"
    )
    parser.add_argument("--preview-rows", type=int, default=8, help="preview 抽帧行数")
    parser.add_argument(
        "--preview-episodes",
        default="10",
        help="只给这些 episode 出 preview 图（指标始终按全部验证 episode 算）；空串表示全出",
    )
    parser.add_argument("--workers", type=int, default=8, help="并行进程数")
    parser.add_argument(
        "--no-shared-veto",
        dest="veto_shared",
        action="store_false",
        default=True,
        help="关掉混合支撑否决（纯归一化似然 argmax），用于与默认口径做对照",
    )
    parser.add_argument("--open-iterations", type=int, default=1)
    parser.add_argument("--temporal-window", type=int, default=3)
    parser.add_argument("--final-erode", type=int, default=1)
    args = parser.parse_args(argv)

    paths = resolve_h5(args.h5)
    wanted = set(parse_episodes(args.episodes))
    params = MaskParams(
        open_iterations=args.open_iterations,
        temporal_window=args.temporal_window,
        final_erode=args.final_erode,
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    preview_only = (
        set(parse_episodes(args.preview_episodes)) if args.preview_episodes else None
    )
    jobs: list[tuple[str, str]] = []
    for path in paths:
        with h5py.File(str(path), "r") as handle:
            for name in episode_names(handle):
                if int(name[len("episode_") :]) in wanted:
                    jobs.append((str(path), name))
    if not jobs:
        raise SystemExit("验证集为空：没有任何 episode 命中")
    print(f"验证集：{len(paths)} 个 h5 × {len(jobs)} 个 episode，并行 {args.workers}")

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_episode,
                h5_path,
                episode_name,
                args.model,
                str(out_dir),
                params,
                args.preview_rows
                if preview_only is None
                or int(episode_name[len("episode_") :]) in preview_only
                else 0,
                args.veto_shared,
            ): (h5_path, episode_name)
            for h5_path, episode_name in jobs
        }
        for future in as_completed(futures):
            records.append(future.result())
    elapsed = time.perf_counter() - started

    records.sort(key=lambda item: (item["task"], item["episode"]))
    by_task: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_task.setdefault(record["task"], []).append(record)

    payload = {
        "参数": {
            "颜色表": args.model,
            "验证集": sorted(wanted),
            "混合支撑否决": bool(args.veto_shared),
            "开运算次数": params.open_iterations,
            "时间窗": params.temporal_window,
            "最终腐蚀次数": params.final_erode,
        },
        "耗时秒": round(elapsed, 1),
        "全局": summarize(records),
        "逐任务": {task: summarize(items) for task, items in by_task.items()},
        "逐 episode": records,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    overall = payload["全局"]
    print(
        json.dumps(
            {
                "耗时秒": payload["耗时秒"],
                "全局": {
                    k: overall[k]
                    for k in (
                        "物体误标率",
                        "背景误标率",
                        "机械臂召回",
                        "标定精确率",
                        "未见颜色占比",
                        "碰到物体的帧占比",
                        "false_object_pixels",
                    )
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    worst = sorted(
        by_task.items(),
        key=lambda item: summarize(item[1])["false_object_pixels"],
        reverse=True,
    )[:5]
    print("误标物体像素最多的 5 个任务：")
    for task, items in worst:
        stats = summarize(items)
        print(
            f"  {task}: {stats['false_object_pixels']} px"
            f"（物体误标率 {stats['物体误标率']}，召回 {stats['机械臂召回']}）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
