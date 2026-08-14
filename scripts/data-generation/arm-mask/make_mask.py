#!/usr/bin/env python3
"""唯一 mask 生产入口：任意 h5 数据源 → K=13 网格 mask sidecar。

## 两个模式共用这一个入口，走完全相同的代码路径

| 模式 | `--source` 指向 | 有 GT？ |
|---|---|---|
| ① 现有 dataset 直接产 mask | 官方 h5 备份 `/data/hongzefu/robomme_data_h5` | 否 |
| ② 同 seed 重新生成 + 实测 | `gt-data/generate_dataset.py` 的产物目录 | 是 |

**本入口全程不看 GT**，只读 `obs/front_rgb` 与 `info/`，因此两种数据源零分叉。
模式②的 GT 量化是之后独立的一步（`evaluate.py` 读本入口写的 sidecar），既不混进
生成器、也不混进 mask 生产。

推理链：像素表查表 → 四条形态学规则 → K=13 网格化。像素表在 **val split** 上拟合，
与两个模式消费的 **train split** 零 seed 重叠。

## 产物（独立 sidecar，源 h5 始终只读）

`<out-dir>/arm_grid_mask_<Task>.h5`，每 episode 三层全存（用户拍板）：
`arm_grid_mask` (T,32,32) bool【正式产物，K=13】、`arm_cell_counts` (T,32,32)
uint8【阈值无关，换 K 免重跑 mask】、`arm_mask_px` (T,256,256) bool【像素层留痕，
任意 K / 涂红帧可由它重建】；另存 `is_video_demo`/`is_completed`（下游 MotionJEPA
build_data_raw_from_h5 切段与 exec 截断必需——刻意**不存** exec_len，
`first_completed + 2` 的截断公式留在下游，防两仓两口径）。主键对齐：
(task, episode_<i>, timestep 序) ↔ MotionJEPA 侧 `<Task>_ep<i>`。

## 金丝雀（无 GT 时的唯一自动监测，产物全部落盘后才判，FAIL 退出码 1）

- **未见颜色率**（诊断量，方向安全——未见 ⇒ 不判臂 ⇒ 只会漏标）：相对基线同任务
  的倍率 + 绝对值**双判据**（单看倍率会被零基线任务放大成无穷；单看绝对值会误杀
  RouteStick——它的未见率来自运行时动态创建的路线曲线，是任务固有属性而非迁移症状）。
  基线取模式②的实测 JSON：同 seed、同场景、同分布，比跨 split 外推强。
- **结构闸门**（真正测「臂丢没丢」）：空像素 mask 帧占比（画面顶部机械臂基座恒可见，
  空帧应为 0）+ 逐任务像素判臂率下限。

⚠ **模式①的根本盲点**：「颜色在标定集只在臂上见过、在官方数据却落在物体上」无法
量化——官方数据没有 GT 当尺子，像素刚性红线（误标物体恒 0）在那里**不可复验**。
关闭这个盲点正是模式②存在的理由：同 seed 重放出带 GT 的同场景数据，让红线可验。

## 用法（在仓库根）

    # 模式①：官方 h5 前 10 个 episode
    uv run --no-sync python scripts/data-generation/arm-mask/make_mask.py \\
      --source /data/hongzefu/robomme_data_h5 --tasks all --episodes 0-9 --workers 16

    # 模式②：自生带 GT 数据（通常由 run_generated.py 编排调用）
    uv run --no-sync python scripts/data-generation/arm-mask/make_mask.py \\
      --source artifacts/generated/<目录> --tasks all --episodes 0-9 \\
      --out-dir <sidecar 目录> --json <统计 JSON>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
GT_DATA_DIR = SCRIPT_DIR.parent / "gt-data"
for _path in (SCRIPT_DIR, GT_DATA_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from arm_mask import MaskParams, apply_red_mask, arm_masks_for_episode  # noqa: E402
from color_model import CLASS_ARM, CLASS_UNKNOWN, ColorModel  # noqa: E402
from fit_color_model import parse_episodes  # noqa: E402
from grid_mask import (  # noqa: E402
    WAN_VAE_SPATIAL_DOWNSAMPLE,
    cell_counts,
    grid_from_counts,
    upsample_grid,
)

# ⚠ 本入口不 import 任何 GT 相关的闸门：mask 生产全程不看 GT，两种数据源零分叉。
# 像素刚性红线（误标物体恒 0）由 evaluate.py 在模式②上校验。

# 用户 2026-08-14 拍板：全局统一 K=13（全任务/episode/格子位置一体生效）。
# 这是全仓唯一落点——grid_mask.GridParams.min_pixels 刻意无默认值，库层不立第二个口径。
GRID_MIN_PIXELS = 13

SIDECAR_SCHEMA_VERSION = "arm-grid-mask-v1"
DEFAULT_SOURCE_ROOT = "/data/hongzefu/robomme_data_h5"
DEFAULT_MODEL = GT_DATA_DIR / "outputs" / "color_model.npz"
# 金丝雀基线：模式②的实测 JSON（同 seed 同场景，比跨 split 外推强）
DEFAULT_BASELINE_JSON = SCRIPT_DIR / "outputs" / "json" / "generated_eval.json"
PREVIEW_KINDS = ("max", "min", "unseen")
FRAME_PIXELS = 256 * 256

# 预览出图口径（只影响 --preview 出的图，不影响任何产物数字）
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
TILE_SCALE_AGENT = 2  # 256→512，整图长边约 1.6k，压缩后仍可读
GRID_OVERLAY_ALPHA = 0.45  # 半透明红：涂死就看不见格里盖了什么
COLOR_BOTH = (96, 226, 240)  # 青：网格与像素 mask 都标
COLOR_GRID_ONLY = (255, 190, 60)  # 橙黄：网格多涂出来的
COLOR_PIXEL_ONLY = (0, 0, 255)  # 蓝：像素 mask 有但网格丢了
CELL_EDGE_COLOR = (255, 255, 120)  # 被选中格的 1px 描边

# sidecar 根 attrs 的约定键集合（测试逐一核对，防漏写也防偷加）
ROOT_ATTR_KEYS = (
    "schema_version",
    "task",
    "source_h5",
    "source_h5_size_bytes",
    "source_h5_mtime_iso",
    "episodes",
    "min_pixels",
    "cell_size",
    "grid_shape",
    "frame_shape",
    "wan_vae_spatial_downsample",
    "threshold_rule",
    "color_model_path",
    "color_model_md5",
    "mask_open_iterations",
    "mask_temporal_window",
    "mask_final_erode",
    "pipeline",
    "has_ground_truth",
    "generated_at_iso",
    "git_commit",
)
EPISODE_ATTR_KEYS = (
    "episode_index",
    "num_frames",
    "seed",
    "difficulty",
    "demo_prefix",
    "phase_segments",
    "unseen_color_pixels",
    "classified_arm_pixels",
    "arm_pixels",
    "grid_cells",
    "empty_mask_frames",
    "empty_grid_frames",
)
EPISODE_DATASETS = (
    "arm_grid_mask",
    "arm_cell_counts",
    "arm_mask_px",
    "is_video_demo",
    "is_completed",
    "unseen_pixels",
    "arm_pixels",
    "timestep_index",
)


@dataclass(frozen=True)
class CanaryThresholds:
    """金丝雀阈值。全部有实测锚点（16 任务官方 ep0 实测），改动前先看 README 五节。"""

    global_unseen_fail: float = 0.005  # 全局未见率上限（基线 0.0019，实测 0.0013）
    task_unseen_ratio_fail: float = 5.0  # 逐任务相对基线倍率……
    task_unseen_abs_fail: float = 0.005  # ……且绝对值须同时超过才 FAIL（双判据）
    task_unseen_ratio_warn: float = 2.0
    task_unseen_abs_warn: float = 0.001
    baseline_floor: float = 1e-5  # 基线低于它的任务走纯绝对值分支（防零基线放大）
    empty_mask_frame_ratio_fail: float = 0.01  # 逐 episode 空像素 mask 帧占比上限
    task_arm_pixel_ratio_fail: float = 0.005  # 逐任务像素判臂率下限（实测最低 1.75%）


def _sorted_numeric_names(group: h5py.Group, prefix: str) -> list[str]:
    """按数字后缀排序的成员名。⚠ h5py 迭代是字典序（timestep_10 < timestep_2），必须显式排。"""
    named: list[tuple[int, str]] = []
    for name in group:
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix) :]
        if not suffix.isdigit():
            raise ValueError(f"无法解析的成员名：{name}")
        named.append((int(suffix), name))
    named.sort()
    return [name for _, name in named]


def iter_frames(
    episode_group: h5py.Group,
) -> Iterator[tuple[str, np.ndarray, bool, bool]]:
    """帧迭代器：按 timestep 数字序产出 (名, front_rgb, is_video_demo, is_completed)。

    与 `color_model.iter_episode_frames` 的两点差异都是刻意的：
    1. **不读 obs/front_camera_segmentation**——mask 生产全程不看 GT，这样官方数据
       （没有 GT，读了必 KeyError）与自生数据（有 GT）能走完全相同的代码路径；
    2. **多读 info/is_completed**——下游 build_data_raw_from_h5 靠它算 exec 截断点
       （`first_completed + 2`，公式留在下游）。
    缺任一字段一律 fail-loud，报错带 timestep 名。
    """
    for name in _sorted_numeric_names(episode_group, "timestep_"):
        group = episode_group[name]
        obs = group.get("obs")
        info = group.get("info")
        if not isinstance(obs, h5py.Group) or "front_rgb" not in obs:
            raise KeyError(f"{name} 缺 obs/front_rgb")
        if not isinstance(info, h5py.Group) or "is_video_demo" not in info:
            raise KeyError(f"{name} 缺 info/is_video_demo")
        if "is_completed" not in info:
            raise KeyError(f"{name} 缺 info/is_completed")
        yield (
            name,
            obs["front_rgb"][()],
            bool(info["is_video_demo"][()]),
            bool(info["is_completed"][()]),
        )


def _demo_prefix(flags: np.ndarray) -> int:
    """is_video_demo 的严格前缀长度；非前缀结构返回 -1（不 fail——mask 链路按段处理不受影响）。"""
    total = int(flags.sum())
    if bool(np.all(flags[:total])) and not bool(np.any(flags[total:])):
        return total
    return -1


def _phase_segments(flags: np.ndarray) -> int:
    if flags.size == 0:
        return 0
    return int(1 + np.count_nonzero(flags[1:] != flags[:-1]))


def annotate_episode_arrays(
    episode_group: h5py.Group,
    model: ColorModel,
    params: MaskParams,
    cell_size: int,
    min_pixels: int,
    keep_frames: bool,
) -> dict[str, Any]:
    """单 episode 全帧标注：classify → 四条形态学规则 → 网格。返回数组 + 统计。

    keep_frames=True 时额外保留 rgb / 判决标签帧（预览渲染用；只在预览开启时付内存）。
    """
    cell_area = cell_size * cell_size
    names: list[str] = []
    rgbs: list[np.ndarray] = []
    demo_flags: list[bool] = []
    completed_flags: list[bool] = []
    predicted: list[np.ndarray] = []
    for name, rgb, is_demo, is_completed in iter_frames(episode_group):
        names.append(name)
        rgbs.append(rgb)
        demo_flags.append(is_demo)
        completed_flags.append(is_completed)
        predicted.append(model.classify(rgb))

    total = len(names)
    if total == 0:
        raise ValueError("episode 没有任何 timestep")
    # 主键自检：timestep 编号必须恰为 0..T-1，破了就停（下游按序号对齐，错位是静默灾难）
    expected = [f"timestep_{i}" for i in range(total)]
    if names != expected:
        raise AssertionError(f"timestep 编号不连续：首个异常 {set(names) ^ set(expected)}")

    masks = arm_masks_for_episode(predicted, demo_flags, params)

    counts = np.stack([cell_counts(mask, cell_size) for mask in masks]).astype(np.uint8)
    assert int(counts.max(initial=0)) <= cell_area
    grid = counts >= min_pixels
    # 与 grid_mask 模块的口径逐位互验（uint8 存储不改变判据）
    if not np.array_equal(grid[0], grid_from_counts(counts[0].astype(np.int64), min_pixels)):
        raise AssertionError("grid 与 grid_from_counts 口径漂移")

    mask_px = np.stack(masks)
    unseen_pixels = np.array(
        [int((labels == CLASS_UNKNOWN).sum()) for labels in predicted], np.int32
    )
    classified_arm = int(sum(int((labels == CLASS_ARM).sum()) for labels in predicted))
    arm_pixels = np.array([int(mask.sum()) for mask in masks], np.int32)
    flags = np.array(demo_flags, bool)

    record: dict[str, Any] = {
        "num_frames": total,
        "arm_grid_mask": grid,
        "arm_cell_counts": counts,
        "arm_mask_px": mask_px,
        "is_video_demo": flags,
        "is_completed": np.array(completed_flags, bool),
        "unseen_pixels": unseen_pixels,
        "arm_pixels": arm_pixels,
        "timestep_index": np.arange(total, dtype=np.int32),
        "demo_prefix": _demo_prefix(flags),
        "phase_segments": _phase_segments(flags),
        "unseen_color_pixels": int(unseen_pixels.sum()),
        "classified_arm_pixels": classified_arm,
        "arm_pixels_total": int(arm_pixels.sum()),
        "grid_cells_total": int(grid.sum()),
        "empty_mask_frames": int((arm_pixels == 0).sum()),
        "empty_grid_frames": int((grid.reshape(total, -1).sum(axis=1) == 0).sum()),
        # 65 行格计数直方图：任意 K 的格数就是它的后缀和，不存计数图也能事后换 K 评估
        "counts_histogram": np.bincount(
            counts.reshape(-1).astype(np.int64), minlength=cell_area + 1
        ).astype(int),
    }
    if keep_frames:
        record["rgb_frames"] = rgbs
        record["label_frames"] = predicted
    return record


def pick_preview_frames(
    arm_pixels: np.ndarray, unseen_pixels: np.ndarray, kinds: Sequence[str]
) -> dict[str, int]:
    """预览挑帧（全部与 K 无关）：max=信息最多 / min=最可能漏臂 / unseen=迁移诊断。"""
    mapping = {
        "max": int(np.argmax(arm_pixels)),
        "min": int(np.argmin(arm_pixels)),
        "unseen": int(np.argmax(unseen_pixels)),
    }
    unknown = set(kinds) - set(mapping)
    if unknown:
        raise ValueError(f"未知的预览帧型：{sorted(unknown)}")
    return {kind: mapping[kind] for kind in kinds}


def _unseen_image(rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """未见色高亮：未见色像素涂品红，其余原图压暗 30%。无 GT 时唯一的迁移诊断面板。"""
    image = (np.asarray(rgb).astype(np.float32) * 0.7).astype(np.uint8)
    image[np.asarray(labels) == CLASS_UNKNOWN] = (255, 0, 255)
    return image


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


# ---------------------------------------------------------------------------
# sidecar 读写
# ---------------------------------------------------------------------------


def write_sidecar(
    out_path: Path,
    records: dict[int, dict[str, Any]],
    root_attrs: dict[str, Any],
    store_pixel_mask: bool,
) -> Path:
    """写一个任务的 sidecar h5。episode 键 = episode_<i>，与官方 h5 同名对齐。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(out_path, "w") as handle:
        for key, value in root_attrs.items():
            handle.attrs[key] = value
        for index in sorted(records):
            record = records[index]
            group = handle.create_group(f"episode_{index}")
            total = record["num_frames"]
            group.attrs["episode_index"] = int(index)
            group.attrs["num_frames"] = int(total)
            group.attrs["seed"] = int(record["seed"])
            group.attrs["difficulty"] = str(record["difficulty"])
            group.attrs["demo_prefix"] = int(record["demo_prefix"])
            group.attrs["phase_segments"] = int(record["phase_segments"])
            group.attrs["unseen_color_pixels"] = int(record["unseen_color_pixels"])
            group.attrs["classified_arm_pixels"] = int(record["classified_arm_pixels"])
            group.attrs["arm_pixels"] = int(record["arm_pixels_total"])
            group.attrs["grid_cells"] = int(record["grid_cells_total"])
            group.attrs["empty_mask_frames"] = int(record["empty_mask_frames"])
            group.attrs["empty_grid_frames"] = int(record["empty_grid_frames"])
            group.create_dataset(
                "arm_grid_mask",
                data=record["arm_grid_mask"],
                compression="gzip",
                compression_opts=4,
                chunks=(min(64, total), *record["arm_grid_mask"].shape[1:]),
            )
            group.create_dataset(
                "arm_cell_counts",
                data=record["arm_cell_counts"],
                compression="gzip",
                compression_opts=4,
                chunks=(min(64, total), *record["arm_cell_counts"].shape[1:]),
            )
            if store_pixel_mask:
                group.create_dataset(
                    "arm_mask_px",
                    data=record["arm_mask_px"],
                    compression="gzip",
                    compression_opts=4,
                    chunks=(min(8, total), *record["arm_mask_px"].shape[1:]),
                )
            group.create_dataset("is_video_demo", data=record["is_video_demo"])
            group.create_dataset("is_completed", data=record["is_completed"])
            group.create_dataset("unseen_pixels", data=record["unseen_pixels"])
            group.create_dataset("arm_pixels", data=record["arm_pixels"])
            group.create_dataset("timestep_index", data=record["timestep_index"])
    return out_path


