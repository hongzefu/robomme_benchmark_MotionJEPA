#!/usr/bin/env python3
"""导出纯 CV arm mask 的目视检查图。

输入可以是 v2 产物：脚本只读取 ``front_rgb`` / ``front_depth``，不会复用 v2 已经删除桌面的
``front_rgb_masked``。支持两种输出：

1. 默认三列概览：原图 / 半透明 arm mask / 背景补洞结果，保持既有行为；
2. ``--contact-sheet``：按 ``--temporal-stride`` 在时间轴抽帧并强制保留末帧，每个保留帧只把
   arm mask 内像素写成纯红 ``(255, 0, 0)``，其余原始像素逐位不变，再按时间顺序平铺成一张图。

两种模式都先对完整 episode 计算 CV mask，不能先抽帧再检测，否则会改变 episode 级桌面平面拟合。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

import cv2
import h5py
import numpy as np

from cv_arm_removal import remove_robot_arm_sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "flow-viz" / "v3.1-codex-preview"
DEFAULT_CONTACT_OUTPUT_DIR = (
    SCRIPT_DIR / "products" / "temporal4-red-mask-contact-sheets"
)
SCALE = 2
LABEL_HEIGHT = 22
GAP = 6
CONTACT_COLUMNS = 8
MASK_RED_RGB = np.asarray((255, 0, 0), dtype=np.uint8)


def _timestep_names(episode_group: h5py.Group) -> list[str]:
    named: list[tuple[int, str]] = []
    for name in episode_group.keys():
        if name.startswith("timestep_") and name[len("timestep_") :].isdigit():
            named.append((int(name[len("timestep_") :]), name))
    named.sort()
    return [name for _, name in named]


def _pick_positions(length: int, count: int) -> list[int]:
    if length <= 0:
        return []
    if length <= count:
        return list(range(length))
    return list(dict.fromkeys(np.linspace(0, length - 1, count).round().astype(int)))


def _temporal_positions(length: int, stride: int) -> list[int]:
    """返回 ``0,stride,2*stride,...,末帧``，末帧只出现一次。"""
    if stride < 1:
        raise ValueError(f"temporal_stride 必须 ≥ 1，收到 {stride}")
    if length <= 0:
        return []
    positions = list(range(0, length, stride))
    if positions[-1] != length - 1:
        positions.append(length - 1)
    return positions


def _to_bgr(rgb: np.ndarray) -> np.ndarray:
    scaled = cv2.resize(
        rgb, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST
    )
    return cv2.cvtColor(scaled, cv2.COLOR_RGB2BGR)


def _to_bgr_original(rgb: np.ndarray) -> np.ndarray:
    """保持 256×256 原始空间分辨率，只做 RGB→BGR 通道转换。"""
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _label(image: np.ndarray, text: str) -> np.ndarray:
    height, width = image.shape[:2]
    canvas = np.full((height + LABEL_HEIGHT, width, 3), 24, dtype=np.uint8)
    canvas[LABEL_HEIGHT:] = image
    cv2.putText(
        canvas,
        text[:56],
        (4, LABEL_HEIGHT - 7),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _mask_overlay(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    overlay = rgb.copy()
    overlay[mask] = np.asarray((255, 40, 40), dtype=np.uint8)
    return np.where(mask[..., None], (0.30 * rgb + 0.70 * overlay).astype(np.uint8), rgb)


def _load_episode_rgbd(
    h5_path: Path, episode: int
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """从只读 h5 载入一个完整 episode 的原始 RGB-D。"""
    with h5py.File(h5_path, "r") as handle:
        episode_name = f"episode_{episode}"
        if episode_name not in handle:
            raise KeyError(f"{h5_path.name} 里没有 {episode_name}")
        episode_group = handle[episode_name]
        names = _timestep_names(episode_group)
        if not names:
            raise ValueError(f"{h5_path.name} 的 {episode_name} 一个 timestep 都没有")

        rgb_frames: list[np.ndarray] = []
        depth_frames: list[np.ndarray] = []
        for name in names:
            obs = episode_group[name]["obs"]
            for required in ("front_rgb", "front_depth"):
                if required not in obs:
                    raise KeyError(f"{h5_path.name}/{episode_name}/{name} 缺少 {required}")
            rgb_frames.append(np.asarray(obs["front_rgb"][()], dtype=np.uint8))
            depth_frames.append(np.asarray(obs["front_depth"][()]))
    return names, np.stack(rgb_frames, axis=0), np.stack(depth_frames, axis=0)


def _paint_mask_red(original: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """仅把删除像素设为纯红；mask 外原始像素逐位不变。"""
    frame = np.asarray(original)
    mask_array = np.asarray(mask, dtype=bool)
    if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[-1] != 3:
        raise ValueError(f"原图必须是 uint8 [H,W,3]，收到 {frame.shape}/{frame.dtype}")
    if mask_array.shape != frame.shape[:2]:
        raise ValueError(f"mask 与原图分辨率不一致：{mask_array.shape} vs {frame.shape[:2]}")
    output = frame.copy()
    output[mask_array] = MASK_RED_RGB
    if not np.array_equal(output[~mask_array], frame[~mask_array]):
        raise ValueError("纯红遮罩改写了 mask 外原始像素")
    if np.any(mask_array) and not np.all(output[mask_array] == MASK_RED_RGB):
        raise ValueError("删除像素没有全部写成纯红 (255, 0, 0)")
    return output


def build_preview(
    h5_path: Path, episode: int, frames: int
) -> tuple[np.ndarray, dict[str, Any]]:
    """计算完整 episode，再拼出原图/掩码/结果三列网格。"""
    names, rgb_stack, depth_stack = _load_episode_rgbd(h5_path, episode)
    result = remove_robot_arm_sequence(rgb_stack, depth_stack)
    removed = np.asarray(result.frames, dtype=np.uint8)
    masks = np.asarray(result.masks, dtype=bool)
    if not np.array_equal(removed[~masks], rgb_stack[~masks]):
        raise ValueError("去臂算法改写了 mask 外像素")

    rows: list[np.ndarray] = []
    for position in _pick_positions(len(names), frames):
        index = int(names[position][len("timestep_") :])
        panels = (
            _label(_to_bgr(rgb_stack[position]), f"t={index} front_rgb"),
            _label(
                _to_bgr(_mask_overlay(rgb_stack[position], masks[position])),
                f"t={index} cv_arm_mask",
            ),
            _label(_to_bgr(removed[position]), f"t={index} arm_removed"),
        )
        spacer = np.full((panels[0].shape[0], GAP, 3), 24, dtype=np.uint8)
        rows.append(np.hstack([panels[0], spacer, panels[1], spacer, panels[2]]))

    width = max(row.shape[1] for row in rows)
    separated: list[np.ndarray] = []
    for row in rows:
        separated.append(row)
        separated.append(np.full((GAP, width, 3), 24, dtype=np.uint8))
    grid = np.vstack(separated[:-1])
    summary = dict(result.stats)
    summary.update(
        {
            "frame_count": len(names),
            "masked_pixels": int(masks.sum()),
            "masked_fraction": float(masks.mean()),
        }
    )
    return grid, summary


def build_red_mask_contact_sheet(
    h5_path: Path,
    episode: int,
    temporal_stride: int,
    columns: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """把时序抽稀后的纯红删除图按时间顺序平铺成一张 episode contact sheet。"""
    if columns < 1:
        raise ValueError(f"columns 必须 ≥ 1，收到 {columns}")
    names, rgb_stack, depth_stack = _load_episode_rgbd(h5_path, episode)

    # 必须用完整 episode 检测 mask；这里只取 masks，绝不使用背景填充后的 result.frames。
    result = remove_robot_arm_sequence(rgb_stack, depth_stack)
    masks = np.asarray(result.masks, dtype=bool)
    cv_stats = result.stats
    if masks.shape != rgb_stack.shape[:3]:
        raise ValueError(f"CV mask shape 非法：{masks.shape}，期望 {rgb_stack.shape[:3]}")
    # contact sheet 不使用背景图与填充结果，尽早释放这两块完整时序数组，压低长 episode 峰值内存。
    del result

    positions = _temporal_positions(len(names), temporal_stride)
    if not positions:
        raise ValueError("时序抽稀后没有任何帧")

    tiles: list[np.ndarray] = []
    selected_mask_pixels = 0
    selected_mask_total = 0
    retained_timesteps: list[int] = []
    for position in positions:
        source_timestep = int(names[position][len("timestep_") :])
        retained_timesteps.append(source_timestep)
        mask = masks[position]
        red_frame = _paint_mask_red(rgb_stack[position], mask)
        selected_mask_pixels += int(np.count_nonzero(mask))
        selected_mask_total += int(mask.size)
        tiles.append(
            _label(
                _to_bgr_original(red_frame),
                f"source t={source_timestep} deleted=red",
            )
        )

    tile_height, tile_width = tiles[0].shape[:2]
    blank = np.full((tile_height, tile_width, 3), 24, dtype=np.uint8)
    rows: list[np.ndarray] = []
    for start in range(0, len(tiles), columns):
        cells = tiles[start : start + columns]
        cells.extend([blank] * (columns - len(cells)))
        row_parts: list[np.ndarray] = []
        for cell_index, cell in enumerate(cells):
            if cell_index:
                row_parts.append(np.full((tile_height, GAP, 3), 24, dtype=np.uint8))
            row_parts.append(cell)
        rows.append(np.hstack(row_parts))

    sheet_width = rows[0].shape[1]
    separated: list[np.ndarray] = []
    for row_index, row in enumerate(rows):
        if row_index:
            separated.append(np.full((GAP, sheet_width, 3), 24, dtype=np.uint8))
        separated.append(row)
    body = np.vstack(separated)

    header_height = 34
    header = np.full((header_height, sheet_width, 3), 18, dtype=np.uint8)
    cv2.putText(
        header,
        f"{h5_path.stem} ep={episode} | temporal stride={temporal_stride} | "
        f"source={len(names)} | kept={len(positions)} | deleted pixels=red",
        (8, 23),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )
    sheet = np.vstack([header, np.full((GAP, sheet_width, 3), 24, dtype=np.uint8), body])
    summary = {
        "source_frame_count": len(names),
        "temporal_stride": int(temporal_stride),
        "retained_frame_count": len(positions),
        "retained_source_timesteps": retained_timesteps,
        "first_source_timestep": retained_timesteps[0],
        "last_source_timestep": retained_timesteps[-1],
        "selected_mask_pixels": selected_mask_pixels,
        "selected_mask_fraction": (
            float(selected_mask_pixels / selected_mask_total) if selected_mask_total else 0.0
        ),
        "mask_inside_color_rgb": [int(item) for item in MASK_RED_RGB],
        "mask_outside_bitwise_unchanged": True,
        "background_fill_used": False,
        "columns": int(columns),
        "sheet_height": int(sheet.shape[0]),
        "sheet_width": int(sheet.shape[1]),
        "cv_stats": cv_stats,
    }
    return sheet, summary


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出纯 CV 去机械臂三列目视检查图")
    parser.add_argument("--h5", nargs="+", required=True, help="待检查 h5，可传多个")
    parser.add_argument("--episode", type=int, default=0, help="默认只检查 episode 0")
    parser.add_argument("--frames", type=int, default=8, help="每任务均匀抽帧数")
    parser.add_argument(
        "--contact-sheet",
        action="store_true",
        help="输出时序抽稀后的纯红删除图 contact sheet；不输出三列背景补洞概览",
    )
    parser.add_argument(
        "--temporal-stride",
        type=int,
        default=4,
        help="contact sheet 的时序降采样步长；保留 0,N,2N,...,末帧（默认 %(default)s）",
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=CONTACT_COLUMNS,
        help="contact sheet 每行平铺多少帧（默认 %(default)s）",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="图片输出目录；三列概览默认写 artifacts，contact sheet 默认写脚本目录内 products/",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    default_output = (
        DEFAULT_CONTACT_OUTPUT_DIR if namespace.contact_sheet else DEFAULT_OUTPUT_DIR
    )
    output_dir = Path(namespace.output_dir or default_output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for raw in namespace.h5:
        h5_path = Path(raw).expanduser().resolve()
        try:
            if namespace.contact_sheet:
                grid, summary = build_red_mask_contact_sheet(
                    h5_path,
                    namespace.episode,
                    namespace.temporal_stride,
                    namespace.columns,
                )
            else:
                grid, summary = build_preview(h5_path, namespace.episode, namespace.frames)
        except Exception as exc:
            print(f"✗ {h5_path.name}: {exc}", flush=True)
            failures += 1
            continue
        suffix = (
            f"temporal{namespace.temporal_stride}_red-mask-contact-sheet"
            if namespace.contact_sheet
            else "cv-arm-removed"
        )
        target = output_dir / f"{h5_path.stem}_ep{namespace.episode}_{suffix}.png"
        if not cv2.imwrite(str(target), grid):
            print(f"✗ {h5_path.name}: 写图失败 {target}", flush=True)
            failures += 1
            continue
        if namespace.contact_sheet:
            print(
                f"✓ {h5_path.name}: 源 {summary['source_frame_count']} 帧，"
                f"时序步长 {summary['temporal_stride']} 保留 "
                f"{summary['retained_frame_count']} 帧，纯红 mask 占比 "
                f"{summary['selected_mask_fraction']:.2%}，"
                f"拼图 {summary['sheet_width']}x{summary['sheet_height']} → {target}",
                flush=True,
            )
        else:
            print(
                f"✓ {h5_path.name}: {summary['frame_count']} 帧，"
                f"mask 占比 {summary['masked_fraction']:.2%} → {target}",
                flush=True,
            )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
