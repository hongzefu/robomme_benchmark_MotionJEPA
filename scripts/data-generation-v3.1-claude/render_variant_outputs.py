#!/usr/bin/env python3
"""v3.1 变体统一渲染入口：读现成 h5 的 ``front_rgb``，跑指定变体，出红遮罩可视化。

与 v3 的渲染器同源，差异只有三点：

1. **变体插件**：``--variant <name>`` 按名字加载 ``variants/<name>.py``（契约见
   ``variants/__init__.py``），各变体互不冲突、可并行跑；
2. **黑指尖可视化**：变体返回的 ``tip_masks``（保留的黑指尖）在第三联 mask 图里
   画成**绿色**（白=删除、绿=指尖保留、黑=未动），红遮罩图里指尖保持原像素；
3. **物体误删 tripwire**：summary 里逐任务记录 ``red_on_saturated_pixels``
   （删除 mask 与原图高饱和 S≥60 像素的交集计数，均值/最大）——彩色任务物体被
   误删时该值会显著升高，作为目视核查之外的廉价红灯（无彩物体它测不到，白缆线、
   白按钮仍要靠目视）。

产物写到 ``outputs/<variant>/``：``<Task>_ep0_preview.png``（原图 | 红遮罩 | mask
三联，均匀抽帧）、``<Task>_ep0_grid.png``（全部抽样帧红遮罩网格拼图，时序稳定性
判读用，单张可达数十 MB 不入 git）、``summary.json``。

时序口径与 v3 相同：时序降采样 4 倍（t=0,4,8,…），空间 256×256。
图上标注不写中文（OpenCV Hershey 字体渲染不了中文），一律 ASCII。
"""

from __future__ import annotations

import argparse
import importlib.util
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

SCRIPT_DIR = Path(__file__).resolve().parent
VARIANTS_DIR = SCRIPT_DIR / "variants"
DEFAULT_OUTPUT_ROOT = SCRIPT_DIR / "outputs"

# 单块图放大倍数：256×256 原图太小，看不清碎片与指尖
SCALE = 2
LABEL_HEIGHT = 22
GAP = 6
# 全帧网格拼图每行帧数
GRID_COLUMNS = 8
# tripwire 的高饱和阈值（OpenCV S 域 0–255），与 v3 protect 的默认阈值一致
TRIPWIRE_SAT_MIN = 60

RED = np.array([255, 0, 0], dtype=np.uint8)


def load_variant(name: str):
    """按名字加载变体模块并校验契约三要素。"""
    path = VARIANTS_DIR / f"{name}.py"
    if not path.is_file():
        available = sorted(p.stem for p in VARIANTS_DIR.glob("*.py") if p.stem != "__init__")
        raise SystemExit(f"找不到变体 {name}（{path}）。现有变体：{available}")
    spec = importlib.util.spec_from_file_location(f"v31_variant_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in ("NAME", "DESCRIPTION", "compute_masks"):
        if not hasattr(module, attr):
            raise SystemExit(f"变体 {name} 缺少契约属性 {attr}（见 variants/__init__.py）")
    if module.NAME != name:
        raise SystemExit(f"变体 {name} 的 NAME={module.NAME!r} 与文件名不符")
    return module


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


def _mask_to_bgr(remove: np.ndarray, tip: np.ndarray) -> np.ndarray:
    """mask 三色图：白=删除、绿=指尖保留、黑=未动。"""
    canvas = np.zeros((*remove.shape, 3), dtype=np.uint8)
    canvas[remove] = (255, 255, 255)
    canvas[tip] = (0, 200, 0)  # BGR 下的绿
    return cv2.resize(canvas, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)


def apply_red_mask(frames: np.ndarray, masks: np.ndarray) -> np.ndarray:
    """mask 处涂纯红 (255,0,0)，其余像素（含指尖）与输入逐位相同。绝不就地改。"""
    out = frames.copy()
    out[masks] = RED
    return out


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
    remove_masks: np.ndarray,
    tip_masks: np.ndarray,
    picked_timesteps: list[int],
    preview_frames: int,
) -> np.ndarray:
    """三联网格：原图 | 红遮罩图 | mask（白=删除、绿=指尖保留）。行为均匀抽帧。"""
    rows: list[np.ndarray] = []
    for position in _pick_positions(frames.shape[0], preview_frames):
        t = picked_timesteps[position]
        left = _label(_to_bgr(frames[position]), f"t={t} front_rgb")
        middle = _label(_to_bgr(red_frames[position]), f"t={t} red_masked")
        right = _label(
            _mask_to_bgr(remove_masks[position], tip_masks[position]),
            f"t={t} mask(white=rm green=tip)",
        )
        spacer = np.full((left.shape[0], GAP, 3), 24, dtype=np.uint8)
        rows.append(np.hstack([left, spacer, middle, spacer, right]))
    grid_rows: list[np.ndarray] = []
    for row in rows:
        grid_rows.append(row)
        grid_rows.append(np.full((GAP, row.shape[1], 3), 24, dtype=np.uint8))
    return np.vstack(grid_rows[:-1])


