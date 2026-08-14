"""可视化视频入口（make_videos）的逻辑测试（合成数据，秒级，不碰真实数据）。

覆盖五件事：

1. **误差着色与计数**：四类互斥且穷尽（并集恰为 pred ∪ GT臂）、不修改输入、
   计数与着色像素数逐项一致、frame_error 刻意不含误涂背景。
2. **网格叠加**：grid_overlay_fast 变色范围恰为 upsample_grid（不画格线时）。
3. **画布布局与拼接**：W/H 为 16 的倍数（防 imageio/libx264 静默缩放）、
   compose_frame 逐块可还原、逐帧字幕纯 ASCII（cv2.putText 画不了中文）。
4. **worst 选段**：边界裁剪不越界、全局 top 段互不重叠（重叠峰跳过取下一名）、
   每任务恰取第一名、误差降序且并列稳定、段数上限与零误差忽略。
5. **fail-loud**：sidecar 指纹（源文件名/字节数/mtime）不符即报错、
   面板数/面板尺寸不符即报错。
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_GEN_DIR = REPO_ROOT / "scripts" / "data-generation"
ARM_MASK_DIR = DATA_GEN_DIR / "arm-mask"
GT_DATA_DIR = DATA_GEN_DIR / "gt-data"

for _path in (str(ARM_MASK_DIR), str(GT_DATA_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

make_videos = importlib.import_module("make_videos")
color_model = importlib.import_module("color_model")
grid_mask_mod = importlib.import_module("grid_mask")

CLASS_ARM = color_model.CLASS_ARM
CLASS_OBJECT = color_model.CLASS_OBJECT
CLASS_BACKGROUND = color_model.CLASS_BACKGROUND
upsample_grid = grid_mask_mod.upsample_grid

ErrorCounts = make_videos.ErrorCounts
FrameScore = make_videos.FrameScore
caption_lines = make_videos.caption_lines
check_sidecar_fingerprint = make_videos.check_sidecar_fingerprint
compose_frame = make_videos.compose_frame
error_counts = make_videos.error_counts
error_overlay = make_videos.error_overlay
frame_error = make_videos.frame_error
gray3 = make_videos.gray3
grid_overlay_fast = make_videos.grid_overlay_fast
panel_layout = make_videos.panel_layout
select_per_task_segments = make_videos.select_per_task_segments
select_top_segments = make_videos.select_top_segments


def _toy_case(size: int = 16) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """合成一帧：GT 三类分块 + 一个跨类的 pred mask。"""
    rng = np.random.default_rng(0)
    rgb = rng.integers(0, 256, (size, size, 3), np.uint8)
    gt = np.full((size, size), CLASS_BACKGROUND, np.int64)
    gt[:, : size // 3] = CLASS_ARM
    gt[:, size // 3 : 2 * size // 3] = CLASS_OBJECT
    pred = np.zeros((size, size), bool)
    pred[: size // 2, :] = True  # 上半横跨三类；下半的 GT 臂全漏
    return rgb, pred, gt


# ---------------------------------------------------------------------------
# 误差着色与计数
# ---------------------------------------------------------------------------


def test_误差着色四类互斥且穷尽():
    rgb, pred, gt = _toy_case()
    image = error_overlay(rgb, pred, gt)
    base = gray3(rgb)
    colors = {
        make_videos.COLOR_MISSED_ARM: (gt == CLASS_ARM) & ~pred,
        make_videos.COLOR_FALSE_OBJECT: pred & (gt == CLASS_OBJECT),
        make_videos.COLOR_FALSE_BACKGROUND: pred & (gt == CLASS_BACKGROUND),
        make_videos.COLOR_HIT_ARM: pred & (gt == CLASS_ARM),
    }
    union = np.zeros(pred.shape, bool)
    for color, region in colors.items():
        assert np.all(image[region] == np.array(color, np.uint8)), color
        assert not np.any(union & region), "四类必须互斥"
        union |= region
    assert np.array_equal(union, pred | (gt == CLASS_ARM)), "并集必须恰为 pred ∪ GT臂"
    assert np.array_equal(image[~union], base[~union]), "其余像素必须是灰度底"


def test_误差着色不修改输入():
    rgb, pred, gt = _toy_case()
    rgb0, pred0, gt0 = rgb.copy(), pred.copy(), gt.copy()
    error_overlay(rgb, pred, gt)
    error_counts(pred, gt)
    gray3(rgb)
    assert np.array_equal(rgb, rgb0) and np.array_equal(pred, pred0)
    assert np.array_equal(gt, gt0)


def test_误差计数与着色像素数一致():
    rgb, pred, gt = _toy_case()
    counts = error_counts(pred, gt)
    image = error_overlay(rgb, pred, gt)
    for value, color in (
        (counts.missed_arm, make_videos.COLOR_MISSED_ARM),
        (counts.false_object, make_videos.COLOR_FALSE_OBJECT),
        (counts.false_background, make_videos.COLOR_FALSE_BACKGROUND),
        (counts.hit_arm, make_videos.COLOR_HIT_ARM),
    ):
        painted = int(np.all(image == np.array(color, np.uint8), axis=2).sum())
        assert painted == value, color


def test_逐帧误差只算漏标与误涂物体():
    base = ErrorCounts(missed_arm=7, false_object=5, false_background=100, hit_arm=3)
    assert frame_error(base) == 12
    # 只加误涂背景：误差不变
    assert frame_error(base._replace(false_background=10_000)) == 12
    # 加漏标 / 误涂物体：线性增加
    assert frame_error(base._replace(missed_arm=8)) == 13
    assert frame_error(base._replace(false_object=6)) == 13


# ---------------------------------------------------------------------------
# 网格叠加
# ---------------------------------------------------------------------------


def test_网格叠加涂色范围等于upsample_grid():
    rng = np.random.default_rng(1)
    rgb = rng.integers(0, 200, (32, 32, 3), np.uint8)  # < 255 保证混红必然变色
    grid = np.zeros((4, 4), bool)
    grid[1, 2] = grid[3, 0] = True
    out = grid_overlay_fast(rgb, grid, cell_size=8, draw_lines=False)
    changed = np.any(out != rgb, axis=2)
    assert np.array_equal(changed, upsample_grid(grid, 8))
    # 输入不被修改
    out2 = grid_overlay_fast(rgb, grid, cell_size=8, draw_lines=True)
    assert out2.shape == rgb.shape and out2.dtype == np.uint8


# ---------------------------------------------------------------------------
# 布局与拼接
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cols,rows", [(3, 1), (3, 2)])
def test_面板拼接尺寸为偶数且16的倍数(cols, rows):
    layout = panel_layout(cols, rows, 256)
    assert layout.width % 16 == 0 and layout.height % 16 == 0
    assert len(layout.panel_boxes) == cols * rows


def test_面板拼接逐块可还原():
    layout = panel_layout(3, 2, 32)
    template = np.zeros((layout.height, layout.width, 3), np.uint8)
    rng = np.random.default_rng(2)
    panels = [rng.integers(0, 256, (32, 32, 3), np.uint8) for _ in range(6)]
    frame = compose_frame(template, panels, layout)
    for (y, x), panel in zip(layout.panel_boxes, panels):
        assert np.array_equal(frame[y : y + 32, x : x + 32], panel)
    assert np.array_equal(template, np.zeros_like(template)), "模板不得被就地修改"


def test_面板数与尺寸不符即报错():
    layout = panel_layout(3, 1, 32)
    template = np.zeros((layout.height, layout.width, 3), np.uint8)
    good = [np.zeros((32, 32, 3), np.uint8)] * 3
    with pytest.raises(ValueError, match="面板数"):
        compose_frame(template, good[:2], layout)
    bad = [np.zeros((16, 16, 3), np.uint8)] * 3
    with pytest.raises(ValueError, match="shape"):
        compose_frame(template, bad, layout)


def test_逐帧字幕为纯ASCII():
    counts = ErrorCounts(1, 2, 3, 4)
    for lines in (
        caption_lines("MoveCube", 0, 5, 96, "demo"),
        caption_lines("RouteStick", 9, 0, 505, "exec", counts, extra="rank 1/20 peak=99@5"),
    ):
        assert all(line.isascii() for line in lines), lines


# ---------------------------------------------------------------------------
# worst 选段
# ---------------------------------------------------------------------------


def _score(task, ep, frame, err):
    return FrameScore(task, ep, frame, err, err, 0)


def test_worst选段边界不越界():
    lengths = {("A", 0): 10}
    scores = [_score("A", 0, 0, 5), _score("A", 0, 9, 4)]
    segments = select_top_segments(scores, lengths, count=2, context_frames=3)
    for seg in segments:
        assert 0 <= seg.start <= seg.end <= 9
    # 两端各一个峰：起点段 [0,3]、终点段 [6,9]
    assert {(s.start, s.end) for s in segments} == {(0, 3), (6, 9)}


def test_worst全局top段互不重叠且重叠峰取下一名():
    lengths = {("A", 0): 100, ("B", 0): 100}
    # 帧 14 与帧 10 的段重叠（±3）→ 帧 10 被跳过，取下一名 B 的帧 50
    scores = [_score("A", 0, 14, 9), _score("A", 0, 10, 5), _score("B", 0, 50, 3)]
    segments = select_top_segments(scores, lengths, count=2, context_frames=3)
    assert [(s.task, s.peak_frame, s.peak_error) for s in segments] == [
        ("A", 14, 9),
        ("B", 50, 3),
    ]
    # 同帧号不同 episode / 任务不算重叠
    lengths2 = {("A", 0): 100, ("A", 1): 100}
    scores2 = [_score("A", 0, 10, 5), _score("A", 1, 10, 4)]
    assert len(select_top_segments(scores2, lengths2, 2, 3)) == 2


def test_worst每任务恰取第一名且按误差降序():
    lengths = {("A", 0): 100, ("A", 1): 100, ("B", 0): 100, ("C", 0): 100}
    scores = [
        _score("A", 0, 10, 5),
        _score("A", 1, 20, 8),  # A 的第一名
        _score("B", 0, 30, 9),  # B 的第一名
        # C 全帧误差 0 → 无段
        _score("C", 0, 40, 0),
    ]
    segments = select_per_task_segments(scores, lengths, context_frames=2)
    assert [(s.task, s.episode, s.peak_frame, s.peak_error) for s in segments] == [
        ("B", 0, 30, 9),
        ("A", 1, 20, 8),
    ]


def test_worst按误差降序且并列稳定():
    lengths = {("A", 0): 100, ("B", 0): 100}
    scores = [_score("B", 0, 50, 7), _score("A", 0, 50, 7), _score("A", 0, 20, 9)]
    segments = select_top_segments(scores, lengths, count=3, context_frames=1)
    assert [(s.task, s.peak_frame) for s in segments] == [("A", 20), ("A", 50), ("B", 50)]


def test_worst段数不超过count且忽略零误差():
    lengths = {("A", 0): 2000}
    scores = [_score("A", 0, t, 0) for t in range(50)] + [
        _score("A", 0, 100 * (i + 1), i + 1) for i in range(10)
    ]
    segments = select_top_segments(scores, lengths, count=4, context_frames=2)
    assert len(segments) == 4
    assert all(seg.peak_error > 0 for seg in segments)
    assert select_top_segments([_score("A", 0, 5, 0)], lengths, 4, 2) == []
    assert select_per_task_segments([_score("A", 0, 5, 0)], lengths, 2) == []


# ---------------------------------------------------------------------------
# fail-loud：sidecar 指纹
# ---------------------------------------------------------------------------


def _fingerprint_attrs(path: Path) -> dict:
    stat = path.stat()
    return {
        "source_h5": str(path),
        "source_h5_size_bytes": stat.st_size,
        "source_h5_mtime_iso": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def test_sidecar指纹一致时通过(tmp_path):
    source = tmp_path / "record_dataset_Toy.h5"
    source.write_bytes(b"x" * 128)
    check_sidecar_fingerprint(_fingerprint_attrs(source), source, "Toy/episode_0")


def test_sidecar指纹不符时报错(tmp_path):
    source = tmp_path / "record_dataset_Toy.h5"
    source.write_bytes(b"x" * 128)
    good = _fingerprint_attrs(source)
    with pytest.raises(ValueError, match="记录源"):
        check_sidecar_fingerprint({**good, "source_h5": "别的文件.h5"}, source, "ctx")
    with pytest.raises(ValueError, match="字节数"):
        check_sidecar_fingerprint({**good, "source_h5_size_bytes": 1}, source, "ctx")
    with pytest.raises(ValueError, match="mtime"):
        check_sidecar_fingerprint(
            {**good, "source_h5_mtime_iso": "2000-01-01T00:00:00+00:00"}, source, "ctx"
        )


# ---------------------------------------------------------------------------
# mp4 写读 smoke
# ---------------------------------------------------------------------------


def test_写出mp4可回读帧数(tmp_path):
    imageio = pytest.importorskip("imageio")
    pytest.importorskip("imageio_ffmpeg")
    opts = make_videos.VideoOptions(fps=5, quality=5)
    path = tmp_path / "toy.mp4"
    frames = [np.full((32, 32, 3), v, np.uint8) for v in (0, 60, 120, 180)]
    with make_videos._open_writer(path, opts) as writer:
        for frame in frames:
            writer.append_data(frame)
    reader = imageio.get_reader(str(path))
    try:
        assert reader.count_frames() == len(frames)
    finally:
        reader.close()
