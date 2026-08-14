#!/usr/bin/env python3
"""网格 mask 阈值扫描入口：全 64 档指标 + 三套预览图。

对给定 episode 逐帧跑「颜色表分类 → 四条形态学规则」得到像素级机械臂 mask（与
`render_outputs.process_episode` 前半段逐字同构），然后按 `grid_mask.py` 的口径
网格化（32×32 格、每格 8×8 px、对齐 Wan VAE 输入的 8× 空间下采样），拿 GT 当尺子
量化每个阈值的代价。

## 核心设计：阈值无关的 65 行累计表

每格的预测计数 v ∈ [0, 64] 与阈值无关。逐帧算 32×32 计数图后用 `np.bincount`
累成 65 行表，任意阈值 K 的聚合指标都是该表的后缀和（Σ_{v≥K}），逐位精确——
所以 JSON 里直接给**全 64 档**曲线，出图只挑 8 个候选档；统计全在格空间做，
不上采样回像素域。该推导的正确性由 `tests/lightweight/test_grid_mask_v4_2.py`
的「累计表后缀和等于直算」用例锁死。

## ⚠ 刚性红线不适用于网格口径

整格涂红必然覆盖物体/背景像素，「误标物体恒为 0」在网格口径下必然击穿。因此本
入口**刻意不 import 也不调用 `render_outputs.enforce_no_false_object`**——那道
闸门是像素口径的存在理由，网格口径只做 GT 量化记录、不设闸门。`render_outputs.py`
本身一个字不动，仍是像素口径的唯一全量指标入口。

## 阈值全局统一

单一整数 K 对全部任务 / episode / 格子位置一体生效（用户拍板口径）。本入口是
**扫描器**：不接受 `--min-pixels` 单值参数，永远扫全 64 档；逐任务/逐 episode
的分解只用于观测「哪个任务在某全局 K 下最吃亏」，不派生分任务阈值。

## 数据口径分工

- 目视挑阈值：标定集 val ep0-5 出预览图。⚠ ep0-9 是颜色表的拟合集，**其上一切
  数字偏乐观、不作结论**（JSON 参数块会自动注明）。
- 可引用数字：评估集 val ep10-19（与 `validation_val_ep10-19.json` 同口径）。
  该口径下脚本自动对拍五个锚点数字（帧数 / 像素 mask 像素 / GT 三类像素），
  逐位不等即非零退出——证明本入口复刻的像素链路与全量入口零口径漂移。

用法（在仓库根）：

    # 评估集全量量化（全 64 档进 JSON，不出图，自动对拍锚点）
    uv run --no-sync python scripts/data-generation-v4.2/grid_sweep.py \\
      --episodes 10-19 --no-preview --workers 16 \\
      --out scripts/data-generation-v4.2/outputs/json/grid_sweep_val_ep10-19.json

    # 标定集预览出图（目视挑阈值用）
    uv run --no-sync python scripts/data-generation-v4.2/grid_sweep.py \\
      --episodes 0-5 --workers 16 --candidate-k 1,2,4,8,13,20,26,32 \\
      --preview-dir scripts/data-generation-v4.2/outputs/grid_sweep_val_ep0-5 \\
      --out scripts/data-generation-v4.2/outputs/json/grid_sweep_val_ep0-5.json
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

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arm_mask_v4 import MaskParams, apply_red_mask, arm_masks_for_episode  # noqa: E402
from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_OBJECT,
    ColorModel,
    class_ids_from_setup,
    episode_names,
    iter_episode_frames,
    labels_from_segmentation,
    uncovered_mask,
)
from fit_color_model import parse_episodes, resolve_h5  # noqa: E402
from grid_mask import (  # noqa: E402
    WAN_VAE_SPATIAL_DOWNSAMPLE,
    GridParams,
    cell_counts,
    grid_from_counts,
    upsample_grid,
)

# 共享件按唯一口径 import：误差图四色、比率的 None 语义都不许第二处定义。
# ⚠ 刻意不 import enforce_no_false_object——刚性闸门不适用于网格口径（见模块 docstring）
from render_outputs import _error_image, _ratio  # noqa: E402
from segmentation_walkthrough import _gt_image, _pick_frame  # noqa: E402


DEFAULT_CANDIDATE_K = (1, 2, 4, 8, 13, 20, 26, 32)

# 65 行累计表的列布局（行索引 = 格内预测计数 v ∈ [0, 64]）
COL_CELLS = 0  # 预测计数恰为 v 的格子数
COL_PRED_PX = 1  # 这些格子里像素 mask 的像素数（= v·cells，兼自校验）
COL_GT_ARM = 2  # 这些格子里 GT 臂像素数
COL_GT_OBJ = 3  # GT 物体像素数（含 GT 兜底，与 labels_from_segmentation 口径一致）
COL_GT_BG = 4  # GT 背景像素数
COL_GT_UNCOV = 5  # 其中 GT 兜底（setup 未覆盖 seg id）像素数，细分不许静默
COL_NO_ARM = 6  # 其中 GT 臂像素 == 0 的格子数（涂了就是纯误涂）
COL_TOUCH_ARM = 7  # 其中 GT 臂像素 ≥ 1 的格子数
COL_ARM_MAJOR = 8  # 其中 GT 臂像素 ≥ 半格 的格子数
COL_TOUCH_OBJ = 9  # 其中 GT 物体像素 ≥ 1 的格子数
TABLE_COLUMNS = 10


def _bincount_cells(
    pred_counts: np.ndarray, weights: np.ndarray | None, table_rows: int
) -> np.ndarray:
    """按格的预测计数档位 bincount；weights 为 None 时数格子数。"""
    if weights is None:
        return np.bincount(pred_counts, minlength=table_rows).astype(np.int64)
    # float64 对 ≤2^53 的整数精确，这里的量级（单帧 ≤ 65536）远在其内
    return np.bincount(
        pred_counts, weights=weights.astype(np.float64), minlength=table_rows
    ).astype(np.int64)


def process_episode_grid(
    h5_path: str,
    episode_name: str,
    model_path: str,
    params: MaskParams,
    candidate_k: tuple[int, ...],
    cell_size: int,
    want_preview: bool,
) -> dict[str, Any]:
    """一个 episode 的全帧格空间统计（+ 可选预览载荷）。

    前半段（分类 → 形态学）与 `render_outputs.process_episode` 逐字同构，这是
    锚点对拍能成立的前提；后半段全部在 32×32 格空间做，与阈值无关。
    """
    model = ColorModel.load(model_path)
    task = Path(h5_path).stem.replace("record_dataset_", "")
    cell_area = cell_size * cell_size
    table_rows = cell_area + 1

    with h5py.File(h5_path, "r") as handle:
        episode = handle[episode_name]
        class_ids = class_ids_from_setup(episode["setup"])
        frames = list(iter_episode_frames(episode))
        # ⚠ iter_episode_frames 是 4 元组 (timestep 名, front_rgb, segmentation, is_video_demo)
        predicted = [model.classify(rgb) for _, rgb, _, _ in frames]
        truth = [
            labels_from_segmentation(segmentation, class_ids)
            for _, _, segmentation, _ in frames
        ]
        uncovered = [
            uncovered_mask(segmentation, class_ids) for _, _, segmentation, _ in frames
        ]
        demo_flags = [flag for _, _, _, flag in frames]
        masks = arm_masks_for_episode(predicted, demo_flags, params)

        table = np.zeros((table_rows, TABLE_COLUMNS), np.int64)
        frames_with_object_paint = {k: 0 for k in candidate_k}
        frames_grid_empty_but_gt_arm = {k: 0 for k in candidate_k}
        # 逐帧的 K=1 涂进物体像素数（选「最坏帧」用；K=1 是最激进档，8 档共用此帧）
        painted_obj_k1_per_frame: list[int] = []
        gt_arm_px_per_frame: list[int] = []

        # ⚠ 格空间统计只用 truth（GT 尺子），不许误用 predicted——
        # CLASS_MIX == CLASS_OBJECT == 1 数值相同、语义不同
        for mask, gt, uncov in zip(masks, truth, uncovered):
            pred_cell = cell_counts(mask, cell_size).ravel()
            gt_arm_cell = cell_counts(gt == CLASS_ARM, cell_size).ravel()
            gt_obj_cell = cell_counts(gt == CLASS_OBJECT, cell_size).ravel()
            gt_bg_cell = cell_counts(gt == CLASS_BACKGROUND, cell_size).ravel()
            gt_uncov_cell = cell_counts(np.asarray(uncov), cell_size).ravel()
            # GT 三类穷尽：一旦破了说明 labels_from_segmentation 口径变了
            if not np.array_equal(
                gt_arm_cell + gt_obj_cell + gt_bg_cell,
                np.full_like(gt_arm_cell, cell_area),
            ):
                raise AssertionError("GT 三类在格内不穷尽，labels 口径疑似变更")

            table[:, COL_CELLS] += _bincount_cells(pred_cell, None, table_rows)
            table[:, COL_PRED_PX] += _bincount_cells(pred_cell, pred_cell, table_rows)
            table[:, COL_GT_ARM] += _bincount_cells(pred_cell, gt_arm_cell, table_rows)
            table[:, COL_GT_OBJ] += _bincount_cells(pred_cell, gt_obj_cell, table_rows)
            table[:, COL_GT_BG] += _bincount_cells(pred_cell, gt_bg_cell, table_rows)
            table[:, COL_GT_UNCOV] += _bincount_cells(
                pred_cell, gt_uncov_cell, table_rows
            )
            table[:, COL_NO_ARM] += _bincount_cells(
                pred_cell, (gt_arm_cell == 0).astype(np.int64), table_rows
            )
            table[:, COL_TOUCH_ARM] += _bincount_cells(
                pred_cell, (gt_arm_cell >= 1).astype(np.int64), table_rows
            )
            table[:, COL_ARM_MAJOR] += _bincount_cells(
                pred_cell, (gt_arm_cell >= cell_area // 2).astype(np.int64), table_rows
            )
            table[:, COL_TOUCH_OBJ] += _bincount_cells(
                pred_cell, (gt_obj_cell >= 1).astype(np.int64), table_rows
            )

            gt_arm_total = int(gt_arm_cell.sum())
            gt_arm_px_per_frame.append(gt_arm_total)
            painted_obj_k1_per_frame.append(int(gt_obj_cell[pred_cell >= 1].sum()))
            for k in candidate_k:
                chosen = pred_cell >= k
                if int(gt_obj_cell[chosen].sum()) > 0:
                    frames_with_object_paint[k] += 1
                if not chosen.any() and gt_arm_total > 0:
                    frames_grid_empty_but_gt_arm[k] += 1

        # 自校验：COL_PRED_PX 逐行必须等于 v·cells
        rows = np.arange(table_rows, dtype=np.int64)
        if not np.array_equal(table[:, COL_PRED_PX], rows * table[:, COL_CELLS]):
            raise AssertionError("累计表自校验失败：pred_px ≠ v·cells")

        record: dict[str, Any] = {
            "task": task,
            "episode": episode_name,
            "frames": len(frames),
            "table": table,
            "frames_with_object_paint": frames_with_object_paint,
            "frames_grid_empty_but_gt_arm": frames_grid_empty_but_gt_arm,
        }

        if want_preview:
            # 两张代表帧，挑选规则都与 K 无关（8 档共用同帧才横向可比）：
            # 典型帧 = 走查同口径 _pick_frame；最坏帧 = K=1 下涂进 GT 物体最多的帧
            typical_index, typical_false_object = _pick_frame(masks, truth)
            worst_index = int(np.argmax(painted_obj_k1_per_frame))
            record["preview"] = {
                kind: {
                    "frame_index": index,
                    "timestep": frames[index][0],
                    "rgb": frames[index][1],
                    "gt": truth[index].astype(np.int8),
                    "mask": masks[index],
                    "gt_arm_pixels": gt_arm_px_per_frame[index],
                    "false_object": typical_false_object if kind == "typical" else 0,
                    "painted_obj_k1": painted_obj_k1_per_frame[index],
                }
                for kind, index in (("typical", typical_index), ("worst", worst_index))
            }
    return record


# ---------------------------------------------------------------------------
# 指标：全部从 65 行累计表的后缀和推导
# ---------------------------------------------------------------------------


def anchors_from_table(
    table: np.ndarray, frames: int, cell_area: int
) -> dict[str, int]:
    """与阈值无关的锚点量（全列和 + 帧数）。"""
    total = table.sum(axis=0)
    return {
        "frames": int(frames),
        "cells_total": int(total[COL_CELLS]),
        "pixel_mask_pixels": int(total[COL_PRED_PX]),
        "gt_arm_pixels": int(total[COL_GT_ARM]),
        "gt_object_pixels": int(total[COL_GT_OBJ]),
        "gt_background_pixels": int(total[COL_GT_BG]),
        "gt_uncovered_pixels": int(total[COL_GT_UNCOV]),
        "gt_touch_cells_total": int(total[COL_TOUCH_ARM]),
        "gt_major_cells_total": int(total[COL_ARM_MAJOR]),
        # GT 侧格类定义与 K 无关（触臂 = 格内 GT 臂 ≥1；臂主导 = ≥ 半格）。
        # ⚠ 不做与 K 对称的 GT 定义——分子分母同缩会出「阈值越高召回越好」的假象
        "GT臂主导格定义": f"格内 GT 臂像素 ≥ {cell_area // 2}",
    }


def metrics_for_threshold(
    table: np.ndarray, anchors: dict[str, Any], min_pixels: int, cell_area: int
) -> dict[str, Any]:
    """单个全局阈值 K 的全部指标 = 表的后缀和 Σ_{v≥K}。"""
    suffix = table[min_pixels:].sum(axis=0)
    grid_cells = int(suffix[COL_CELLS])
    painted_pixels = grid_cells * cell_area
    painted_gt_arm = int(suffix[COL_GT_ARM])
    painted_gt_object = int(suffix[COL_GT_OBJ])
    painted_gt_background = int(suffix[COL_GT_BG])
    # 三分解恒等式：GT 三类穷尽 ⇒ 涂红像素恰好分完
    if painted_gt_arm + painted_gt_object + painted_gt_background != painted_pixels:
        raise AssertionError(f"K={min_pixels} 三分解恒等式被破坏")
    return {
        "min_pixels": min_pixels,
        "占比": f"{min_pixels}/{cell_area} = {min_pixels / cell_area:.1%}",
        "grid_cells": grid_cells,
        "painted_pixels": painted_pixels,
        "painted_gt_arm": painted_gt_arm,
        "painted_gt_object": painted_gt_object,
        "painted_gt_background": painted_gt_background,
        "painted_gt_uncovered": int(suffix[COL_GT_UNCOV]),
        "pixel_mask_in_grid": int(suffix[COL_PRED_PX]),
        "cells_no_arm": int(suffix[COL_NO_ARM]),
        "cells_touching_object": int(suffix[COL_TOUCH_OBJ]),
        "hit_gt_touch_cells": int(suffix[COL_TOUCH_ARM]),
        "hit_gt_major_cells": int(suffix[COL_ARM_MAJOR]),
        "网格臂格占比（/ 全部格）": _ratio(grid_cells, anchors["cells_total"]),
        "GT 臂像素覆盖率（/ GT 臂像素）": _ratio(
            painted_gt_arm, anchors["gt_arm_pixels"]
        ),
        "GT 物体像素被涂比例（/ GT 物体像素）": _ratio(
            painted_gt_object, anchors["gt_object_pixels"]
        ),
        "GT 背景像素被涂比例（/ GT 背景像素）": _ratio(
            painted_gt_background, anchors["gt_background_pixels"]
        ),
        "涂红像素中 GT 物体占比（/ 涂红像素）": _ratio(
            painted_gt_object, painted_pixels
        ),
        "网格精确率（/ 涂红像素）": _ratio(painted_gt_arm, painted_pixels),
        "像素 mask 保留率（/ 像素 mask 像素）": _ratio(
            int(suffix[COL_PRED_PX]), anchors["pixel_mask_pixels"]
        ),
        "GT 触臂格召回（/ GT 触臂格）": _ratio(
            int(suffix[COL_TOUCH_ARM]), anchors["gt_touch_cells_total"]
        ),
        "GT 臂主导格召回（/ GT 臂主导格）": _ratio(
            int(suffix[COL_ARM_MAJOR]), anchors["gt_major_cells_total"]
        ),
        "纯误涂格占比（/ 网格臂格）": _ratio(int(suffix[COL_NO_ARM]), grid_cells),
    }


def compensation_table(table: np.ndarray, cell_area: int) -> list[dict[str, Any]]:
    """低估补偿换算表：逐计数档位 v 的「名义占比 vs GT 臂平均占比」。

    「名义占比」是链路看到的（像素 mask 计数），「GT 臂平均占比」是真相；两者之差
    就是像素 mask 漏标（评估集召回 0.817440）造成的系统性低估——想选「格内真实臂
    占比 ≥ X」的阈值，直接在这张表上找 GT 臂平均占比 ≈ X 的档位，不必做整体反推
    （整体反推假设漏标在格间均匀，实际薄边缘格漏得多、臂身中央格几乎不漏）。
    """
    out = []
    for v in range(table.shape[0]):
        cells = int(table[v, COL_CELLS])
        out.append(
            {
                "v": v,
                "名义占比": round(v / cell_area, 6),
                "cells": cells,
                "GT臂平均占比": _ratio(int(table[v, COL_GT_ARM]), cells * cell_area),
                "GT物体平均占比": _ratio(int(table[v, COL_GT_OBJ]), cells * cell_area),
                "GT背景平均占比": _ratio(int(table[v, COL_GT_BG]), cells * cell_area),
            }
        )
    return out


def _sum_frame_counters(
    records: Sequence[dict[str, Any]], key: str, candidate_k: tuple[int, ...]
) -> dict[int, int]:
    return {k: sum(record[key][k] for record in records) for k in candidate_k}


def summarize_scope(
    records: Sequence[dict[str, Any]],
    candidate_k: tuple[int, ...],
    cell_area: int,
    thresholds: Sequence[int],
) -> dict[str, Any]:
    """一个聚合范围（全局 / 单任务）的锚点 + 逐阈值指标。"""
    table = np.sum([record["table"] for record in records], axis=0)
    frames = sum(record["frames"] for record in records)
    anchors = anchors_from_table(table, frames, cell_area)
    frame_paint = _sum_frame_counters(records, "frames_with_object_paint", candidate_k)
    frame_empty = _sum_frame_counters(
        records, "frames_grid_empty_but_gt_arm", candidate_k
    )
    by_threshold: dict[str, Any] = {}
    for k in thresholds:
        metrics = metrics_for_threshold(table, anchors, k, cell_area)
        if k in candidate_k:
            metrics["frames_with_object_paint"] = frame_paint[k]
            metrics["frames_grid_empty_but_gt_arm"] = frame_empty[k]
        by_threshold[str(k)] = metrics
    return {"锚点": anchors, "逐阈值": by_threshold, "_table": table}


# ---------------------------------------------------------------------------
# 预览渲染（PIL 拼图；给 agent 的 tiles 与给人的 mosaic/strips 两套）
# ---------------------------------------------------------------------------

GRID_OVERLAY_ALPHA = 0.45  # 半透明红：涂死就看不见格里盖了什么
COLOR_BOTH = (96, 226, 240)  # 青：网格与像素 mask 都标（呼应走查 KEEP 色）
COLOR_GRID_ONLY = (255, 190, 60)  # 橙黄：网格多涂出来的（本入口新增的唯一一档配色）
COLOR_PIXEL_ONLY = (0, 0, 255)  # 蓝：像素 mask 有但网格丢了（呼应 COLOR_MISSED_ARM）
CELL_EDGE_COLOR = (255, 255, 120)  # 被选中格的 1px 描边
TILE_SCALE_AGENT = 2  # 给 agent：256→512，整图长边约 1.6k，只被轻压
TILE_SCALE_HUMAN = 3  # 给人：256→768，人可自己放大


def _nearest(image: np.ndarray, scale: int) -> np.ndarray:
    """最近邻整数倍放大（np.repeat×2）。⚠ 禁止任何插值——块状硬边正是要看的东西。"""
    return np.repeat(np.repeat(image, scale, axis=0), scale, axis=1)


def _grid_overlay(
    rgb: np.ndarray, grid: np.ndarray, cell_size: int, scale: int
) -> np.ndarray:
    """原帧 + 半透明红网格 + 选中格描边 + 极淡全局格线。"""
    up = upsample_grid(grid, cell_size)
    base = rgb.astype(np.float32)
    red = np.array((255.0, 0.0, 0.0))
    base[up] = base[up] * (1 - GRID_OVERLAY_ALPHA) + red * GRID_OVERLAY_ALPHA
    big = _nearest(base.astype(np.uint8), scale).astype(np.float32)
    # 极淡全局格线（不画满格实线——1024 格全实线会糊成一片，但完全不画又看不出块状）
    step = cell_size * scale
    big[::step, :] = big[::step, :] * 0.85 + 255 * 0.15
    big[:, ::step] = big[:, ::step] * 0.85 + 255 * 0.15
    big = big.astype(np.uint8)
    # 被选中格的 1px 描边
    edge = np.array(CELL_EDGE_COLOR, np.uint8)
    for row, col in zip(*np.nonzero(grid)):
        y0, x0 = row * step, col * step
        y1, x1 = y0 + step - 1, x0 + step - 1
        big[y0, x0 : x1 + 1] = edge
        big[y1, x0 : x1 + 1] = edge
        big[y0 : y1 + 1, x0] = edge
        big[y0 : y1 + 1, x1] = edge
    return big


def _diff_image(pixel_mask: np.ndarray, up_grid: np.ndarray) -> np.ndarray:
    """网格 vs 像素三色差异图：青=都标 / 橙黄=网格多涂 / 蓝=网格丢。"""
    image = np.zeros((*pixel_mask.shape, 3), np.uint8)
    image[up_grid & pixel_mask] = COLOR_BOTH
    image[up_grid & ~pixel_mask] = COLOR_GRID_ONLY
    image[pixel_mask & ~up_grid] = COLOR_PIXEL_ONLY
    return image


def _load_pixel_recall(path: Path) -> dict[str, float]:
    """从已归档的 validation JSON 读逐任务像素级召回（标题栏与 mosaic 排序用）。"""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        task: stats["机械臂召回"]
        for task, stats in payload.get("逐任务", {}).items()
        if stats.get("机械臂召回") is not None
    }


def render_previews(
    entries: Sequence[dict[str, Any]],
    aggregated: dict[str, dict[str, dict[str, Any]]] | None,
    candidate_k: tuple[int, ...],
    cell_size: int,
    preview_dir: Path,
    pixel_recall: dict[str, float],
    kinds: tuple[str, ...],
) -> dict[str, int]:
    """产出预览图。

    `entries` 是扁平的代表帧清单（每项含 task / episode / kind / payload），tiles
    逐项渲染；`aggregated` 为**每任务聚合后**的代表帧（task → kind → 载荷），只有
    它非空时才产出 mosaic / strips——那两套按任务横向排布，逐 episode 模式下没有
    对应语义（同一格位会被 11 个 episode 争用），故直接跳过。
    """
    from PIL import Image, ImageDraw, ImageFont

    from segmentation_walkthrough import FONT_PATH

    cell_area = cell_size * cell_size

    def font(size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(FONT_PATH, size)

    def text_center(draw, text, box, size, fill=(240, 240, 240)):
        x0, y0, x1, y1 = box
        f = font(size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=f)
        draw.text(
            (
                (x0 + x1 - (right - left)) / 2 - left,
                (y0 + y1 - (bottom - top)) / 2 - top,
            ),
            text,
            font=f,
            fill=fill,
        )

    def compose(
        rows: list[list[tuple[np.ndarray, str, str]]],
        title: str,
        legend: str,
        out_path: Path,
        tile: int,
    ) -> None:
        """通用拼图：rows 是 [(图, 表头, 脚注)] 的二维排布。"""
        gap, pad, title_h, head_h, foot_h, legend_h = 10, 16, 56, 30, 26, 34
        columns = max(len(row) for row in rows)
        width = pad * 2 + columns * tile + (columns - 1) * gap
        row_h = head_h + tile + foot_h
        height = title_h + len(rows) * row_h + legend_h + pad
        canvas = Image.new("RGB", (width, height), (24, 24, 28))
        draw = ImageDraw.Draw(canvas)
        text_center(draw, title, (0, 0, width, title_h), 22)
        for row_index, row in enumerate(rows):
            y0 = title_h + row_index * row_h
            for col_index, (image, head, foot) in enumerate(row):
                x0 = pad + col_index * (tile + gap)
                if head:
                    text_center(draw, head, (x0, y0, x0 + tile, y0 + head_h), 16)
                canvas.paste(Image.fromarray(image), (x0, y0 + head_h))
                if foot:
                    text_center(
                        draw,
                        foot,
                        (x0, y0 + head_h + tile, x0 + tile, y0 + head_h + tile + foot_h),
                        14,
                        fill=(170, 170, 178),
                    )
        if legend:
            text_center(
                draw, legend, (0, height - legend_h - 6, width, height - 6), 15,
                fill=(170, 170, 178),
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path)

    tiles_dir = preview_dir / "tiles"
    mosaic_dir = preview_dir / "mosaic"
    strips_dir = preview_dir / "strips"
    written = {"tiles": 0, "mosaic": 0, "strips": 0}

    diff_legend = (
        "差异图：青=网格与像素 mask 都标 / 橙黄=网格多涂 / 蓝=网格丢 ｜ "
        "误差图：白=臂标对 / 红=涂到物体 / 黄=涂到背景 / 蓝=漏臂"
    )

    # ---- tiles：每（代表帧 × 阈值）一张 2×3，给 agent 读 ----
    for entry in entries:
        task, kind, payload = entry["task"], entry["kind"], entry["payload"]
        if kind not in kinds:
            continue
        # 逐 episode 模式的文件名带 ep 号（同一任务会出多张，不带号会互相覆盖）；
        # 聚合模式沿用原命名，既有产物与外部引用不受影响
        stem = task if aggregated is not None else f"{task}_ep{entry['episode_index']:02d}"
        rgb = payload["rgb"]
        gt = payload["gt"].astype(np.int64)
        mask = payload["mask"]
        counts = cell_counts(mask, cell_size)
        recall = pixel_recall.get(task)
        recall_text = f"像素级召回 {recall:.3f}" if recall is not None else ""
        scale = TILE_SCALE_AGENT
        base_row = [
            (_nearest(rgb, scale), "原帧 front_rgb", ""),
            (_nearest(_gt_image(gt), scale), "GT 三类（白=臂 橙=物体 蓝=背景）", ""),
            (
                _nearest(apply_red_mask(rgb, mask), scale),
                "像素 mask 红遮罩（基准）",
                f"像素 mask {int(mask.sum())} px",
            ),
        ]
        for k in candidate_k:
            grid = grid_from_counts(counts, k)
            up = upsample_grid(grid, cell_size)
            painted_arm = int((up & (gt == CLASS_ARM)).sum())
            painted_obj = int((up & (gt == CLASS_OBJECT)).sum())
            painted_bg = int((up & (gt == CLASS_BACKGROUND)).sum())
            grid_row = [
                (
                    _grid_overlay(rgb, grid, cell_size, scale),
                    f"网格叠加（K={k}）",
                    f"{int(grid.sum())} 格 = {int(grid.sum()) * cell_area} px",
                ),
                (
                    _nearest(_diff_image(mask, up), scale),
                    "网格 vs 像素差异",
                    f"多涂 {int((up & ~mask).sum())} px / 丢 {int((mask & ~up).sum())} px",
                ),
                (
                    _nearest(_error_image(up, gt), scale),
                    "网格版误差图（GT 尺子）",
                    f"臂 {painted_arm} / 物体 {painted_obj} / 背景 {painted_bg} px",
                ),
            ]
            title = (
                f"{task} · {payload['episode']} · 帧 {payload['frame_index']}"
                f"（{kind}） · K={k}（{k}/{cell_area} = {k / cell_area:.1%}）"
                + (f" · {recall_text}" if recall_text else "")
            )
            compose(
                [base_row, grid_row],
                title,
                diff_legend,
                tiles_dir / f"{stem}_K{k:02d}_{kind}.png",
                tile=256 * scale,
            )
            written["tiles"] += 1

    if aggregated is None:
        # 逐 episode 模式：mosaic / strips 按任务横向排布，同一格位会被多个 episode
        # 争用，没有对应语义，直接跳过
        return written

    # 任务排序：按像素级召回升序（最弱的 StopCube 恒在左上角），缺数字的排最后
    previews = aggregated
    ordered_tasks = sorted(
        previews, key=lambda task: (pixel_recall.get(task, 2.0), task)
    )

    # ---- mosaic：每阈值一张 4×4（typical 帧的三色差异图），给人拍板 ----
    for k in candidate_k:
        rows: list[list[tuple[np.ndarray, str, str]]] = []
        row: list[tuple[np.ndarray, str, str]] = []
        for task in ordered_tasks:
            payload = previews[task]["typical"]
            mask = payload["mask"]
            up = upsample_grid(
                grid_from_counts(cell_counts(mask, cell_size), k), cell_size
            )
            recall = pixel_recall.get(task)
            foot = f"像素召回 {recall:.3f}" if recall is not None else ""
            row.append((_nearest(_diff_image(mask, up), TILE_SCALE_HUMAN), task, foot))
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        compose(
            rows,
            f"网格 vs 像素差异 · K={k}（{k}/{cell_area} = {k / cell_area:.1%}）"
            "· 任务按像素级召回升序 ·（给人看，不给 agent 读）",
            diff_legend,
            mosaic_dir / f"grid_K{k:02d}.png",
            tile=256 * TILE_SCALE_HUMAN,
        )
        written["mosaic"] += 1

    # ---- strips：每任务一张 1×(2+8)（typical 帧跨阈值横条），给人逐任务对比 ----
    for task in ordered_tasks:
        payload = previews[task]["typical"]
        rgb, mask = payload["rgb"], payload["mask"]
        gt = payload["gt"].astype(np.int64)
        counts = cell_counts(mask, cell_size)
        row = [
            (_nearest(rgb, TILE_SCALE_HUMAN), "原帧", ""),
            (_nearest(_gt_image(gt), TILE_SCALE_HUMAN), "GT 三类", ""),
        ]
        for k in candidate_k:
            grid = grid_from_counts(counts, k)
            row.append(
                (
                    _grid_overlay(rgb, grid, cell_size, TILE_SCALE_HUMAN),
                    f"K={k}（{k / cell_area:.0%}）",
                    f"{int(grid.sum())} 格",
                )
            )
        compose(
            [row],
            f"{task} · {payload['episode']} · 帧 {payload['frame_index']} · "
            "跨阈值横条 ·（给人看，不给 agent 读）",
            "",
            strips_dir / f"{task}_sweep.png",
            tile=256 * TILE_SCALE_HUMAN,
        )
        written["strips"] += 1
    return written


def _episode_index(episode_name: str) -> int:
    return int(episode_name[len("episode_") :])


def _flat_preview_entries(
    records: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """逐 episode 模式的扁平代表帧清单：每个 (任务, episode, kind) 各一项。

    与聚合模式的区别只在这里——聚合模式每任务只留一个 episode 胜出，逐 episode
    模式一个不丢，用于「每个 episode 都出图」的目视核查。
    """
    entries: list[dict[str, Any]] = []
    for record in records:
        if "preview" not in record:
            continue
        for kind, payload in record["preview"].items():
            entries.append(
                {
                    "task": record["task"],
                    "episode": record["episode"],
                    "episode_index": _episode_index(record["episode"]),
                    "kind": kind,
                    "payload": dict(payload, episode=record["episode"]),
                }
            )
    entries.sort(key=lambda item: (item["task"], item["episode_index"], item["kind"]))
    return entries


def _merge_task_previews(
    records: Sequence[dict[str, Any]]
) -> dict[str, dict[str, dict[str, Any]]]:
    """按任务聚合各 episode 的代表帧：typical 取（误标物体, GT 臂像素）最大者，
    worst 取 K=1 涂进物体最多者。附上 episode 名供标题栏。"""
    previews: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        if "preview" not in record:
            continue
        task = record["task"]
        for kind, payload in record["preview"].items():
            payload = dict(payload, episode=record["episode"])
            current = previews.setdefault(task, {}).get(kind)
            if kind == "typical":
                key = (payload["false_object"], payload["gt_arm_pixels"])
                current_key = (
                    (current["false_object"], current["gt_arm_pixels"])
                    if current
                    else (-1, -1)
                )
            else:
                key = (payload["painted_obj_k1"],)
                current_key = (current["painted_obj_k1"],) if current else (-1,)
            if current is None or key > current_key:
                previews[task][kind] = payload
    return previews


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

# 锚点对拍：ep10-19 口径下这五个数必须与已归档 validation JSON 逐位相等，
# 证明本入口复刻的像素链路与全量入口零口径漂移
ANCHOR_KEYS = (
    ("frames", "frames"),
    ("pixel_mask_pixels", "pred_pixels"),
    ("gt_arm_pixels", "gt_arm_pixels"),
    ("gt_object_pixels", "gt_object_pixels"),
    ("gt_background_pixels", "gt_background_pixels"),
)


def check_anchors(anchors: dict[str, Any], validation_path: Path) -> int:
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    reference = payload["全局"]
    failures = []
    for ours, theirs in ANCHOR_KEYS:
        if int(anchors[ours]) != int(reference[theirs]):
            failures.append(f"{ours}={anchors[ours]} ≠ validation.{theirs}={reference[theirs]}")
    if failures:
        print("⚠ 锚点对拍失败（像素链路与全量入口出现口径漂移）：")
        for line in failures:
            print(f"  {line}")
        return 1
    print(
        f"锚点对拍通过：五项与 {validation_path.name} 逐位相等"
        f"（frames={anchors['frames']}, pixel_mask_pixels={anchors['pixel_mask_pixels']}）"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--h5",
        nargs="+",
        default=["artifacts/generated/v4seg-16env-val20ep/record_dataset_*.h5"],
        help="h5 路径或 glob（默认 val split 的 v4seg 数据集）",
    )
    parser.add_argument(
        "--model",
        default=str(SCRIPT_DIR / "outputs" / "color_model.npz"),
        help="fit_color_model.py 产出的颜色表",
    )
    parser.add_argument(
        "--episodes",
        default="10-19",
        help="episode 口径：量化用评估集 10-19；预览出图用标定集 0-5（数字不作结论）",
    )
    parser.add_argument(
        "--out",
        default=str(SCRIPT_DIR / "outputs" / "json" / "grid_sweep_val_ep10-19.json"),
        help="指标 JSON 落盘路径（全部 JSON 产物集中在 outputs/json/）",
    )
    parser.add_argument(
        "--preview-dir",
        default=None,
        help="预览图输出目录（tiles/mosaic/strips 三套）；不给则不出图",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="显式声明不出图（与 --preview-dir 互斥，纯粹让命令行意图可读）",
    )
    parser.add_argument(
        "--preview-per-episode",
        action="store_true",
        help="逐 episode 出 tiles（每任务每 episode 各一张，文件名带 ep 号）；"
        "默认是每任务只出一张聚合代表帧。该模式不产 mosaic/strips（按任务排布，无对应语义）",
    )
    parser.add_argument(
        "--preview-kinds",
        default="typical,worst",
        help="出哪种代表帧：typical（走查同口径最大臂帧）/ worst（K=1 涂进物体最多帧），"
        "逗号分隔",
    )
    parser.add_argument(
        "--candidate-k",
        default=",".join(str(k) for k in DEFAULT_CANDIDATE_K),
        help="出图/帧级统计的候选阈值（逗号分隔的格内像素数）；指标 JSON 恒扫全 64 档",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=WAN_VAE_SPATIAL_DOWNSAMPLE,
        help="格边长 px（默认 8 = Wan VAE 空间下采样倍率，改动前先想清楚对齐关系）",
    )
    parser.add_argument(
        "--anchor-json",
        default=None,
        help="锚点对拍用的 validation JSON；默认 --episodes 10-19 时自动指向已归档文件",
    )
    parser.add_argument("--workers", type=int, default=8, help="并行进程数")
    parser.add_argument("--open-iterations", type=int, default=1)
    parser.add_argument("--temporal-window", type=int, default=3)
    parser.add_argument("--final-erode", type=int, default=1)
    args = parser.parse_args(argv)

    if args.preview_dir and args.no_preview:
        raise SystemExit("--preview-dir 与 --no-preview 互斥")
    want_preview = args.preview_dir is not None
    preview_kinds = tuple(
        item.strip() for item in args.preview_kinds.split(",") if item.strip()
    )
    if not preview_kinds or any(k not in ("typical", "worst") for k in preview_kinds):
        raise SystemExit(f"--preview-kinds 只接受 typical / worst：{preview_kinds}")

    cell_area = args.cell_size * args.cell_size
    candidate_k = tuple(
        sorted({int(item) for item in args.candidate_k.split(",") if item.strip()})
    )
    if not candidate_k or any(k < 1 or k > cell_area for k in candidate_k):
        raise SystemExit(f"候选阈值必须在 [1, {cell_area}] 内：{candidate_k}")

    params = MaskParams(
        open_iterations=args.open_iterations,
        temporal_window=args.temporal_window,
        final_erode=args.final_erode,
    )
    paths = resolve_h5(args.h5)
    wanted = set(parse_episodes(args.episodes))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, str]] = []
    for path in paths:
        with h5py.File(str(path), "r") as handle:
            for name in episode_names(handle):
                if int(name[len("episode_") :]) in wanted:
                    jobs.append((str(path), name))
    if not jobs:
        raise SystemExit("扫描集为空：没有任何 episode 命中")
    print(
        f"网格阈值扫描：{len(paths)} 个 h5 × {len(jobs)} 个 episode，"
        f"格 {args.cell_size}×{args.cell_size}，全 {cell_area} 档 + 候选 {candidate_k}，"
        f"并行 {args.workers}"
    )

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_episode_grid,
                h5_path,
                episode_name,
                args.model,
                params,
                candidate_k,
                args.cell_size,
                want_preview,
            ): (h5_path, episode_name)
            for h5_path, episode_name in jobs
        }
        for future in as_completed(futures):
            records.append(future.result())
    elapsed = time.perf_counter() - started
    records.sort(key=lambda item: (item["task"], item["episode"]))

    thresholds_all = tuple(range(1, cell_area + 1))
    overall = summarize_scope(records, candidate_k, cell_area, thresholds_all)
    # K=1 自检：像素 mask 的每个像素必落在计数 ≥1 的格里，保留率必须精确为 1
    k1 = overall["逐阈值"]["1"]
    if k1["pixel_mask_in_grid"] != overall["锚点"]["pixel_mask_pixels"]:
        raise AssertionError("K=1 像素 mask 保留率 ≠ 1，网格化实现有误")

    by_task: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_task.setdefault(record["task"], []).append(record)
    per_task = {
        task: summarize_scope(items, candidate_k, cell_area, candidate_k)
        for task, items in by_task.items()
    }
    per_episode = [
        {
            "task": record["task"],
            "episode": record["episode"],
            "frames": record["frames"],
            "候选档": {
                str(k): {
                    "grid_cells": int(record["table"][k:, COL_CELLS].sum()),
                    "painted_gt_object": int(record["table"][k:, COL_GT_OBJ].sum()),
                    "painted_gt_arm": int(record["table"][k:, COL_GT_ARM].sum()),
                }
                for k in candidate_k
            },
        }
        for record in records
    ]

    # ⚠ 判据是「与标定集有交集」而非「完全落在标定集内」：ep0-10 这类跨界口径同样
    # 被颜色表的拟合集污染，数字一样偏乐观，必须照样警告
    calibration_scope = bool(wanted & set(range(10)))
    payload = {
        "参数": {
            "颜色表": args.model,
            "episodes": sorted(wanted),
            "格边长px": args.cell_size,
            "格数": f"{256 // args.cell_size}×{256 // args.cell_size}",
            "口径": "格内 v4.2 像素 mask 判臂像素数 ≥ K ⇒ 整格标臂；K 全局统一"
            "（全任务/episode/格子位置一体生效，无任何按任务覆盖）",
            "候选档": list(candidate_k),
            "刚性红线": "不适用于网格口径（整格涂红必覆盖物体/背景像素），"
            "GT 只做量化记录、不设闸门；enforce_no_false_object 刻意未调用",
            "形态学参数": [params.open_iterations, params.temporal_window, params.final_erode],
            **(
                {
                    "⚠ 口径警告": "本文件为颜色表标定集口径（ep0-9 内），数字偏乐观、"
                    "不作结论；可引用数字一律以 val ep10-19 的 grid_sweep JSON 为准"
                }
                if calibration_scope
                else {}
            ),
        },
        "耗时秒": round(elapsed, 1),
        "锚点": overall["锚点"],
        "逐阈值": overall["逐阈值"],
        "逐计数档位": compensation_table(overall["_table"], cell_area),
        "逐任务": {
            task: {"锚点": scope["锚点"], "逐阈值": scope["逐阈值"]}
            for task, scope in per_task.items()
        },
        "逐 episode": per_episode,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"指标 JSON 已写入 {out_path}（全 {cell_area} 档）")

    if want_preview:
        pixel_recall = _load_pixel_recall(
            SCRIPT_DIR / "outputs" / "json" / "validation_val_ep10-19.json"
        )
        preview_dir = Path(args.preview_dir)
        if args.preview_per_episode:
            entries = _flat_preview_entries(records)
            aggregated = None
        else:
            aggregated = _merge_task_previews(records)
            entries = [
                {
                    "task": task,
                    "episode": payload["episode"],
                    "episode_index": _episode_index(payload["episode"]),
                    "kind": kind,
                    "payload": payload,
                }
                for task, kinds in aggregated.items()
                for kind, payload in kinds.items()
            ]
        written = render_previews(
            entries,
            aggregated,
            candidate_k,
            args.cell_size,
            preview_dir,
            pixel_recall,
            preview_kinds,
        )
        print(
            f"预览图已写入 {preview_dir}：tiles {written['tiles']} 张 / "
            f"mosaic {written['mosaic']} 张 / strips {written['strips']} 张"
            + ("（逐 episode 模式不产 mosaic/strips）" if aggregated is None else "")
        )

    # 终端速览：候选档的关键指标
    print("候选档速览（完整曲线见 JSON）：")
    for k in candidate_k:
        metrics = overall["逐阈值"][str(k)]
        print(
            f"  K={k:2d}（{k / cell_area:5.1%}）："
            f"臂覆盖 {metrics['GT 臂像素覆盖率（/ GT 臂像素）']}，"
            f"物体被涂 {metrics['GT 物体像素被涂比例（/ GT 物体像素）']}，"
            f"精确率 {metrics['网格精确率（/ 涂红像素）']}，"
            f"纯误涂格 {metrics['cells_no_arm']}"
        )

    anchor_json = args.anchor_json
    if anchor_json is None and wanted == set(range(10, 20)):
        default_anchor = SCRIPT_DIR / "outputs" / "json" / "validation_val_ep10-19.json"
        if default_anchor.exists():
            anchor_json = str(default_anchor)
    if anchor_json is not None:
        return check_anchors(overall["锚点"], Path(anchor_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