def build_frame_grid(red_frames: np.ndarray, picked_timesteps: list[int]) -> np.ndarray:
    """全部抽样帧的红遮罩图网格拼接大图（视频的替代品）。"""
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


def tripwire_stats(
    frames: np.ndarray, remove_masks: np.ndarray, tip_masks: np.ndarray
) -> dict[str, Any]:
    """物体误删红灯（只测得到彩色物体）+ 指尖像素计数。"""
    red_on_sat: list[int] = []
    tip_pixels: list[int] = []
    for index in range(frames.shape[0]):
        hsv = cv2.cvtColor(frames[index], cv2.COLOR_RGB2HSV)
        red_on_sat.append(int((remove_masks[index] & (hsv[..., 1] >= TRIPWIRE_SAT_MIN)).sum()))
        tip_pixels.append(int(tip_masks[index].sum()))
    return {
        "red_on_saturated_mean": float(np.mean(red_on_sat)),
        "red_on_saturated_max": int(np.max(red_on_sat)),
        "red_on_saturated_argmax": int(np.argmax(red_on_sat)),
        "tip_pixels_mean": float(np.mean(tip_pixels)),
        "tip_pixels_max": int(np.max(tip_pixels)),
        "tip_frames_nonzero": int(np.count_nonzero(tip_pixels)),
    }


def _parse_overrides(pairs: Sequence[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set 参数必须是 k=v 形式：{pair}")
        key, raw = pair.split("=", 1)
        overrides[key.strip()] = json.loads(raw) if raw not in ("", "null") else None
    return overrides


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v3.1 变体统一渲染入口（读现成 h5，不写 h5）")
    parser.add_argument("--variant", required=True, help="variants/ 下的变体名（文件名去 .py）")
    parser.add_argument("--h5", nargs="+", required=True, help="输入 h5 文件，可传多个/通配")
    parser.add_argument("--episode", type=int, default=0, help="处理哪个 episode，默认 0")
    parser.add_argument("--temporal-stride", type=int, default=4, help="时序降采样步长，默认 4")
    parser.add_argument("--frames", type=int, default=8, help="预览图抽几帧，默认 8")
    parser.add_argument("--output-dir", default=None,
                        help="产物目录，默认 outputs/<variant>/")
    parser.add_argument("--no-grid", action="store_true", help="只出三联预览图，不出全帧网格拼图")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    module = load_variant(namespace.variant)

    if namespace.output_dir is None:
        output_dir = DEFAULT_OUTPUT_ROOT / namespace.variant
    else:
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
            remove_masks, tip_masks, stats = module.compute_masks(frames, phase)
            remove_masks = np.asarray(remove_masks, dtype=bool)
            tip_masks = np.asarray(tip_masks, dtype=bool)
            if remove_masks.shape != frames.shape[:3] or tip_masks.shape != frames.shape[:3]:
                raise ValueError(
                    f"mask 形状不符：remove {remove_masks.shape} tip {tip_masks.shape}"
                    f" vs frames {frames.shape[:3]}"
                )
            overlap = int((remove_masks & tip_masks).sum())
            if overlap:
                raise ValueError(f"remove 与 tip 相交 {overlap} 像素，违反变体契约")
            red_frames = apply_red_mask(frames, remove_masks)

            preview = build_preview_grid(
                frames, red_frames, remove_masks, tip_masks, picked, namespace.frames
            )
            cv2.imwrite(str(output_dir / f"{task}_ep{namespace.episode}_preview.png"), preview)
            if not namespace.no_grid:
                grid = build_frame_grid(red_frames, picked)
                cv2.imwrite(str(output_dir / f"{task}_ep{namespace.episode}_grid.png"), grid)
        except Exception as exc:
            print(f"✗ {task}: {exc}", flush=True)
            failures += 1
            continue
        entry: dict[str, Any] = {
            "variant_stats": stats,
            "tripwire": tripwire_stats(frames, remove_masks, tip_masks),
            "removed_fraction_mean": float(remove_masks.mean()),
            "frame_count": int(frames.shape[0]),
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "source_h5": str(h5_path),
            "temporal_stride": namespace.temporal_stride,
        }
        per_task[task] = entry
        print(
            f"✓ {task}: {entry['frame_count']} 帧，删除占比 {entry['removed_fraction_mean']:.3f}"
            f"，red_on_sat max {entry['tripwire']['red_on_saturated_max']}"
            f"，tip 非零帧 {entry['tripwire']['tip_frames_nonzero']}"
            f"，耗时 {entry['elapsed_seconds']}s",
            flush=True,
        )

    summary = {
        "variant": module.NAME,
        "description": module.DESCRIPTION,
        "episode": namespace.episode,
        "temporal_stride": namespace.temporal_stride,
        "tasks": per_task,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsummary 已写到 {summary_path}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
