#!/usr/bin/env python3
"""导出原图、纯 CV arm mask 与去臂结果三列网格，供逐任务目视检查。

输入可以是 v2 产物：脚本只读取 ``front_rgb`` / ``front_depth``，不会复用 v2 已经删除桌面的
``front_rgb_masked``。整段 episode 先统一估计时序背景，再均匀抽帧展示。
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
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "flow-viz" / "v3-codex-preview"
SCALE = 2
LABEL_HEIGHT = 22
GAP = 6


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


def _to_bgr(rgb: np.ndarray) -> np.ndarray:
    scaled = cv2.resize(
        rgb, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST
    )
    return cv2.cvtColor(scaled, cv2.COLOR_RGB2BGR)


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


def build_preview(
    h5_path: Path, episode: int, frames: int
) -> tuple[np.ndarray, dict[str, Any]]:
    """计算完整 episode，再拼出原图/掩码/结果三列网格。"""
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

    rgb_stack = np.stack(rgb_frames, axis=0)
    result = remove_robot_arm_sequence(
        rgb_stack, np.stack(depth_frames, axis=0)
    )
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


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出纯 CV 去机械臂三列目视检查图")
    parser.add_argument("--h5", nargs="+", required=True, help="待检查 h5，可传多个")
    parser.add_argument("--episode", type=int, default=0, help="默认只检查 episode 0")
    parser.add_argument("--frames", type=int, default=8, help="每任务均匀抽帧数")
    parser.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="图片输出目录"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    output_dir = Path(namespace.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for raw in namespace.h5:
        h5_path = Path(raw).expanduser().resolve()
        try:
            grid, summary = build_preview(h5_path, namespace.episode, namespace.frames)
        except Exception as exc:
            print(f"✗ {h5_path.name}: {exc}", flush=True)
            failures += 1
            continue
        target = output_dir / f"{h5_path.stem}_ep{namespace.episode}_cv-arm-removed.png"
        if not cv2.imwrite(str(target), grid):
            print(f"✗ {h5_path.name}: 写图失败 {target}", flush=True)
            failures += 1
            continue
        print(
            f"✓ {h5_path.name}: {summary['frame_count']} 帧，"
            f"mask 占比 {summary['masked_fraction']:.2%} → {target}",
            flush=True,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