def read_sidecar_episode(path: str | Path, episode_name: str) -> dict[str, Any]:
    """回读一个 episode（下游消费示例，README 引用）。返回 datasets + attrs。"""
    with h5py.File(str(path), "r") as handle:
        group = handle[episode_name]
        out: dict[str, Any] = {
            name: group[name][()] for name in group if isinstance(group[name], h5py.Dataset)
        }
        out["attrs"] = dict(group.attrs)
        out["root_attrs"] = dict(handle.attrs)
    return out


def verify_sidecar(
    path: Path, records: dict[int, dict[str, Any]], store_pixel_mask: bool
) -> None:
    """写后回读，与内存数组逐位对拍；不一致直接抛错。"""
    for index, record in records.items():
        loaded = read_sidecar_episode(path, f"episode_{index}")
        names = list(EPISODE_DATASETS)
        if not store_pixel_mask:
            names.remove("arm_mask_px")
        for name in names:
            if loaded[name].dtype != record[name].dtype or not np.array_equal(
                loaded[name], record[name]
            ):
                raise AssertionError(f"{path.name}/episode_{index}/{name} 回读对拍失败")


# ---------------------------------------------------------------------------
# 金丝雀
# ---------------------------------------------------------------------------


def load_unseen_baseline(path: Path) -> dict[str, float]:
    """从模式②的实测 JSON 读逐任务未见颜色率当基线。

    兼容两种键名：本仓实测 JSON 写「未见颜色率」，历史 validation JSON 写「未见颜色占比」。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    baseline = {}
    for task, stats in payload["逐任务"].items():
        value = stats.get("未见颜色率")
        if value is None:
            value = stats.get("未见颜色占比")
        baseline[task] = float(value) if value is not None else 0.0
    return baseline


def canary_verdict(
    per_task: dict[str, dict[str, Any]],
    per_episode: Sequence[dict[str, Any]],
    baseline: dict[str, float] | None,
    thresholds: CanaryThresholds,
) -> tuple[str, list[str]]:
    """→ ("PASS"|"WARN"|"FAIL", 命中项中文明细)。纯函数，测试表驱动打这里。

    未见率一律像素加权（Σ未见像素 / Σ总像素），不做逐 episode 算术平均。
    """
    details: list[str] = []
    failed = False
    warned = False

    total_px = sum(item["total_pixels"] for item in per_task.values())
    global_unseen = (
        sum(item["unseen_color_pixels"] for item in per_task.values()) / total_px
        if total_px
        else 0.0
    )
    if global_unseen > thresholds.global_unseen_fail:
        failed = True
        details.append(
            f"FAIL-A 全局未见颜色率 {global_unseen:.4%} > {thresholds.global_unseen_fail:.1%}"
        )

    for task, item in sorted(per_task.items()):
        unseen = item["unseen_color_pixels"] / item["total_pixels"]
        base = baseline.get(task) if baseline is not None else None
        if base is not None and base >= thresholds.baseline_floor:
            ratio = unseen / base
            if (
                ratio > thresholds.task_unseen_ratio_fail
                and unseen > thresholds.task_unseen_abs_fail
            ):
                failed = True
                details.append(
                    f"FAIL-B {task} 未见率 {unseen:.4%}（基线 {base:.4%} 的 {ratio:.1f}×）"
                )
            elif (
                ratio > thresholds.task_unseen_ratio_warn
                and unseen > thresholds.task_unseen_abs_warn
            ):
                warned = True
                details.append(
                    f"WARN {task} 未见率 {unseen:.4%}（基线 {base:.4%} 的 {ratio:.1f}×）"
                )
        else:
            # 零基线/无基线：纯绝对值分支
            if unseen > thresholds.task_unseen_abs_fail:
                failed = True
                details.append(f"FAIL-B {task} 未见率 {unseen:.4%}（无有效基线，绝对值超限）")
            elif unseen > thresholds.task_unseen_abs_warn:
                warned = True
                details.append(f"WARN {task} 未见率 {unseen:.4%}（无有效基线）")

        arm_ratio = item["arm_pixels"] / item["total_pixels"]
        if arm_ratio < thresholds.task_arm_pixel_ratio_fail:
            failed = True
            details.append(
                f"FAIL-D {task} 像素判臂率 {arm_ratio:.4%} < "
                f"{thresholds.task_arm_pixel_ratio_fail:.1%}（臂疑似大面积丢失）"
            )

    for item in per_episode:
        ratio = item["empty_mask_frames"] / item["num_frames"]
        if ratio > thresholds.empty_mask_frame_ratio_fail:
            failed = True
            details.append(
                f"FAIL-C {item['task']}/episode_{item['episode']} 空像素 mask 帧占比 "
                f"{ratio:.2%}（{item['empty_mask_frames']}/{item['num_frames']} 帧）"
            )

    if failed:
        return "FAIL", details
    if warned:
        return "WARN", details
    return "PASS", details


# ---------------------------------------------------------------------------
# 预览渲染（无 GT 版式；在 worker 内渲染，避免帧数据过 pickle）
# ---------------------------------------------------------------------------


def render_episode_previews(
    task: str,
    episode_index: int,
    record: dict[str, Any],
    kinds: Sequence[str],
    cell_size: int,
    min_pixels: int,
    preview_dir: Path,
    baseline_rate: float | None,
) -> int:
    """一个 episode 的预览图：每帧型一张 2×3。返回落盘张数。"""
    # 惰性 import：只有出图才拉 PIL，主链路与测试隔离面都保持窄
    from PIL import Image, ImageDraw, ImageFont

    scale = TILE_SCALE_AGENT
    tile = 256 * scale
    cell_area = cell_size * cell_size

    def font(size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(FONT_PATH, size)

    def text_center(draw, text, box, size, fill=(240, 240, 240)):
        x0, y0, x1, y1 = box
        f = font(size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=f)
        draw.text(
            ((x0 + x1 - (right - left)) / 2 - left, (y0 + y1 - (bottom - top)) / 2 - top),
            text,
            font=f,
            fill=fill,
        )

    frames = pick_preview_frames(record["arm_pixels"], record["unseen_pixels"], kinds)
    total = record["num_frames"]
    episode_unseen = record["unseen_color_pixels"] / (total * FRAME_PIXELS)
    baseline_text = (
        f"（同任务基线 {baseline_rate:.4%}，倍率 "
        f"{episode_unseen / baseline_rate:.2f}×）"
        if baseline_rate is not None and baseline_rate > 0
        else "（无有效基线）"
    )
    legend = (
        "⚠ 官方数据无 GT segmentation，本图无误差图与 GT 三类面板；品红=颜色表未见色"
        f"（一律不判臂）｜ 本 episode 未见率 {episode_unseen:.4%}{baseline_text}"
    )

    written = 0
    for kind, frame_index in frames.items():
        rgb = record["rgb_frames"][frame_index]
        labels = record["label_frames"][frame_index]
        mask = record["arm_mask_px"][frame_index]
        grid = record["arm_grid_mask"][frame_index]
        up = upsample_grid(grid, cell_size)
        phase = "demo" if bool(record["is_video_demo"][frame_index]) else "exec"
        unseen_px = int(record["unseen_pixels"][frame_index])

        white = np.zeros((*up.shape, 3), np.uint8)
        white[up] = (255, 255, 255)
        rows = [
            [
                (_nearest(rgb, scale), "原帧 front_rgb", f"timestep_{frame_index} · {phase}"),
                (
                    _nearest(apply_red_mask(rgb, mask), scale),
                    "像素 mask 红遮罩",
                    f"{int(mask.sum())} px（{mask.sum() / FRAME_PIXELS:.2%}）",
                ),
                (
                    _nearest(_unseen_image(rgb, labels), scale),
                    "未见色高亮（品红）",
                    f"{unseen_px} px（{unseen_px / FRAME_PIXELS:.4%}）",
                ),
            ],
            [
                (
                    _grid_overlay(rgb, grid, cell_size, scale),
                    f"网格叠加（K={min_pixels}）",
                    f"{int(grid.sum())} 格 = {int(grid.sum()) * cell_area} px",
                ),
                (
                    _nearest(_diff_image(mask, up), scale),
                    "网格 vs 像素差异",
                    f"多涂 {int((up & ~mask).sum())} px / 丢 {int((mask & ~up).sum())} px",
                ),
                (_nearest(white, scale), "网格 mask（下游消费口径）", "白=选中格"),
            ],
        ]

        gap, pad, title_h, head_h, foot_h, legend_h = 10, 16, 56, 30, 26, 34
        width = pad * 2 + 3 * tile + 2 * gap
        row_h = head_h + tile + foot_h
        height = title_h + 2 * row_h + legend_h + pad
        canvas = Image.new("RGB", (width, height), (24, 24, 28))
        draw = ImageDraw.Draw(canvas)
        text_center(
            draw,
            f"{task} · episode_{episode_index} · 帧 {frame_index}/{total}（{kind}） · "
            f"K={min_pixels}（{min_pixels}/{cell_area} = {min_pixels / cell_area:.1%}）",
            (0, 0, width, title_h),
            22,
        )
        for row_index, row in enumerate(rows):
            y0 = title_h + row_index * row_h
            for col_index, (image, head, foot) in enumerate(row):
                x0 = pad + col_index * (tile + gap)
                text_center(draw, head, (x0, y0, x0 + tile, y0 + head_h), 16)
                canvas.paste(Image.fromarray(image), (x0, y0 + head_h))
                text_center(
                    draw,
                    foot,
                    (x0, y0 + head_h + tile, x0 + tile, y0 + head_h + tile + foot_h),
                    14,
                    fill=(170, 170, 178),
                )
        text_center(draw, legend, (0, height - legend_h - 6, width, height - 6), 15,
                    fill=(170, 170, 178))
        preview_dir.mkdir(parents=True, exist_ok=True)
        canvas.save(preview_dir / f"{task}_ep{episode_index:02d}_{kind}.png")
        written += 1
    return written


# ---------------------------------------------------------------------------
# per-task worker
# ---------------------------------------------------------------------------


def process_task(
    h5_path: str,
    episodes: tuple[int, ...],
    model_path: str,
    params: MaskParams,
    cell_size: int,
    out_dir: str,
    preview_dir: str | None,
    preview_kinds: tuple[str, ...],
    store_pixel_mask: bool,
    verify: bool,
    baseline_rate: float | None,
    root_attrs_common: dict[str, Any],
) -> dict[str, Any]:
    """一个任务的全部工作：标注 → 写 sidecar → 回读校验 → 渲染预览 → 返回统计。

    worker=任务粒度：sidecar 一任务一文件，worker 自己写自己的文件即无并发写问题，
    数组也不必过 pickle（返回值只有统计与直方图）。
    """
    import cv2

    cv2.setNumThreads(1)  # 16 进程 × cv2 默认多线程会互抢，形态学算子单线程即可

    task = Path(h5_path).stem.replace("record_dataset_", "")
    model = ColorModel.load(model_path)
    want_preview = preview_dir is not None

    records: dict[int, dict[str, Any]] = {}
    with h5py.File(h5_path, "r") as handle:
        for index in episodes:
            name = f"episode_{index}"
            if name not in handle:
                raise KeyError(f"{task} 缺 {name}")
            episode = handle[name]
            record = annotate_episode_arrays(
                episode, model, params, cell_size, GRID_MIN_PIXELS, want_preview
            )
            setup = episode["setup"]
            record["seed"] = int(np.asarray(setup["seed"][()]).item())
            difficulty = setup["difficulty"][()]
            record["difficulty"] = (
                difficulty.decode() if isinstance(difficulty, bytes) else str(difficulty)
            )
            records[index] = record

    source = Path(h5_path)
    stat = source.stat()
    root_attrs = {
        **root_attrs_common,
        "task": task,
        "source_h5": str(source),
        "source_h5_size_bytes": int(stat.st_size),
        "source_h5_mtime_iso": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        "episodes": np.array(sorted(records), np.int32),
    }
    out_path = Path(out_dir) / f"arm_grid_mask_{task}.h5"
    write_sidecar(out_path, records, root_attrs, store_pixel_mask)
    if verify:
        verify_sidecar(out_path, records, store_pixel_mask)

    previews_written = 0
    if want_preview:
        for index, record in records.items():
            previews_written += render_episode_previews(
                task,
                index,
                record,
                preview_kinds,
                cell_size,
                GRID_MIN_PIXELS,
                Path(preview_dir),
                baseline_rate,
            )

    cell_area = cell_size * cell_size
    per_episode = []
    histogram = np.zeros(cell_area + 1, np.int64)
    for index, record in sorted(records.items()):
        histogram += np.asarray(record["counts_histogram"], np.int64)
        per_episode.append(
            {
                "task": task,
                "episode": index,
                "num_frames": record["num_frames"],
                "demo_prefix": record["demo_prefix"],
                "phase_segments": record["phase_segments"],
                "unseen_color_pixels": record["unseen_color_pixels"],
                "未见颜色率": record["unseen_color_pixels"]
                / (record["num_frames"] * FRAME_PIXELS),
                "classified_arm_pixels": record["classified_arm_pixels"],
                "arm_pixels": record["arm_pixels_total"],
                "grid_cells": record["grid_cells_total"],
                "empty_mask_frames": record["empty_mask_frames"],
                "empty_grid_frames": record["empty_grid_frames"],
                "格计数直方图": [int(v) for v in record["counts_histogram"]],
            }
        )
    num_frames = sum(record["num_frames"] for record in records.values())
    return {
        "task": task,
        "sidecar": str(out_path),
        "num_episodes": len(records),
        "num_frames": num_frames,
        "total_pixels": num_frames * FRAME_PIXELS,
        "unseen_color_pixels": int(
            sum(record["unseen_color_pixels"] for record in records.values())
        ),
        "classified_arm_pixels": int(
            sum(record["classified_arm_pixels"] for record in records.values())
        ),
        "arm_pixels": int(sum(record["arm_pixels_total"] for record in records.values())),
        "grid_cells": int(sum(record["grid_cells_total"] for record in records.values())),
        "empty_mask_frames": int(
            sum(record["empty_mask_frames"] for record in records.values())
        ),
        "empty_grid_frames": int(
            sum(record["empty_grid_frames"] for record in records.values())
        ),
        "previews_written": previews_written,
        "counts_histogram": [int(v) for v in histogram],
        "per_episode": per_episode,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _source_has_ground_truth(h5_path: Path, episode: int) -> bool:
    """探测数据源有没有 GT segmentation（只影响 sidecar 的一条 attr，不影响 mask 产出）。"""
    with h5py.File(str(h5_path), "r") as handle:
        group = handle.get(f"episode_{episode}")
        if not isinstance(group, h5py.Group):
            return False
        first = group.get("timestep_0")
        if not isinstance(first, h5py.Group):
            return False
        obs = first.get("obs")
        return isinstance(obs, h5py.Group) and "front_camera_segmentation" in obs


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        "--reference-root",
        dest="source",
        default=DEFAULT_SOURCE_ROOT,
        help="h5 数据源目录：官方备份（模式①）或自生带 GT 数据集（模式②）。始终只读",
    )
    parser.add_argument("--tasks", default="all", help="all 或逗号分隔任务名")
    parser.add_argument("--episodes", default="0-9", help="episode 区间（用户口径：前 10 个）")
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="像素表 npz（gt-data 产出）")
    parser.add_argument(
        "--out-dir",
        default=str(SCRIPT_DIR / "outputs" / "arm_grid_mask_reference"),
        help="sidecar 输出目录（每任务一个 h5）",
    )
    parser.add_argument(
        "--json",
        default=str(SCRIPT_DIR / "outputs" / "json" / "make_mask_reference.json"),
    )
    parser.add_argument("--preview-dir", default=None, help="预览图目录；默认不出图")
    parser.add_argument("--no-preview", action="store_true", help="显式声明不出图")
    parser.add_argument("--preview-kinds", default=",".join(PREVIEW_KINDS))
    parser.add_argument(
        "--no-store-pixel-mask",
        action="store_true",
        help="不落 arm_mask_px 像素层（默认三层全存，用户拍板）",
    )
    parser.add_argument("--baseline-json", default=str(DEFAULT_BASELINE_JSON))
    parser.add_argument("--no-baseline", action="store_true", help="无基线降级为纯绝对值判据")
    parser.add_argument(
        "--no-canary",
        action="store_true",
        help="跳过金丝雀判决（模式②专用）。金丝雀是**无 GT 时的替代监测**；数据源带 GT 时 "
        "evaluate.py 的刚性红线是更强的判据，此时再跑金丝雀既冗余、又因缺基线而退化成纯"
        "绝对值判据，会误杀 RouteStick / InsertPeg 这类未见率天生偏高的任务（其高未见率"
        "来自运行时动态创建的路线曲线等，是任务固有属性而非迁移症状）",
    )
    parser.add_argument("--no-verify", action="store_true", help="跳过写后回读对拍")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--open-iterations", type=int, default=1)
    parser.add_argument("--temporal-window", type=int, default=3)
    parser.add_argument("--final-erode", type=int, default=1)
    args = parser.parse_args(argv)

    if args.preview_dir and args.no_preview:
        raise SystemExit("--preview-dir 与 --no-preview 互斥")
    preview_kinds = tuple(
        kind.strip() for kind in args.preview_kinds.split(",") if kind.strip()
    )

    source_root = Path(args.source)
    all_paths = sorted(source_root.glob("record_dataset_*.h5"))
    if not all_paths:
        raise SystemExit(f"数据源目录没有 record_dataset_*.h5：{source_root}")
    if args.tasks != "all":
        wanted_tasks = {item.strip() for item in args.tasks.split(",") if item.strip()}
        paths = [
            path
            for path in all_paths
            if path.stem.replace("record_dataset_", "") in wanted_tasks
        ]
        missing = wanted_tasks - {
            path.stem.replace("record_dataset_", "") for path in paths
        }
        if missing:
            raise SystemExit(f"找不到任务：{sorted(missing)}")
    else:
        paths = all_paths

    episodes = tuple(parse_episodes(args.episodes))
    params = MaskParams(
        open_iterations=args.open_iterations,
        temporal_window=args.temporal_window,
        final_erode=args.final_erode,
    )

    baseline: dict[str, float] | None = None
    if not args.no_baseline:
        baseline_path = Path(args.baseline_json)
        if not baseline_path.exists():
            raise SystemExit(
                f"金丝雀基线不存在：{baseline_path}（无基线运行须显式 --no-baseline）"
            )
        baseline = load_unseen_baseline(baseline_path)

    model_path = Path(args.model)
    cell_size = WAN_VAE_SPATIAL_DOWNSAMPLE
    source_has_gt = _source_has_ground_truth(paths[0], episodes[0])
    root_attrs_common: dict[str, Any] = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "min_pixels": int(GRID_MIN_PIXELS),
        "cell_size": int(cell_size),
        "grid_shape": np.array([256 // cell_size, 256 // cell_size], np.int32),
        "frame_shape": np.array([256, 256, 3], np.int32),
        "wan_vae_spatial_downsample": int(WAN_VAE_SPATIAL_DOWNSAMPLE),
        "threshold_rule": "cell_counts >= min_pixels（整数比较，无浮点边界）",
        "color_model_path": str(model_path),
        "color_model_md5": _md5(model_path),
        "mask_open_iterations": int(params.open_iterations),
        "mask_temporal_window": int(params.temporal_window),
        "mask_final_erode": int(params.final_erode),
        "pipeline": "color_model.classify -> arm_mask.arm_masks_for_episode -> grid_mask",
        # 只描述**数据源**有没有 GT（模式②有、模式①没有）；本入口两种情况都不读 GT
        "has_ground_truth": bool(source_has_gt),
        "generated_at_iso": datetime.now(tz=timezone.utc).isoformat(),
        "git_commit": _git_commit(),
    }

    print(
        f"mask 生产：{len(paths)} 个任务 × episodes {sorted(episodes)}，"
        f"K={GRID_MIN_PIXELS}（{GRID_MIN_PIXELS}/{cell_size * cell_size} = "
        f"{GRID_MIN_PIXELS / cell_size**2:.1%}），"
        f"数据源{'带 GT（模式②）' if source_has_gt else '无 GT（模式①）'}，"
        f"并行 {args.workers}"
    )
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_task,
                str(path),
                episodes,
                str(model_path),
                params,
                cell_size,
                args.out_dir,
                None if args.no_preview else args.preview_dir,
                preview_kinds,
                not args.no_store_pixel_mask,
                not args.no_verify,
                (
                    baseline.get(path.stem.replace("record_dataset_", ""))
                    if baseline
                    else None
                ),
                root_attrs_common,
            ): path
            for path in paths
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"  {result['task']}: {result['num_episodes']} ep / "
                f"{result['num_frames']} 帧，未见率 "
                f"{result['unseen_color_pixels'] / result['total_pixels']:.4%}，"
                f"判臂率 {result['arm_pixels'] / result['total_pixels']:.2%}"
            )
    elapsed = time.perf_counter() - started
    results.sort(key=lambda item: item["task"])

    per_task = {item["task"]: item for item in results}
    per_episode = [entry for item in results for entry in item["per_episode"]]
    thresholds = CanaryThresholds()
    if args.no_canary:
        verdict, details = "SKIPPED", [
            "数据源带 GT，判据以 evaluate.py 的刚性红线（误标物体像素恒 0）为准；"
            "金丝雀是无 GT 时的替代监测，此处跳过"
        ]
    else:
        verdict, details = canary_verdict(per_task, per_episode, baseline, thresholds)

    total_px = sum(item["total_pixels"] for item in results)
    payload = {
        "参数": {
            "source": str(source_root),
            "数据源带GT": bool(source_has_gt),
            "episodes": sorted(episodes),
            "口径": "像素表拟合在 val split，本入口消费 train split（零 seed 重叠）；"
            "mask 生产全程不看 GT。无 GT 数据源上像素刚性红线不可复验，"
            "由模式②（同 seed 重放出带 GT 的同场景数据）关闭该盲点",
            "min_pixels": GRID_MIN_PIXELS,
            "cell_size": cell_size,
            "形态学参数": [params.open_iterations, params.temporal_window, params.final_erode],
            "color_model_md5": root_attrs_common["color_model_md5"],
            "store_pixel_mask": not args.no_store_pixel_mask,
            "金丝雀阈值": {
                "全局未见率上限": thresholds.global_unseen_fail,
                "逐任务倍率上限(且)": thresholds.task_unseen_ratio_fail,
                "逐任务绝对值上限": thresholds.task_unseen_abs_fail,
                "空mask帧占比上限": thresholds.empty_mask_frame_ratio_fail,
                "判臂率下限": thresholds.task_arm_pixel_ratio_fail,
            },
            "基线": None if baseline is None else str(args.baseline_json),
        },
        "耗时秒": round(elapsed, 1),
        "金丝雀": {"判决": verdict, "命中项": details},
        "全局": {
            "num_frames": sum(item["num_frames"] for item in results),
            "unseen_color_pixels": sum(item["unseen_color_pixels"] for item in results),
            "未见颜色率": sum(item["unseen_color_pixels"] for item in results) / total_px,
            "arm_pixels": sum(item["arm_pixels"] for item in results),
            "像素判臂率": sum(item["arm_pixels"] for item in results) / total_px,
            "grid_cells": sum(item["grid_cells"] for item in results),
            "empty_mask_frames": sum(item["empty_mask_frames"] for item in results),
            "empty_grid_frames": sum(item["empty_grid_frames"] for item in results),
            "previews_written": sum(item["previews_written"] for item in results),
        },
        "逐任务": {
            item["task"]: {
                key: item[key]
                for key in (
                    "sidecar",
                    "num_episodes",
                    "num_frames",
                    "unseen_color_pixels",
                    "classified_arm_pixels",
                    "arm_pixels",
                    "grid_cells",
                    "empty_mask_frames",
                    "empty_grid_frames",
                    "counts_histogram",
                )
            }
            | {
                "未见颜色率": item["unseen_color_pixels"] / item["total_pixels"],
                "像素判臂率": item["arm_pixels"] / item["total_pixels"],
                "基线未见率": baseline.get(item["task"]) if baseline else None,
            }
            for item in results
        },
        "逐 episode": per_episode,
    }
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"统计 JSON 已写入 {json_path}")

    print(f"金丝雀判决：{verdict}")
    for line in details:
        print(f"  {line}")
    if verdict == "FAIL":
        print("⚠ 金丝雀 FAIL：产物已全部落盘（供诊断），以退出码 1 结束")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
