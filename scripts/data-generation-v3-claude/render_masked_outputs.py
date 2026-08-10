#!/usr/bin/env python3
"""读现成 h5 的 ``front_rgb``，跑纯 CV 删臂，输出红遮罩可视化产物。

本脚本是 v3-claude 链路的唯一入口：**不重新仿真、不写 h5**（用户口径：只要可视化
产物），直接消费 ``artifacts/generated/v21-16env`` 里已生成的 16 任务 × episode_0。

产物（默认写到本目录 ``outputs/`` 下，用户口径：产物放脚本目录内部）：

- ``<Task>_ep0_preview.png``：均匀抽帧的三联网格——原图 | 红遮罩图 | 纯 mask 图
  （白=删除），2 倍放大供细看。第三联是必须的：红遮罩与画面里的红色任务物体
  撞色，只看第二联分不清「这块红是遮罩还是方块」。
- ``<Task>_ep0_grid.png``：**全部抽样帧**的红遮罩图网格拼接大图（每行 8 帧、
  原始分辨率），用于看时间上的稳定性（碎片闪烁、阴影抖动）。用户口径：输出
  不以视频形式、而是拼接图片——本图就是视频的替代品。
- ``summary.json``：逐任务 stats + 生效参数 + 底座区 bbox 跨任务一致性检查
  （16 任务同一机器人同一相机，bbox 不一致就是底座检测失效的红灯）。

时序口径（用户拍板）：**时序降采样 4 倍**——按 timestep 顺序每 4 帧取 1 帧
（t=0,4,8,…），CV 处理与全部产物都基于抽帧后的序列；空间分辨率保持 256×256。

图上标注不写中文：OpenCV 的 Hershey 字体渲染不了中文。标注一律 ASCII
（写法沿用 v2 ``export_masked_preview.py``，拷代码不 import——v2/v3 独立演进）。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - 环境问题应当直接暴露
    raise SystemExit(f"需要 opencv：{exc}")

from arm_removal import ArmRemovalParams, apply_red_mask, compute_arm_masks

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PARAMS_PATH = SCRIPT_DIR / "arm_removal_params.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "outputs"

# 单块图放大倍数：256×256 原图太小，看不清碎片与边缘
SCALE = 2
LABEL_HEIGHT = 22
GAP = 6
# 全帧网格拼图每行帧数（原始分辨率 256，8 帧一行拼出 2 千像素宽，PNG 可控）
GRID_COLUMNS = 8


def _timestep_indices(episode_group: h5py.Group) -> list[int]:
    indices: list[int] = []
    for name in episode_group.keys():
        if name.startswith("timestep_") and name[len("timestep_") :].isdigit():
            indices.append(int(name[len("timestep_") :]))
    return sorted(indices)


def _pick_positions(count: int, want: int) -> list[int]:
    """在 0..count-1 上均匀取 want 个位置，保证首尾都在。"""
    if count <= want:
        return list(range(count))
    positions = np.linspace(0, count - 1, want).round().astype(int)
    picked: list[int] = []
    for position in positions:
        if int(position) not in picked:
            picked.append(int(position))
    return picked


def _label(image: np.ndarray, text: str) -> np.ndarray:
    height, width = image.shape[:2]
    canvas = np.full((height + LABEL_HEIGHT, width, 3), 24, dtype=np.uint8)
    canvas[LABEL_HEIGHT:] = image
    cv2.putText(
        canvas,
        text[:48],
        (4, LABEL_HEIGHT - 7),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _to_bgr(rgb: np.ndarray) -> np.ndarray:
    scaled = cv2.resize(rgb, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(scaled, cv2.COLOR_RGB2BGR)


def _mask_to_bgr(mask: np.ndarray) -> np.ndarray:
    gray = (mask.astype(np.uint8)) * 255
    scaled = cv2.resize(gray, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(scaled, cv2.COLOR_GRAY2BGR)


def load_episode(
    h5_path: Path, episode: int, temporal_stride: int
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """按时序降采样读一个 episode。返回 (frames, phase_flags, 抽中的 timestep 编号)。"""
    with h5py.File(h5_path, "r") as handle:
        episode_name = f"episode_{episode}"
        if episode_name not in handle:
            raise KeyError(f"{h5_path.name} 里没有 {episode_name}")
        episode_group = handle[episode_name]
        indices = _timestep_indices(episode_group)
        if not indices:
            raise ValueError(f"{h5_path.name} 的 {episode_name} 一个 timestep 都没有")
        picked = indices[::temporal_stride]
        frames = np.empty((len(picked), 256, 256, 3), dtype=np.uint8)
        phase = np.zeros(len(picked), dtype=bool)
        for row, index in enumerate(picked):
            timestep = episode_group[f"timestep_{index}"]
            frames[row] = timestep["obs"]["front_rgb"][()]
            info = timestep.get("info")
            if info is not None and "is_video_demo" in info:
                phase[row] = bool(info["is_video_demo"][()])
    return frames, phase, picked


def build_preview_grid(
    frames: np.ndarray,
    red_frames: np.ndarray,
    masks: np.ndarray,
    picked_timesteps: list[int],
    preview_frames: int,
) -> np.ndarray:
    """三联网格：原图 | 红遮罩图 | 纯 mask（白=删除）。行为均匀抽帧。"""
    rows: list[np.ndarray] = []
    for position in _pick_positions(frames.shape[0], preview_frames):
        t = picked_timesteps[position]
        left = _label(_to_bgr(frames[position]), f"t={t} front_rgb")
        middle = _label(_to_bgr(red_frames[position]), f"t={t} red_masked")
        right = _label(_mask_to_bgr(masks[position]), f"t={t} mask(white=removed)")
        spacer = np.full((left.shape[0], GAP, 3), 24, dtype=np.uint8)
        rows.append(np.hstack([left, spacer, middle, spacer, right]))
    grid_rows: list[np.ndarray] = []
    for row in rows:
        grid_rows.append(row)
        grid_rows.append(np.full((GAP, row.shape[1], 3), 24, dtype=np.uint8))
    return np.vstack(grid_rows[:-1])


def build_frame_grid(red_frames: np.ndarray, picked_timesteps: list[int]) -> np.ndarray:
    """全部抽样帧的红遮罩图网格拼接大图（视频的替代品，用户口径：输出用拼接图片）。

    每行 ``GRID_COLUMNS`` 帧、原始分辨率、每帧带 t 标注，按时间行优先排布。
    """
    tiles: list[np.ndarray] = []
    for position in range(red_frames.shape[0]):
        bgr = cv2.cvtColor(red_frames[position], cv2.COLOR_RGB2BGR)
        tiles.append(_label(bgr, f"t={picked_timesteps[position]}"))
    tile_h, tile_w = tiles[0].shape[:2]
    blank = np.full((tile_h, tile_w, 3), 24, dtype=np.uint8)
    rows: list[np.ndarray] = []
    for start in range(0, len(tiles), GRID_COLUMNS):
        chunk = tiles[start : start + GRID_COLUMNS]
        chunk.extend([blank] * (GRID_COLUMNS - len(chunk)))
        cells: list[np.ndarray] = []
        for tile in chunk:
            cells.append(tile)
            cells.append(np.full((tile_h, GAP, 3), 24, dtype=np.uint8))
        rows.append(np.hstack(cells[:-1]))
        rows.append(np.full((GAP, rows[-1].shape[1], 3), 24, dtype=np.uint8))
    return np.vstack(rows[:-1])


def _first_ok_bbox(stats: dict[str, Any]) -> list[int] | None:
    for segment in stats["segments"]:
        occluder = segment["static_occluder"]
        if occluder["status"] == "ok":
            return occluder["bbox"]
    return None


def check_bbox_consistency(per_task: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """16 任务同一机器人同一相机，底座 bbox 必须一致（行列偏差 ≤2px 视为通过）。"""
    bboxes = {task: _first_ok_bbox(stats) for task, stats in per_task.items()}
    detected = {task: bbox for task, bbox in bboxes.items() if bbox is not None}
    result: dict[str, Any] = {
        "bbox_per_task": bboxes,
        "tasks_without_detection": sorted(set(bboxes) - set(detected)),
    }
    if len(detected) >= 2:
        arr = np.array(list(detected.values()))
        deviation = int((arr.max(axis=0) - arr.min(axis=0)).max())
        result["max_deviation_px"] = deviation
        result["consistent_within_2px"] = bool(deviation <= 2)
    return result


def _parse_overrides(pairs: Sequence[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set 参数必须是 k=v 形式：{pair}")
        key, raw = pair.split("=", 1)
        overrides[key.strip()] = json.loads(raw) if raw not in ("", "null") else None
    return overrides


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纯 CV 删臂红遮罩可视化（读现成 h5，不写 h5）")
    parser.add_argument("--h5", nargs="+", required=True, help="输入 h5 文件，可传多个/通配")
    parser.add_argument("--episode", type=int, default=0, help="处理哪个 episode，默认 0")
    parser.add_argument("--temporal-stride", type=int, default=4, help="时序降采样步长，默认 4")
    parser.add_argument("--frames", type=int, default=6, help="预览图抽几帧，默认 6")
    parser.add_argument("--params", default=str(DEFAULT_PARAMS_PATH), help="参数 json（唯一真源）")
    parser.add_argument("--set", action="append", default=[], metavar="K=V",
                        help="覆写单个参数（JSON 字面量），可重复")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help=f"产物目录，默认 {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--no-grid", action="store_true", help="只出三联预览图，不出全帧网格拼图")
    parser.add_argument("--write-back", action="store_true",
                        help="把生效参数写回 --params 文件（调参收敛后使用）")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    params_path = Path(namespace.params).expanduser().resolve()
    base = json.loads(params_path.read_text(encoding="utf-8"))
    base.update(_parse_overrides(namespace.set))
    params = ArmRemovalParams.from_dict(base)

    output_dir = Path(namespace.output_dir).expanduser().resolve()
    generated_root = (SCRIPT_DIR.parents[1] / "artifacts" / "generated").resolve()
    if generated_root == output_dir or generated_root in output_dir.parents:
        raise SystemExit(f"产物目录不得位于 {generated_root} 之下（那里只放生成链路的正式 h5 产物）")
    output_dir.mkdir(parents=True, exist_ok=True)

    per_task: dict[str, dict[str, Any]] = {}
    failures = 0
    for raw in namespace.h5:
        h5_path = Path(raw).expanduser().resolve()
        task = h5_path.stem.removeprefix("record_dataset_")
        started = time.perf_counter()
        try:
            frames, phase, picked = load_episode(h5_path, namespace.episode, namespace.temporal_stride)
            masks, stats = compute_arm_masks(frames, phase, params)
            red_frames = apply_red_mask(frames, masks)

            preview = build_preview_grid(frames, red_frames, masks, picked, namespace.frames)
            preview_path = output_dir / f"{task}_ep{namespace.episode}_preview.png"
            cv2.imwrite(str(preview_path), preview)
            if not namespace.no_grid:
                grid = build_frame_grid(red_frames, picked)
                cv2.imwrite(str(output_dir / f"{task}_ep{namespace.episode}_grid.png"), grid)
        except Exception as exc:
            print(f"✗ {task}: {exc}", flush=True)
            failures += 1
            continue
        stats["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        stats["source_h5"] = str(h5_path)
        stats["temporal_stride"] = namespace.temporal_stride
        per_task[task] = stats
        bbox = _first_ok_bbox(stats)
        print(
            f"✓ {task}: {stats['frame_count']} 帧（stride={namespace.temporal_stride}）"
            f"，{stats['segment_count']} 段，删除占比均值 {stats['removed_fraction_mean']:.3f}"
            f"，底座 bbox {bbox}，耗时 {stats['elapsed_seconds']}s",
            flush=True,
        )

    summary = {
        "params": params.to_dict(),
        "episode": namespace.episode,
        "temporal_stride": namespace.temporal_stride,
        "tasks": per_task,
        "static_occluder_consistency": check_bbox_consistency(per_task) if per_task else {},
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsummary 已写到 {summary_path}", flush=True)

    if namespace.write_back:
        params_path.write_text(
            json.dumps(params.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"生效参数已写回 {params_path}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
