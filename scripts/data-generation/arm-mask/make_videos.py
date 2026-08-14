#!/usr/bin/env python3
"""可视化视频入口：sidecar + 源 h5 → 逐 episode 多面板 mp4（模式②另出 worst 片段合集）。

## 定位：目视工具，不是判据

本入口**只读** sidecar（make_mask.py 的产物）与源 h5，**不重跑推理链**——想换 K /
换形态学参数出新视频，必须先重跑 make_mask.py。数字判据以 evaluate.py 为准，
视频只负责让人看见。

## 面板布局（每格 256×256，--scale 可整数倍放大）

- **模式①（官方 h5，无 GT）1×3**：RGB 原帧 | 像素 mask 叠加（纯红） | 网格 mask 叠加（半透明红，K=13）
- **模式②（自生带 GT）3×2**，列语义上下对齐（像素在中列、网格在右列）：
  - 上排：RGB 原帧 | 像素 mask 叠加 | 网格 mask 叠加
  - 下排：GT 臂 mask 叠加（纯绿） | 像素误差 | 网格误差
- 误差面板画在压暗灰度 RGB 上：**蓝=漏标臂、红=误涂物体、橙=误涂背景、绿=涂对**。
  ⚠ 红色包含 setup 表未覆盖 seg id 的**兜底物体**像素；网格误差面板必然出现红色
  （整格涂红覆盖物体是网格口径的固有性质），**不等于像素刚性红线被击穿**——红线只
  约束像素口径（evaluate.py 实测 false_object_pixels = 0）。

## worst 片段合集（仅模式②）

逐帧误差 = **网格 mask 对 GT 的漏标臂像素 + 误涂物体像素**（刻意不含误涂背景——
整格涂红盖到背景是网格化的必然代价，不算错；`frame_error` 是该口径的唯一落点）。
全体帧按误差降序取 top-N **峰值帧**（默认 20），各带前后 --context-seconds 上下文，
同 episode 重叠/相邻段合并（峰值取大者）、跨 episode 永不合并，段数可少于 N。
合集按峰值误差降序排列，段前有中文标题卡，峰值帧画黄框；另落 worst.json 机读排名。

## 防错配（最高风险项）

sidecar 与源 h5 必须同批：worker 启动即校验 sidecar root attrs 记录的源文件名 /
字节数 / mtime 与当前 --source 下的文件一致，且 num_frames、timestep_index 逐帧
对齐，任一不符 fail-loud——planner 非确定性意味着重新生成的数据集与旧 sidecar
帧数可能不同，静默错配是灾难。

## 用法（在仓库根）

    # 模式①：官方 h5，默认参数即可
    uv run --no-sync python scripts/data-generation/arm-mask/make_videos.py --workers 16

    # 模式②：通常由 run_generated.py --videos 编排调用（保证与 sidecar 同批）
    uv run --no-sync python scripts/data-generation/arm-mask/make_videos.py \\
      --source artifacts/generated/<目录> --workers 16
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
GT_DATA_DIR = SCRIPT_DIR.parent / "gt-data"
for _path in (str(SCRIPT_DIR), str(GT_DATA_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from arm_mask import apply_red_mask  # noqa: E402
from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_OBJECT,
    class_ids_from_setup,
    labels_from_segmentation,
)
from fit_color_model import parse_episodes  # noqa: E402
from grid_mask import WAN_VAE_SPATIAL_DOWNSAMPLE, upsample_grid  # noqa: E402
from make_mask import (  # noqa: E402
    DEFAULT_SOURCE_ROOT,
    FONT_PATH,
    GRID_MIN_PIXELS,
    GRID_OVERLAY_ALPHA,
    _sorted_numeric_names,
    _source_has_ground_truth,
    iter_frames,
    read_sidecar_episode,
)

# 误差四色（画在压暗灰度底上）
COLOR_MISSED_ARM = (60, 120, 255)  # 蓝：GT 臂但没标（漏标臂）
COLOR_FALSE_OBJECT = (255, 60, 60)  # 红：标了但 GT 是物体（含兜底）
COLOR_FALSE_BACKGROUND = (255, 165, 0)  # 橙：标了但 GT 是背景
COLOR_HIT_ARM = (60, 220, 90)  # 绿：标对（GT 臂且标了）
COLOR_GT_ARM = (0, 230, 60)  # GT 臂面板的纯绿叠加
GRAY_DIM = 0.55  # 误差底图压暗系数（太亮时四色对比度不够）

CANVAS_BG = (18, 18, 22)
CANVAS_FG = (235, 235, 235)
PEAK_BORDER_COLOR = (255, 230, 0)  # worst 合集峰值帧的黄框
PEAK_BORDER_PX = 4

# 布局常量（panel_layout 的唯一口径；W/H 会补齐到 16 的倍数防编码器静默缩放）
PAD = 8
GAP = 6
TITLE_H = 34
PANEL_TITLE_H = 20
FOOT_H = 46
MACRO_BLOCK = 16

MODE_REFERENCE = "reference"
MODE_GENERATED = "generated"


# ---------------------------------------------------------------------------
# 纯函数：着色 / 计数 / 布局（全部进单测）
# ---------------------------------------------------------------------------


def gray3(rgb: np.ndarray) -> np.ndarray:
    """压暗灰度底图：亮度加权后乘 GRAY_DIM，三通道复制。不修改输入。"""
    array = np.asarray(rgb, np.float32)
    gray = (array @ np.array([0.299, 0.587, 0.114], np.float32)) * GRAY_DIM
    return np.repeat(gray.astype(np.uint8)[..., None], 3, axis=2)


class ErrorCounts(NamedTuple):
    """与 error_overlay 四色一一对应的像素计数。"""

    missed_arm: int
    false_object: int
    false_background: int
    hit_arm: int


def _error_classes(
    pred_mask: np.ndarray, gt_labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """四类像素集合（互斥，且并集恰为 pred ∪ GT臂）。着色与计数共用，防两套口径。"""
    pred = np.asarray(pred_mask, bool)
    gt = np.asarray(gt_labels)
    gt_arm = gt == CLASS_ARM
    return (
        gt_arm & ~pred,  # 漏标臂
        pred & (gt == CLASS_OBJECT),  # 误涂物体（含兜底）
        pred & (gt == CLASS_BACKGROUND),  # 误涂背景
        pred & gt_arm,  # 涂对
    )


def error_overlay(rgb: np.ndarray, pred_mask: np.ndarray, gt_labels: np.ndarray) -> np.ndarray:
    """误差面板：压暗灰度底 + 四色硬涂。不修改任何输入。"""
    missed, false_obj, false_bg, hit = _error_classes(pred_mask, gt_labels)
    image = gray3(rgb)
    image[missed] = COLOR_MISSED_ARM
    image[false_obj] = COLOR_FALSE_OBJECT
    image[false_bg] = COLOR_FALSE_BACKGROUND
    image[hit] = COLOR_HIT_ARM
    return image


def error_counts(pred_mask: np.ndarray, gt_labels: np.ndarray) -> ErrorCounts:
    """四类像素计数，与 error_overlay 的着色像素数逐项一致（共用 _error_classes）。"""
    missed, false_obj, false_bg, hit = _error_classes(pred_mask, gt_labels)
    return ErrorCounts(
        missed_arm=int(missed.sum()),
        false_object=int(false_obj.sum()),
        false_background=int(false_bg.sum()),
        hit_arm=int(hit.sum()),
    )


def frame_error(counts: ErrorCounts) -> int:
    """逐帧误差的唯一口径：漏标臂 + 误涂物体。刻意不含误涂背景（网格化的必然代价）。"""
    return counts.missed_arm + counts.false_object


def grid_overlay_fast(
    rgb: np.ndarray,
    grid: np.ndarray,
    cell_size: int = WAN_VAE_SPATIAL_DOWNSAMPLE,
    alpha: float = GRID_OVERLAY_ALPHA,
    draw_lines: bool = False,
) -> np.ndarray:
    """网格叠加：选中格半透明红 + 可选极淡全局格线。纯 numpy，不修改输入。

    ⚠ 不要改用 make_mask._grid_overlay——那是出 6 张静态预览图用的，选中格描边是
    逐格 Python 循环，80k 帧的视频规模下会把耗时抬高一到两个数量级。
    """
    up = upsample_grid(np.asarray(grid, bool), cell_size)
    base = np.asarray(rgb, np.float32).copy()
    red = np.array((255.0, 0.0, 0.0), np.float32)
    base[up] = base[up] * (1 - alpha) + red * alpha
    if draw_lines:
        base[::cell_size, :] = base[::cell_size, :] * 0.85 + 255 * 0.15
        base[:, ::cell_size] = base[:, ::cell_size] * 0.85 + 255 * 0.15
    return base.astype(np.uint8)


def _nearest(image: np.ndarray, scale: int) -> np.ndarray:
    """最近邻整数倍放大。⚠ 禁止插值——块状硬边正是要看的东西。"""
    if scale == 1:
        return image
    return np.repeat(np.repeat(image, scale, axis=0), scale, axis=1)


def _ceil_to(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


@dataclass(frozen=True)
class Layout:
    """画布布局：面板左上角坐标为 (y, x)，row-major。"""

    width: int
    height: int
    tile: int
    cols: int
    rows: int
    panel_boxes: tuple[tuple[int, int], ...]
    panel_title_origins: tuple[tuple[int, int], ...]  # (y, x)，高 PANEL_TITLE_H
    title_origin: tuple[int, int]
    legend_origin: tuple[int, int]
    caption_origin: tuple[int, int]  # cv2.putText 的 (x, y) 基线


def panel_layout(cols: int, rows: int, tile: int) -> Layout:
    """算画布尺寸与各面板坐标。W/H 均补齐到 16 的倍数（imageio macro_block 与
    libx264 偶数要求，不补齐会被静默缩放，compose 的逐位性质就没了）。"""
    inner_w = cols * tile + (cols - 1) * GAP
    row_block = PANEL_TITLE_H + tile
    inner_h = TITLE_H + rows * row_block + (rows - 1) * GAP + FOOT_H
    width = _ceil_to(PAD * 2 + inner_w, MACRO_BLOCK)
    height = _ceil_to(PAD * 2 + inner_h, MACRO_BLOCK)
    assert width % MACRO_BLOCK == 0 and height % MACRO_BLOCK == 0

    boxes: list[tuple[int, int]] = []
    title_origins: list[tuple[int, int]] = []
    for row in range(rows):
        y_title = PAD + TITLE_H + row * (row_block + GAP)
        y_panel = y_title + PANEL_TITLE_H
        for col in range(cols):
            x = PAD + col * (tile + GAP)
            boxes.append((y_panel, x))
            title_origins.append((y_title, x))
    foot_y = PAD + TITLE_H + rows * row_block + (rows - 1) * GAP
    return Layout(
        width=width,
        height=height,
        tile=tile,
        cols=cols,
        rows=rows,
        panel_boxes=tuple(boxes),
        panel_title_origins=tuple(title_origins),
        title_origin=(PAD, PAD),
        legend_origin=(foot_y + 2, PAD),
        caption_origin=(PAD, height - PAD - 8),
    )


def compose_frame(
    template: np.ndarray, panels: Sequence[np.ndarray], layout: Layout
) -> np.ndarray:
    """把面板贴进模板副本。面板尺寸必须恰为 tile×tile，不做任何缩放。"""
    if len(panels) != len(layout.panel_boxes):
        raise ValueError(f"面板数 {len(panels)} 与布局 {len(layout.panel_boxes)} 不符")
    frame = template.copy()
    tile = layout.tile
    for (y, x), panel in zip(layout.panel_boxes, panels):
        if panel.shape != (tile, tile, 3):
            raise ValueError(f"面板 shape {panel.shape} 不是 ({tile}, {tile}, 3)")
        frame[y : y + tile, x : x + tile] = panel
    return frame


def caption_lines(
    task: str,
    episode: int,
    frame_index: int,
    total: int,
    phase: str,
    counts: ErrorCounts | None = None,
    extra: str = "",
) -> tuple[str, ...]:
    """逐帧动态字幕。⚠ 必须纯 ASCII——cv2.putText 画不了中文（中文全在 PIL 预渲染的
    静态模板层）。单测钉死 isascii。"""
    text = f"{task} ep{episode}  frame {frame_index + 1}/{total}  [{phase}]"
    if counts is not None:
        text += (
            f"  err={frame_error(counts)}"
            f" (miss_arm={counts.missed_arm} obj={counts.false_object})"
        )
    if extra:
        text += f"  {extra}"
    return (text,)


# ---------------------------------------------------------------------------
# 纯函数：worst 选段
# ---------------------------------------------------------------------------


class FrameScore(NamedTuple):
    """单帧的误差记录（worker 返回，选段输入）。"""

    task: str
    episode: int
    frame: int
    error: int
    missed_arm: int
    false_object: int


@dataclass(frozen=True)
class Segment:
    """一个 worst 片段（含合并信息）。"""

    task: str
    episode: int
    start: int
    end: int
    peak_frame: int
    peak_error: int
    merged_peaks: tuple[int, ...]


def merge_segments(segments: Sequence[Segment], merge_gap_frames: int = 0) -> list[Segment]:
    """同一 (task, episode) 内按 start 合并重叠/相邻（间隔 ≤ merge_gap_frames）段，
    峰值取误差更大者。跨 episode 的输入直接报错——调用方必须先分组。"""
    if not segments:
        return []
    keys = {(seg.task, seg.episode) for seg in segments}
    if len(keys) != 1:
        raise ValueError(f"merge_segments 只接受同一 (task, episode)：{sorted(keys)}")
    ordered = sorted(segments, key=lambda seg: (seg.start, seg.end))
    merged = [ordered[0]]
    for seg in ordered[1:]:
        prev = merged[-1]
        if seg.start <= prev.end + 1 + merge_gap_frames:
            peak_frame, peak_error = (
                (seg.peak_frame, seg.peak_error)
                if seg.peak_error > prev.peak_error
                else (prev.peak_frame, prev.peak_error)
            )
            merged[-1] = Segment(
                task=prev.task,
                episode=prev.episode,
                start=prev.start,
                end=max(prev.end, seg.end),
                peak_frame=peak_frame,
                peak_error=peak_error,
                merged_peaks=tuple(sorted({*prev.merged_peaks, *seg.merged_peaks})),
            )
        else:
            merged.append(seg)
    return merged


def select_worst_segments(
    scores: Sequence[FrameScore],
    episode_lengths: Mapping[tuple[str, int], int],
    top_n: int,
    context_frames: int,
    merge_gap_frames: int = 0,
) -> list[Segment]:
    """选 worst 片段：误差 > 0 的帧按 (误差降序, task, episode, frame) 稳定排序取
    top_n 个峰值帧，各带 ±context_frames 上下文（边界裁剪不补黑帧），同 episode
    合并，最终按峰值误差降序。合并后段数可少于 top_n（top-N 是帧语义不是段语义）。"""
    ranked = sorted(
        (s for s in scores if s.error > 0),
        key=lambda s: (-s.error, s.task, s.episode, s.frame),
    )[:top_n]
    by_episode: dict[tuple[str, int], list[Segment]] = {}
    for score in ranked:
        total = episode_lengths[(score.task, score.episode)]
        if not 0 <= score.frame < total:
            raise ValueError(f"帧号越界：{score} vs 长度 {total}")
        seg = Segment(
            task=score.task,
            episode=score.episode,
            start=max(0, score.frame - context_frames),
            end=min(total - 1, score.frame + context_frames),
            peak_frame=score.frame,
            peak_error=score.error,
            merged_peaks=(score.frame,),
        )
        by_episode.setdefault((score.task, score.episode), []).append(seg)
    merged: list[Segment] = []
    for group in by_episode.values():
        merged.extend(merge_segments(group, merge_gap_frames))
    merged.sort(key=lambda seg: (-seg.peak_error, seg.task, seg.episode, seg.start))
    return merged


# ---------------------------------------------------------------------------
# sidecar 与源的错配校验
# ---------------------------------------------------------------------------


def check_sidecar_fingerprint(
    root_attrs: Mapping[str, Any], source_path: Path, context: str
) -> None:
    """sidecar root attrs 记录的源文件指纹必须与当前 --source 下的文件一致。

    planner 非确定性 ⇒ 重新生成的数据集与旧 sidecar 可能帧数不同，静默错配是本入口
    的最高风险，因此文件名 / 字节数 / mtime 三项全对不上任何一项都 fail-loud。
    """
    recorded = str(root_attrs.get("source_h5", ""))
    if Path(recorded).name != source_path.name:
        raise ValueError(f"{context}: sidecar 记录源 {recorded}，当前源 {source_path}")
    stat = source_path.stat()
    if int(root_attrs.get("source_h5_size_bytes", -1)) != stat.st_size:
        raise ValueError(
            f"{context}: 源文件字节数不符（sidecar 记录 "
            f"{root_attrs.get('source_h5_size_bytes')}，实际 {stat.st_size}）——"
            "sidecar 与数据集不是同批产物，请重跑 make_mask.py"
        )
    recorded_mtime = str(root_attrs.get("source_h5_mtime_iso", ""))
    actual_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    if recorded_mtime != actual_mtime:
        raise ValueError(
            f"{context}: 源文件 mtime 不符（sidecar 记录 {recorded_mtime}，"
            f"实际 {actual_mtime}）——sidecar 与数据集不是同批产物，请重跑 make_mask.py"
        )


# ---------------------------------------------------------------------------
# 静态 chrome（中文，PIL 预渲染，每 episode 一次）
# ---------------------------------------------------------------------------

PANEL_TITLES_REFERENCE = ("RGB 原帧", "像素 mask", "网格 mask (K=13)")
PANEL_TITLES_GENERATED = (
    "RGB 原帧",
    "像素 mask",
    "网格 mask (K=13)",
    "GT 臂 mask",
    "像素误差",
    "网格误差",
)
LEGEND_REFERENCE = "红=判臂像素（纯红=像素层，半透明=网格层）；官方数据无 GT，无误差面板"
LEGEND_GENERATED = (
    "误差面板：蓝=漏标臂  红=误涂物体(含兜底)  橙=误涂背景  绿=涂对 ｜ "
    "网格出现红色≠像素红线击穿（红线只约束像素口径）"
)


def render_static_chrome(
    mode: str, task: str, episode: int, layout: Layout
) -> np.ndarray:
    """画布模板：中文标题条 + 各面板小标题 + 底部图例。每 episode 渲染一次，逐帧
    copy 复用——中文只能走 PIL（cv2.putText 画中文出问号），逐帧跑 PIL 太慢。"""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (layout.width, layout.height), CANVAS_BG)
    draw = ImageDraw.Draw(image)

    def font(size: int) -> "ImageFont.FreeTypeFont":
        return ImageFont.truetype(FONT_PATH, size)

    mode_text = "模式②（带 GT）" if mode == MODE_GENERATED else "模式①（官方，无 GT）"
    draw.text(
        (layout.title_origin[1], layout.title_origin[0]),
        f"{task} · episode_{episode} · {mode_text}",
        font=font(20),
        fill=CANVAS_FG,
    )
    titles = PANEL_TITLES_GENERATED if mode == MODE_GENERATED else PANEL_TITLES_REFERENCE
    for (y, x), title in zip(layout.panel_title_origins, titles):
        draw.text((x, y + 1), title, font=font(14), fill=(200, 200, 200))
    legend = LEGEND_GENERATED if mode == MODE_GENERATED else LEGEND_REFERENCE
    draw.text(
        (layout.legend_origin[1], layout.legend_origin[0]),
        legend,
        font=font(13),
        fill=(170, 170, 170),
    )
    return np.asarray(image, np.uint8)


def render_title_card(layout: Layout, lines: Sequence[str]) -> np.ndarray:
    """worst 合集的段前标题卡：黑底居中中文多行。"""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (layout.width, layout.height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT_PATH, 24)
    y = layout.height // 2 - len(lines) * 20
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((layout.width - (box[2] - box[0])) // 2, y), line, font=font, fill=CANVAS_FG)
        y += 44
    return np.asarray(image, np.uint8)


# ---------------------------------------------------------------------------
# 渲染（带 IO）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoOptions:
    """渲染选项（worker 侧全量透传）。"""

    fps: int = 30
    quality: int = 8
    scale: int = 1
    ffmpeg_threads: int = 1
    overwrite: bool = False
    limit_frames: int = 0


def _layout_for(mode: str, scale: int) -> Layout:
    tile = 256 * scale
    return panel_layout(3, 2 if mode == MODE_GENERATED else 1, tile)


def _read_segmentation(episode_group: h5py.Group, timestep_name: str) -> np.ndarray:
    obs = episode_group[timestep_name].get("obs")
    if not isinstance(obs, h5py.Group) or "front_camera_segmentation" not in obs:
        raise KeyError(f"{timestep_name} 缺 obs/front_camera_segmentation")
    return np.squeeze(obs["front_camera_segmentation"][()])


def _build_panels(
    mode: str,
    rgb: np.ndarray,
    px_mask: np.ndarray,
    grid: np.ndarray,
    gt_labels: np.ndarray | None,
) -> tuple[list[np.ndarray], ErrorCounts | None]:
    """单帧全部面板（256 原尺寸）。返回 (面板列表, 网格误差计数或 None)。"""
    panels = [
        np.asarray(rgb),
        apply_red_mask(rgb, px_mask),
        grid_overlay_fast(rgb, grid, draw_lines=True),
    ]
    if mode != MODE_GENERATED:
        return panels, None
    assert gt_labels is not None
    up = upsample_grid(np.asarray(grid, bool))
    gt_panel = np.array(rgb, copy=True)
    gt_panel[gt_labels == CLASS_ARM] = COLOR_GT_ARM
    panels.append(gt_panel)
    panels.append(error_overlay(rgb, px_mask, gt_labels))
    panels.append(error_overlay(rgb, up, gt_labels))
    return panels, error_counts(up, gt_labels)


def _put_caption(frame: np.ndarray, lines: Sequence[str], layout: Layout) -> None:
    import cv2

    x, y = layout.caption_origin
    for line in reversed(lines):
        cv2.putText(
            frame, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1
        )
        y -= 18


def _open_writer(path: Path, opts: VideoOptions):
    import imageio

    return imageio.get_writer(
        str(path),
        fps=opts.fps,
        codec="libx264",
        quality=opts.quality,
        macro_block_size=1,  # 布局已保证 16 的倍数，显式关掉 imageio 的静默缩放双保险
        output_params=["-threads", str(opts.ffmpeg_threads)],
    )


def render_episode(
    mode: str,
    h5_path: str,
    sidecar_path: str,
    episode_index: int,
    out_dir: str,
    opts: VideoOptions,
) -> dict[str, Any]:
    """worker：单 episode 全帧渲染成一个 mp4，返回统计（模式②含逐帧误差）。"""
    import cv2

    cv2.setNumThreads(1)  # 多 worker × cv2 默认多线程会互抢

    started = time.perf_counter()
    task = Path(h5_path).stem.replace("record_dataset_", "")
    name = f"episode_{episode_index}"
    context = f"{task}/{name}"

    side = read_sidecar_episode(sidecar_path, name)
    if "arm_mask_px" not in side:
        raise KeyError(
            f"{context}: sidecar 没有 arm_mask_px——写入时用了 --no-store-pixel-mask，"
            "无法渲染像素层面板"
        )
    check_sidecar_fingerprint(side["root_attrs"], Path(h5_path), context)
    px_masks = np.asarray(side["arm_mask_px"], bool)
    grids = np.asarray(side["arm_grid_mask"], bool)
    ts_index = np.asarray(side["timestep_index"])
    total = int(side["attrs"]["num_frames"])
    if not (len(px_masks) == len(grids) == len(ts_index) == total):
        raise AssertionError(f"{context}: sidecar 内部帧数不自洽")

    out_path = Path(out_dir) / task / f"{name}.mp4"
    if out_path.exists() and not opts.overwrite:
        # 断点续跑：已存在即跳过。⚠ 模式②仍需逐帧误差供 worst 选段，跳过渲染但补算误差
        errors = _episode_errors(mode, h5_path, name, grids, ts_index) if mode == MODE_GENERATED else None
        return {
            "task": task,
            "episode": episode_index,
            "frames": total,
            "path": str(out_path),
            "skipped": True,
            "seconds": round(time.perf_counter() - started, 2),
            "frame_errors": errors,
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)

    layout = _layout_for(mode, opts.scale)
    template = render_static_chrome(mode, task, episode_index, layout)
    limit = opts.limit_frames or total
    frame_errors: list[list[int]] | None = [] if mode == MODE_GENERATED else None

    # ⚠ 临时名必须仍以 .mp4 结尾——imageio 靠扩展名挑 ffmpeg 后端
    tmp = out_path.with_name(out_path.stem + ".partial.mp4")
    with h5py.File(h5_path, "r") as handle:
        episode = handle[name]
        timestep_names = _sorted_numeric_names(episode, "timestep_")
        if len(timestep_names) != total:
            raise AssertionError(
                f"{context}: 源 h5 帧数 {len(timestep_names)} 与 sidecar {total} 不一致——"
                "sidecar 与数据集不是同批产物"
            )
        class_ids = class_ids_from_setup(episode["setup"]) if mode == MODE_GENERATED else None
        with _open_writer(tmp, opts) as writer:
            for t, (ts_name, rgb, is_demo, _is_completed) in enumerate(iter_frames(episode)):
                if t >= limit:
                    break
                if int(ts_name.removeprefix("timestep_")) != int(ts_index[t]):
                    raise AssertionError(f"{context}: timestep 主键错位 @ {t}")
                gt_labels = None
                if mode == MODE_GENERATED:
                    seg = _read_segmentation(episode, ts_name)
                    gt_labels = labels_from_segmentation(seg, class_ids)
                panels, grid_counts = _build_panels(
                    mode, rgb, px_masks[t], grids[t], gt_labels
                )
                if frame_errors is not None:
                    assert grid_counts is not None
                    frame_errors.append(
                        [frame_error(grid_counts), grid_counts.missed_arm, grid_counts.false_object]
                    )
                frame = compose_frame(
                    template, [_nearest(p, opts.scale) for p in panels], layout
                )
                _put_caption(
                    frame,
                    caption_lines(
                        task, episode_index, t, total,
                        "demo" if is_demo else "exec", grid_counts,
                    ),
                    layout,
                )
                writer.append_data(frame)
    os.replace(tmp, out_path)  # 原子落盘：半截文件永远不占正式名

    return {
        "task": task,
        "episode": episode_index,
        "frames": total,
        "path": str(out_path),
        "skipped": False,
        "seconds": round(time.perf_counter() - started, 2),
        "frame_errors": frame_errors,
    }


def _episode_errors(
    mode: str, h5_path: str, episode_name: str, grids: np.ndarray, ts_index: np.ndarray
) -> list[list[int]]:
    """跳过渲染时补算逐帧网格误差（worst 选段仍需要全量误差）。"""
    assert mode == MODE_GENERATED
    out: list[list[int]] = []
    with h5py.File(h5_path, "r") as handle:
        episode = handle[episode_name]
        class_ids = class_ids_from_setup(episode["setup"])
        names = _sorted_numeric_names(episode, "timestep_")
        if len(names) != len(grids):
            raise AssertionError(f"{episode_name}: 源帧数与 sidecar 不一致")
        for t, ts_name in enumerate(names):
            if int(ts_name.removeprefix("timestep_")) != int(ts_index[t]):
                raise AssertionError(f"{episode_name}: timestep 主键错位 @ {t}")
            gt = labels_from_segmentation(_read_segmentation(episode, ts_name), class_ids)
            counts = error_counts(upsample_grid(grids[t]), gt)
            out.append([frame_error(counts), counts.missed_arm, counts.false_object])
    return out


def render_worst_reel(
    segments: Sequence[Segment],
    h5_by_task: Mapping[str, str],
    sidecar_by_task: Mapping[str, str],
    reel_path: Path,
    opts: VideoOptions,
) -> int:
    """worst 合集（单进程串行）：段按峰值误差降序，段前中文标题卡，峰值帧画黄框，
    段间 2 帧黑帧。返回写出的总帧数。"""
    import cv2

    cv2.setNumThreads(1)

    layout = _layout_for(MODE_GENERATED, opts.scale)
    black = np.zeros((layout.height, layout.width, 3), np.uint8)
    title_frames = max(1, round(opts.fps * 0.6))
    written = 0
    reel_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = reel_path.with_name(reel_path.stem + ".partial.mp4")
    with _open_writer(tmp, opts) as writer:
        for rank, seg in enumerate(segments, start=1):
            card = render_title_card(
                layout,
                [
                    f"第 {rank}/{len(segments)} 名",
                    f"{seg.task} · episode_{seg.episode}",
                    f"峰值帧 {seg.peak_frame} · 误差 {seg.peak_error} px",
                ],
            )
            for _ in range(title_frames):
                writer.append_data(card)
                written += 1

            side = read_sidecar_episode(
                sidecar_by_task[seg.task], f"episode_{seg.episode}"
            )
            px_masks = np.asarray(side["arm_mask_px"], bool)
            grids = np.asarray(side["arm_grid_mask"], bool)
            total = int(side["attrs"]["num_frames"])
            template = render_static_chrome(MODE_GENERATED, seg.task, seg.episode, layout)
            with h5py.File(h5_by_task[seg.task], "r") as handle:
                episode = handle[f"episode_{seg.episode}"]
                class_ids = class_ids_from_setup(episode["setup"])
                for t in range(seg.start, seg.end + 1):
                    ts_name = f"timestep_{t}"
                    rgb = episode[ts_name]["obs"]["front_rgb"][()]
                    is_demo = bool(episode[ts_name]["info"]["is_video_demo"][()])
                    gt = labels_from_segmentation(
                        _read_segmentation(episode, ts_name), class_ids
                    )
                    panels, grid_counts = _build_panels(
                        MODE_GENERATED, rgb, px_masks[t], grids[t], gt
                    )
                    frame = compose_frame(
                        template, [_nearest(p, opts.scale) for p in panels], layout
                    )
                    _put_caption(
                        frame,
                        caption_lines(
                            seg.task, seg.episode, t, total,
                            "demo" if is_demo else "exec", grid_counts,
                            extra=f"rank {rank}/{len(segments)} peak={seg.peak_error}@{seg.peak_frame}",
                        ),
                        layout,
                    )
                    if t == seg.peak_frame:
                        b = PEAK_BORDER_PX
                        frame[:b, :] = PEAK_BORDER_COLOR
                        frame[-b:, :] = PEAK_BORDER_COLOR
                        frame[:, :b] = PEAK_BORDER_COLOR
                        frame[:, -b:] = PEAK_BORDER_COLOR
                    writer.append_data(frame)
                    written += 1
            writer.append_data(black)
            writer.append_data(black)
            written += 2
    os.replace(tmp, reel_path)
    return written


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE_ROOT,
        help="h5 数据源目录：官方备份（模式①）或自生带 GT 数据集（模式②）。始终只读",
    )
    parser.add_argument(
        "--sidecar-dir",
        default=None,
        help="make_mask 的 sidecar 目录；默认按模式取 outputs/arm_grid_mask_reference|generated",
    )
    parser.add_argument(
        "--mode",
        default="auto",
        choices=("auto", MODE_REFERENCE, MODE_GENERATED),
        help="auto 按源有无 GT segmentation 探测；显式 generated 但源无 GT 则报错",
    )
    parser.add_argument("--tasks", default="all", help="all 或逗号分隔任务名")
    parser.add_argument("--episodes", default="0-9")
    parser.add_argument(
        "--out-dir",
        default=str(SCRIPT_DIR / "outputs" / "videos"),
        help="视频输出根目录，实际落 <out-dir>/<reference|generated>/<Task>/episode_<i>.mp4",
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", type=int, default=8)
    parser.add_argument("--scale", type=int, default=1, help="面板最近邻整数倍放大")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--ffmpeg-threads", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true", help="重渲已存在的 mp4")
    parser.add_argument("--limit-frames", type=int, default=0, help="调试：每 episode 只出前 N 帧")
    parser.add_argument("--top-worst", type=int, default=None, help="worst 峰值帧数（默认 20，仅模式②）")
    parser.add_argument("--context-seconds", type=float, default=None, help="worst 段上下文秒数（默认 1.0）")
    parser.add_argument("--no-worst", action="store_true", help="不出 worst 合集（仅模式②有意义）")
    parser.add_argument("--worst-out", default=None, help="worst 合集 mp4 路径")
    parser.add_argument("--worst-json", default=None, help="worst 机读排名 JSON 路径")
    parser.add_argument("--json", default=None, help="运行统计 JSON 路径")
    args = parser.parse_args(argv)

    source_root = Path(args.source)
    all_paths = sorted(source_root.glob("record_dataset_*.h5"))
    if not all_paths:
        raise SystemExit(f"数据源目录没有 record_dataset_*.h5：{source_root}")
    if args.tasks != "all":
        wanted = {item.strip() for item in args.tasks.split(",") if item.strip()}
        paths = [p for p in all_paths if p.stem.replace("record_dataset_", "") in wanted]
        missing = wanted - {p.stem.replace("record_dataset_", "") for p in paths}
        if missing:
            raise SystemExit(f"找不到任务：{sorted(missing)}")
    else:
        paths = all_paths
    episodes = tuple(parse_episodes(args.episodes))

    source_has_gt = _source_has_ground_truth(paths[0], episodes[0])
    if args.mode == "auto":
        mode = MODE_GENERATED if source_has_gt else MODE_REFERENCE
    else:
        mode = args.mode
        if mode == MODE_GENERATED and not source_has_gt:
            raise SystemExit("--mode generated 但数据源没有 GT segmentation")

    worst_flags = {
        "--top-worst": args.top_worst,
        "--context-seconds": args.context_seconds,
        "--worst-out": args.worst_out,
        "--worst-json": args.worst_json,
    }
    if mode == MODE_REFERENCE:
        explicit = [flag for flag, value in worst_flags.items() if value is not None]
        if explicit:
            raise SystemExit(
                f"模式①（无 GT）不出 worst 合集，这些参数无意义：{explicit}"
            )
    top_worst = args.top_worst if args.top_worst is not None else 20
    context_seconds = args.context_seconds if args.context_seconds is not None else 1.0

    sidecar_dir = Path(
        args.sidecar_dir
        if args.sidecar_dir is not None
        else SCRIPT_DIR / "outputs" / f"arm_grid_mask_{mode}"
    )
    out_dir = Path(args.out_dir) / mode
    opts = VideoOptions(
        fps=args.fps,
        quality=args.quality,
        scale=args.scale,
        ffmpeg_threads=args.ffmpeg_threads,
        overwrite=args.overwrite,
        limit_frames=args.limit_frames,
    )

    h5_by_task: dict[str, str] = {}
    sidecar_by_task: dict[str, str] = {}
    jobs: list[tuple[str, str, int]] = []
    for path in paths:
        task = path.stem.replace("record_dataset_", "")
        sidecar = sidecar_dir / f"arm_grid_mask_{task}.h5"
        if not sidecar.exists():
            raise SystemExit(f"sidecar 不存在：{sidecar}（先跑 make_mask.py）")
        h5_by_task[task] = str(path)
        sidecar_by_task[task] = str(sidecar)
        for index in episodes:
            jobs.append((str(path), str(sidecar), index))

    print(
        f"视频渲染：模式{'②（带 GT，6 面板）' if mode == MODE_GENERATED else '①（无 GT，3 面板）'}，"
        f"{len(paths)} 任务 × episodes {sorted(episodes)} = {len(jobs)} 个视频，"
        f"并行 {args.workers} → {out_dir}"
    )
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                render_episode, mode, h5_path, sidecar_path, index, str(out_dir), opts
            ): (h5_path, index)
            for h5_path, sidecar_path, index in jobs
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            tag = "跳过（已存在）" if result["skipped"] else f"{result['seconds']}s"
            print(f"  {result['task']}/episode_{result['episode']}: {result['frames']} 帧，{tag}")
    results.sort(key=lambda item: (item["task"], item["episode"]))
    render_seconds = time.perf_counter() - started

    worst_summary: dict[str, Any] | None = None
    if mode == MODE_GENERATED and not args.no_worst:
        scores: list[FrameScore] = []
        lengths: dict[tuple[str, int], int] = {}
        for result in results:
            key = (result["task"], result["episode"])
            lengths[key] = result["frames"]
            for t, (err, missed, false_obj) in enumerate(result["frame_errors"]):
                scores.append(
                    FrameScore(result["task"], result["episode"], t, err, missed, false_obj)
                )
        context_frames = round(opts.fps * context_seconds)
        segments = select_worst_segments(scores, lengths, top_worst, context_frames)
        reel_path = Path(
            args.worst_out
            if args.worst_out is not None
            else out_dir / f"worst_top{top_worst}.mp4"
        )
        worst_json_path = Path(
            args.worst_json if args.worst_json is not None else out_dir / "worst.json"
        )
        if segments:
            reel_frames = render_worst_reel(
                segments, h5_by_task, sidecar_by_task, reel_path, opts
            )
        else:
            reel_frames = 0
            print("全部帧误差为 0，不出 worst 合集")
        ranked = sorted(
            (s for s in scores if s.error > 0),
            key=lambda s: (-s.error, s.task, s.episode, s.frame),
        )[:top_worst]
        worst_summary = {
            "口径": "逐帧误差 = 网格 mask 对 GT 的漏标臂像素 + 误涂物体像素（不含误涂背景）",
            "参数": {
                "top_worst": top_worst,
                "context_seconds": context_seconds,
                "context_frames": context_frames,
                "fps": opts.fps,
            },
            "帧排名": [
                {
                    "rank": rank,
                    "task": s.task,
                    "episode": s.episode,
                    "frame": s.frame,
                    "error": s.error,
                    "missed_arm": s.missed_arm,
                    "false_object": s.false_object,
                }
                for rank, s in enumerate(ranked, start=1)
            ],
            "段": [
                {
                    "rank": rank,
                    "task": seg.task,
                    "episode": seg.episode,
                    "start": seg.start,
                    "end": seg.end,
                    "frames": seg.end - seg.start + 1,
                    "peak_frame": seg.peak_frame,
                    "peak_error": seg.peak_error,
                    "merged_peaks": list(seg.merged_peaks),
                }
                for rank, seg in enumerate(segments, start=1)
            ],
            "reel": str(reel_path) if segments else None,
            "reel_frames": reel_frames,
        }
        worst_json_path.parent.mkdir(parents=True, exist_ok=True)
        worst_json_path.write_text(
            json.dumps(worst_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if segments:
            print(f"worst 合集：{len(segments)} 段 / {reel_frames} 帧 → {reel_path}")

    summary = {
        "mode": mode,
        "source": str(source_root),
        "sidecar_dir": str(sidecar_dir),
        "out_dir": str(out_dir),
        "num_videos": len(results),
        "num_skipped": sum(1 for r in results if r["skipped"]),
        "total_frames": sum(r["frames"] for r in results),
        "render_seconds": round(render_seconds, 1),
        "fps": opts.fps,
        "scale": opts.scale,
        "generated_at_iso": datetime.now(tz=timezone.utc).isoformat(),
        "per_episode": [
            {k: r[k] for k in ("task", "episode", "frames", "path", "skipped", "seconds")}
            for r in results
        ],
    }
    json_path = Path(args.json if args.json is not None else out_dir / "make_videos.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"完成：{summary['num_videos']} 个视频（跳过 {summary['num_skipped']}），"
        f"共 {summary['total_frames']} 帧，耗时 {summary['render_seconds']}s → {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
