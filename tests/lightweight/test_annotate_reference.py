"""官方数据标注入口（annotate_reference）的逻辑测试（合成 h5，秒级，不碰真实数据）。

覆盖四件事：

1. **官方数据帧迭代器**：按 timestep 数字序（h5py 原生是字典序）、不需要
   segmentation（官方数据没有 GT）、缺 front_rgb/is_video_demo/is_completed 逐一
   fail-loud。
2. **标注自检与三层互验**：arm_mask_px → arm_cell_counts → arm_grid_mask 三层严格
   冗余（counts == cell_counts(px)，grid == counts ≥ K=13），timestep 主键连续。
3. **sidecar 写读回环**：datasets 逐位相等且 dtype 不变；attrs 键集合精确等于约定集
   （防漏写也防偷加）；min_pixels attr 恒为 13（用户 2026-08-14 拍板）。
4. **金丝雀纯函数**：PASS / WARN / FAIL-A/B/C/D 各分支、零基线走绝对值分支、
   未见率像素加权（不是逐任务算术平均）。
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
V42_DIR = REPO_ROOT / "scripts" / "data-generation-v4.2"


def _load_v42_modules():
    """隔离加载 v4.2 的模块。

    ⚠ 本文件的撞名面比 test_grid_mask_v4_2.py 宽得多：annotate_reference 顶层 import
    了 arm_mask_v4 / color_model / fit_color_model / grid_mask，惰性路径还会拉
    grid_sweep / render_outputs / segmentation_walkthrough——这些名字在 v4 / v4.1 /
    v4.2 三个目录同名，必须整组隔离，否则按导入顺序静默拿到错目录的实现。
    """
    names = (
        "annotate_reference",
        "grid_sweep",
        "grid_mask",
        "arm_mask_v4",
        "color_model",
        "fit_color_model",
        "render_outputs",
        "segmentation_walkthrough",
    )
    saved = {name: sys.modules.pop(name, None) for name in names}
    sys.path.insert(0, str(V42_DIR))
    try:
        annotate = importlib.import_module("annotate_reference")
        color_model = importlib.import_module("color_model")
        grid_mask = importlib.import_module("grid_mask")
        arm_mask = importlib.import_module("arm_mask_v4")
    finally:
        sys.path.remove(str(V42_DIR))
        for name in names:
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
    return annotate, color_model, grid_mask, arm_mask


annotate_reference, color_model, grid_mask_mod, arm_mask_v4 = _load_v42_modules()

CLASS_ARM = color_model.CLASS_ARM
CLASS_UNKNOWN = color_model.CLASS_UNKNOWN
ColorModel = color_model.ColorModel
MaskParams = arm_mask_v4.MaskParams
cell_counts = grid_mask_mod.cell_counts

CanaryThresholds = annotate_reference.CanaryThresholds
annotate_episode_arrays = annotate_reference.annotate_episode_arrays
canary_verdict = annotate_reference.canary_verdict
iter_reference_frames = annotate_reference.iter_reference_frames
pick_preview_frames = annotate_reference.pick_preview_frames
read_sidecar_episode = annotate_reference.read_sidecar_episode
verify_sidecar = annotate_reference.verify_sidecar
write_sidecar = annotate_reference.write_sidecar

FRAME_PIXELS = annotate_reference.FRAME_PIXELS

# 合成用三种颜色：臂色（混合列 0、臂列 >0）/ 背景色（重叠计数：背景列与混合列同 >0）/
# 表外色（查不到 → UNKNOWN）
ARM_RGB = (10, 20, 30)
BG_RGB = (200, 210, 220)
UNSEEN_RGB = (123, 45, 67)


def _pack(rgb):
    r, g, b = rgb
    return (r << 16) | (g << 8) | b


def _tiny_model() -> ColorModel:
    entries = {
        _pack(ARM_RGB): (0, 0, 50),
        _pack(BG_RGB): (80, 80, 0),
    }
    colors = np.array(sorted(entries), np.uint32)
    counts = np.array([entries[int(c)] for c in colors], np.int64)
    return ColorModel(colors=colors, counts=counts, source={})


def _frame(size: int = 32, arm_block: int = 12, unseen_pixels: int = 0) -> np.ndarray:
    """背景铺满 + 左上角贴顶臂块 + 可选右下角表外色像素。"""
    frame = np.zeros((size, size, 3), np.uint8)
    frame[:, :] = BG_RGB
    frame[:arm_block, :arm_block] = ARM_RGB
    if unseen_pixels:
        flat = frame.reshape(-1, 3)
        flat[-unseen_pixels:] = UNSEEN_RGB
    return frame


def _make_episode(
    handle: h5py.File,
    name: str = "episode_0",
    frames: list[np.ndarray] | None = None,
    demo: list[bool] | None = None,
    completed: list[bool] | None = None,
    drop_field: str | None = None,
) -> h5py.Group:
    frames = frames if frames is not None else [_frame() for _ in range(4)]
    demo = demo if demo is not None else [True, True, False, False]
    completed = completed if completed is not None else [False] * (len(frames) - 1) + [True]
    episode = handle.create_group(name)
    setup = episode.create_group("setup")
    setup.create_dataset("seed", data=14000)
    setup.create_dataset("difficulty", data="normal")
    for index, (frame, is_demo, is_completed) in enumerate(zip(frames, demo, completed)):
        group = episode.create_group(f"timestep_{index}")
        obs = group.create_group("obs")
        if drop_field != "front_rgb":
            obs.create_dataset("front_rgb", data=frame)
        info = group.create_group("info")
        if drop_field != "is_video_demo":
            info.create_dataset("is_video_demo", data=is_demo)
        if drop_field != "is_completed":
            info.create_dataset("is_completed", data=is_completed)
    return episode


def _memory_h5() -> h5py.File:
    return h5py.File(io.BytesIO(), "w")


def test_迭代器按数字序且不需要segmentation():
    with _memory_h5() as handle:
        # 12 帧才会暴露字典序陷阱（timestep_10 < timestep_2）
        episode = _make_episode(
            handle,
            frames=[_frame(unseen_pixels=i) for i in range(12)],
            demo=[True] * 3 + [False] * 9,
            completed=[False] * 11 + [True],
        )
        rows = list(iter_reference_frames(episode))
        assert [name for name, _, _, _ in rows] == [f"timestep_{i}" for i in range(12)]
        # 合成 episode 里根本没有 front_camera_segmentation，能走通即证明不触碰 GT
        assert [int((rgb.reshape(-1, 3) == UNSEEN_RGB).all(axis=1).sum()) for _, rgb, _, _ in rows] == list(range(12))
        assert [flag for _, _, flag, _ in rows] == [True] * 3 + [False] * 9
        assert [flag for _, _, _, flag in rows] == [False] * 11 + [True]


def test_缺字段各自fail_loud():
    for field in ("front_rgb", "is_video_demo", "is_completed"):
        with _memory_h5() as handle:
            episode = _make_episode(handle, drop_field=field)
            with pytest.raises(KeyError, match="timestep_0"):
                list(iter_reference_frames(episode))


def test_标注三层互验与主键自检():
    model = _tiny_model()
    with _memory_h5() as handle:
        episode = _make_episode(
            handle, frames=[_frame(unseen_pixels=k * 5) for k in range(4)]
        )
        record = annotate_episode_arrays(
            episode, model, MaskParams(), cell_size=8, min_pixels=13, keep_frames=True
        )
    assert record["num_frames"] == 4
    # 三层严格冗余：counts == cell_counts(px)，grid == counts >= 13
    for t in range(4):
        assert np.array_equal(
            record["arm_cell_counts"][t].astype(np.int64),
            cell_counts(record["arm_mask_px"][t], 8),
        )
    assert np.array_equal(
        record["arm_grid_mask"], record["arm_cell_counts"].astype(np.int64) >= 13
    )
    assert record["arm_grid_mask"].dtype == np.bool_
    assert np.array_equal(record["timestep_index"], np.arange(4, dtype=np.int32))
    # 未见色逐帧计数 = 合成时埋进去的表外色像素数
    assert record["unseen_pixels"].tolist() == [0, 5, 10, 15]
    assert record["unseen_color_pixels"] == 30
    # 臂块贴顶且远大于噪声，形态学后 mask 非空、网格非空
    assert record["empty_mask_frames"] == 0
    assert record["empty_grid_frames"] == 0
    # 直方图后缀和 == 网格格数（换 K 免重跑的地基）
    hist = np.asarray(record["counts_histogram"])
    assert int(hist[13:].sum()) == int(record["arm_grid_mask"].sum())


def test_K13常量与拍板口径():
    assert annotate_reference.GRID_MIN_PIXELS == 13


def test_demo_prefix前缀与非前缀():
    assert annotate_reference._demo_prefix(np.array([True, True, False, False])) == 2
    assert annotate_reference._demo_prefix(np.array([False, False])) == 0
    assert annotate_reference._demo_prefix(np.array([True, False, True])) == -1
    assert annotate_reference._phase_segments(np.array([True, False, True])) == 3
    assert annotate_reference._phase_segments(np.array([True, True])) == 1


def test_预览挑帧规则():
    arm = np.array([5, 50, 1, 20])
    unseen = np.array([0, 3, 9, 2])
    picked = pick_preview_frames(arm, unseen, ("max", "min", "unseen"))
    assert picked == {"max": 1, "min": 2, "unseen": 2}
    with pytest.raises(ValueError):
        pick_preview_frames(arm, unseen, ("typical",))


def _fake_record(total: int = 3) -> dict:
    rng = np.random.default_rng(0)
    mask_px = rng.random((total, 32, 32)) > 0.6
    counts = np.stack([cell_counts(m, 8) for m in mask_px]).astype(np.uint8)
    grid = counts >= 13
    arm_pixels = mask_px.reshape(total, -1).sum(axis=1).astype(np.int32)
    return {
        "num_frames": total,
        "arm_grid_mask": grid,
        "arm_cell_counts": counts,
        "arm_mask_px": mask_px,
        "is_video_demo": np.array([True] + [False] * (total - 1)),
        "is_completed": np.array([False] * (total - 1) + [True]),
        "unseen_pixels": np.arange(total, dtype=np.int32),
        "arm_pixels": arm_pixels,
        "timestep_index": np.arange(total, dtype=np.int32),
        "seed": 14000,
        "difficulty": "normal",
        "demo_prefix": 1,
        "phase_segments": 2,
        "unseen_color_pixels": int(np.arange(total).sum()),
        "classified_arm_pixels": int(arm_pixels.sum()) + 7,
        "arm_pixels_total": int(arm_pixels.sum()),
        "grid_cells_total": int(grid.sum()),
        "empty_mask_frames": 0,
        "empty_grid_frames": int((grid.reshape(total, -1).sum(axis=1) == 0).sum()),
        "counts_histogram": np.bincount(
            counts.reshape(-1).astype(np.int64), minlength=65
        ).astype(int),
    }


def _root_attrs() -> dict:
    return {
        "schema_version": annotate_reference.SIDECAR_SCHEMA_VERSION,
        "task": "MoveCube",
        "source_h5": "/tmp/fake.h5",
        "source_h5_size_bytes": 1,
        "source_h5_mtime_iso": "2026-08-14T00:00:00+00:00",
        "episodes": np.array([0], np.int32),
        "min_pixels": annotate_reference.GRID_MIN_PIXELS,
        "cell_size": 8,
        "grid_shape": np.array([32, 32], np.int32),
        "frame_shape": np.array([256, 256, 3], np.int32),
        "wan_vae_spatial_downsample": 8,
        "threshold_rule": "cell_counts >= min_pixels（整数比较，无浮点边界）",
        "color_model_path": "outputs/color_model.npz",
        "color_model_md5": "0" * 32,
        "mask_open_iterations": 1,
        "mask_temporal_window": 3,
        "mask_final_erode": 1,
        "pipeline": "color_model.classify -> arm_mask_v4.arm_masks_for_episode -> grid_mask",
        "has_ground_truth": False,
        "generated_at_iso": "2026-08-14T00:00:00+00:00",
        "git_commit": "test",
    }


def test_sidecar写读回环与attrs键集(tmp_path):
    records = {0: _fake_record()}
    out = write_sidecar(tmp_path / "arm_grid_mask_MoveCube.h5", records, _root_attrs(), True)
    verify_sidecar(out, records, True)  # 逐位对拍（含 dtype）
    loaded = read_sidecar_episode(out, "episode_0")
    assert set(loaded["root_attrs"]) == set(annotate_reference.ROOT_ATTR_KEYS)
    assert set(loaded["attrs"]) == set(annotate_reference.EPISODE_ATTR_KEYS)
    assert int(loaded["root_attrs"]["min_pixels"]) == 13
    assert loaded["root_attrs"]["has_ground_truth"] == False  # noqa: E712
    assert loaded["arm_grid_mask"].dtype == np.bool_
    # 篡改内存数组后 verify 必须报错（对拍不是摆设）
    records[0]["arm_grid_mask"] = ~records[0]["arm_grid_mask"]
    with pytest.raises(AssertionError):
        verify_sidecar(out, records, True)


def test_sidecar可选不落像素层(tmp_path):
    records = {0: _fake_record()}
    out = write_sidecar(tmp_path / "no_px.h5", records, _root_attrs(), False)
    loaded = read_sidecar_episode(out, "episode_0")
    assert "arm_mask_px" not in loaded
    verify_sidecar(out, records, False)


def _task_entry(unseen_rate: float, arm_rate: float = 0.04, frames: int = 100) -> dict:
    total = frames * FRAME_PIXELS
    return {
        "total_pixels": total,
        "unseen_color_pixels": int(round(unseen_rate * total)),
        "arm_pixels": int(round(arm_rate * total)),
    }


def _episode_entry(task: str, empty: int = 0, frames: int = 100) -> dict:
    return {"task": task, "episode": 0, "num_frames": frames, "empty_mask_frames": empty}


def test_金丝雀表驱动():
    thresholds = CanaryThresholds()
    baseline = {"A": 0.002, "B": 0.0}

    # PASS：未见率与基线同量级、判臂率健康、无空帧
    verdict, details = canary_verdict(
        {"A": _task_entry(0.002), "B": _task_entry(0.0001)},
        [_episode_entry("A")],
        baseline,
        thresholds,
    )
    assert verdict == "PASS" and details == []

    # WARN：倍率 3×（>2）且绝对值 0.6%？——0.6% 会撞 FAIL 绝对值上限，取 0.3%
    verdict, details = canary_verdict(
        {"A": _task_entry(0.003), "B": _task_entry(0.0)},
        [_episode_entry("A")],
        baseline,
        thresholds,
    )
    assert verdict == "PASS"  # 0.003/0.002 = 1.5×，未到 WARN 倍率
    verdict, details = canary_verdict(
        {"A": _task_entry(0.0045), "B": _task_entry(0.0)},
        [_episode_entry("A")],
        baseline,
        thresholds,
    )
    assert verdict == "WARN" and any("WARN A" in line for line in details)

    # FAIL-B：倍率 >5× 且绝对值 >0.5% 同时成立才 FAIL
    verdict, details = canary_verdict(
        {"A": _task_entry(0.011), "B": _task_entry(0.0)},
        [_episode_entry("A")],
        baseline,
        thresholds,
    )
    assert verdict == "FAIL" and any("FAIL-B A" in line for line in details)
    # 只超倍率不超绝对值 → 不 FAIL（双判据）
    verdict, _ = canary_verdict(
        {"A": _task_entry(0.002), "B": _task_entry(0.004)},  # B 基线 0 → 绝对值分支
        [_episode_entry("B")],
        baseline,
        thresholds,
    )
    assert verdict == "WARN"  # B 走零基线绝对值分支：0.4% > 0.1% WARN、未过 0.5% FAIL

    # 零基线绝对值 FAIL 分支
    verdict, details = canary_verdict(
        {"B": _task_entry(0.006)},
        [_episode_entry("B")],
        baseline,
        thresholds,
    )
    assert verdict == "FAIL" and any("无有效基线" in line for line in details)

    # FAIL-A 全局：像素加权而非任务算术平均——大任务 0.6% 小任务 0%，
    # 加权 (0.006·900)/1000 = 0.54% > 0.5%，算术平均 0.3% 会漏判
    verdict, details = canary_verdict(
        {
            "A": _task_entry(0.006, frames=900),
            "B": _task_entry(0.0, frames=100),
        },
        [],
        {"A": 0.004, "B": 0.0},
        thresholds,
    )
    assert any(line.startswith("FAIL-A") for line in details)

    # FAIL-C 空 mask 帧：2/100 = 2% > 1%
    verdict, details = canary_verdict(
        {"A": _task_entry(0.001)},
        [_episode_entry("A", empty=2)],
        baseline,
        thresholds,
    )
    assert verdict == "FAIL" and any("FAIL-C" in line for line in details)

    # FAIL-D 判臂率下限：0.3% < 0.5%
    verdict, details = canary_verdict(
        {"A": _task_entry(0.001, arm_rate=0.003)},
        [_episode_entry("A")],
        baseline,
        thresholds,
    )
    assert verdict == "FAIL" and any("FAIL-D" in line for line in details)
