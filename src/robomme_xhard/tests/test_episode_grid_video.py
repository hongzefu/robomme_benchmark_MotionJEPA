"""episode_grid_video 的 CPU 轻量测试：用 tmp_path 造极小假 mp4，验证 2x3 布局与标注口径。"""

from __future__ import annotations

import json
from pathlib import Path

import imageio
import numpy as np
import pytest

from robomme.env_record_wrapper.RecordWrapper import RobommeRecordWrapper as RecordWrapper
from robomme_xhard.tools import episode_grid_video as egv

# 不同档用不同纯色，便于在拼接画面里定位
COLORS = {
    "mother": (200, 30, 30),
    "xhard12": (30, 200, 30),
    "xhard14": (30, 30, 200),
    "xhard16": (200, 200, 30),
    "xhard18": (30, 200, 200),
    "xhard20": (200, 30, 200),
}
GOAL = "put_two_red_cubes_into_the_bin"


def _write(path: Path, n: int, h: int, w: int, color) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = color
    with imageio.get_writer(path.as_posix(), fps=30, codec="libx264", quality=8) as writer:
        for _ in range(n):
            writer.append_data(frame)


def _vname(task: str, ep: int, seed: int, diff: str, prefix: str = "") -> str:
    return f"{prefix}{task}_ep{ep}_seed{seed}_{diff}_{GOAL}.mp4"


def _card(task, role, diff, ep, seed, ts, ok=True):
    return {
        "task": task,
        "role": role,
        "difficulty": diff,
        "mother_episode": ep,
        "seed": seed,
        "timesteps": ts,
        "ok": ok,
    }


@pytest.fixture
def recorded_writes(monkeypatch):
    """记录对原版 _video_write_mp4 的调用，并把帧收进内存（不真正编码）。"""
    calls = []

    def fake(self, frames, output_path):
        calls.append({"self": self, "path": output_path, "frames": [np.array(f) for f in frames]})
        Path(output_path).write_bytes(b"")

    monkeypatch.setattr(RecordWrapper, "_video_write_mp4", fake)
    return calls


def _make_binfill_root(root: Path) -> None:
    """BinFill ep7 seed4701：母档 16x32 帧 5 帧；xhard12 32x48 帧 9 帧；xhard14 只有 FAILED_；
    xhard16 只有 success_NO_OBJECT_（应视作无产物）；xhard18 无任何文件；xhard20 正常 3 帧。"""
    task, ep, seed = "BinFill", 7, 4701
    _write(root / "mother/videos" / _vname(task, ep, seed, "hard"), 5, 16, 32, COLORS["mother"])
    _write(root / "xhard12/videos" / _vname(task, ep, seed, "xhard12"), 9, 32, 48, COLORS["xhard12"])
    _write(root / "xhard14/videos" / _vname(task, ep, seed, "xhard14", "FAILED_"), 4, 16, 32, COLORS["xhard14"])
    _write(
        root / "xhard16/videos" / _vname(task, ep, seed, "xhard16", "success_NO_OBJECT_"),
        4, 16, 32, COLORS["xhard16"],
    )
    _write(root / "xhard20/videos" / _vname(task, ep, seed, "xhard20"), 3, 16, 32, COLORS["xhard20"])
    cards = [
        _card(task, "mother", "hard", ep, seed, 100),
        _card(task, "xhard", "xhard12", ep, seed, 168),
        _card(task, "xhard", "xhard14", ep, seed, None, ok=False),
        _card(task, "xhard", "xhard20", ep, seed, 250),
    ]
    (root / "run_summary.json").write_text(json.dumps({"cards": cards}), encoding="utf-8")


def test_layout_labels_padding_and_timeline(tmp_path, recorded_writes):
    root = tmp_path / "root"
    _make_binfill_root(root)
    stats = egv.render_all(root, tmp_path / "out")
    assert stats["videos"] == 1
    assert stats["cells"] == 6
    # xhard16（只有 NO_OBJECT）与 xhard18 为无产物
    assert stats["missing"] == 2

    assert len(recorded_writes) == 1
    call = recorded_writes[0]
    assert call["self"] is None  # 原版函数以未绑定方式调用
    assert Path(call["path"]).name == "1.1_BinFill_ep7_seed4701.mp4"
    frames = call["frames"]
    # 总长 = 最长一格（xhard12 的 9 帧），不拉伸
    assert len(frames) == 9

    u = egv.discover(root)[("BinFill", 7, 4701)]
    cells = egv.build_cells(u)
    labels = {c.level: c.label for c in cells}
    status = {c.level: c.status for c in cells}
    assert labels["mother"] == "mother (hard) | 100 timestep"
    assert labels["xhard12"] == "xhard12 | 168 timestep | x1.68"
    assert status["xhard14"] == egv.FAILED and labels["xhard14"].endswith("FAILED")
    assert cells[2].stream is not None  # 失败档用 FAILED_ 视频帧
    assert status["xhard16"] == egv.ABSENT and labels["xhard16"].endswith("NO OUTPUT")
    assert status["xhard18"] == egv.ABSENT
    assert labels["xhard20"] == "xhard20 | 250 timestep | x2.50"
    for c in cells:
        assert all(ord(ch) < 128 for ch in c.label)  # cv2.putText 只支持 ASCII

    # 画面几何：格子 = 最大帧 32x48；标签栏高度由原版 _add_text_to_frame 决定
    cell_h, cell_w, label_h = egv.grid_geometry(cells)
    assert (cell_h, cell_w) == (32, 48)
    assert label_h >= 50  # 原版标签栏最小 50 像素
    box_h = cell_h + label_h
    f0 = frames[0]
    assert f0.shape[0] % 16 == 0 and f0.shape[1] % 16 == 0
    assert f0.shape[0] >= 3 * box_h and f0.shape[1] >= 2 * cell_w
    for c in cells:
        if c.stream is not None:
            c.stream.close()

    def body(frame, idx):
        r, c = divmod(idx, 2)
        y0 = r * box_h + label_h
        return frame[y0 : y0 + cell_h, c * cell_w : (c + 1) * cell_w].astype(int)

    # 位置固定：0 母档 | 1 xhard12；2 xhard14 | 3 xhard16；4 xhard18 | 5 xhard20
    m = body(f0, 0)
    # 母档 16x32 原样放左上，不缩放：有效区是母档颜色，下方与右侧补黑
    assert np.abs(m[:16, :32].mean(axis=(0, 1)) - COLORS["mother"]).max() < 20
    assert m[18:, :].max() < 20
    assert m[:, 34:].max() < 20
    x12 = body(f0, 1)
    assert np.abs(x12.mean(axis=(0, 1)) - COLORS["xhard12"]).max() < 20
    x14 = body(f0, 2)
    assert np.abs(x14[:16, :32].mean(axis=(0, 1)) - COLORS["xhard14"]).max() < 20
    # 无产物格为灰底
    x18 = body(f0, 4)
    assert abs(np.median(x18) - egv.GRAY) < 5
    x20 = body(f0, 5)
    assert np.abs(x20[:16, :32].mean(axis=(0, 1)) - COLORS["xhard20"]).max() < 20

    # 短格停末帧：xhard20 只有 3 帧，第 8 帧仍是其颜色（末帧），而非黑屏
    last = frames[-1]
    assert np.abs(body(last, 5)[:16, :32].mean(axis=(0, 1)) - COLORS["xhard20"]).max() < 20
    # 结束后标签栏（追加 ENDED）与播放中不同；xhard12 最长，其标签栏全程不变
    def label_bar(frame, idx):
        r, c = divmod(idx, 2)
        return frame[r * box_h : r * box_h + label_h, c * cell_w : (c + 1) * cell_w]

    assert not np.array_equal(label_bar(frames[0], 5), label_bar(frames[-1], 5))
    assert np.array_equal(label_bar(frames[0], 1), label_bar(frames[-1], 1))


def test_ended_label_appears_exactly_after_last_frame(tmp_path):
    root = tmp_path / "root"
    _make_binfill_root(root)
    u = egv.discover(root)[("BinFill", 7, 4701)]
    cells = egv.build_cells(u)
    x20 = cells[5].stream
    seen = [x20.next() for _ in range(5)]
    assert [e for _, e in seen] == [False, False, False, True, True]
    assert x20.count == 3
    for c in cells:
        if c.stream is not None:
            c.stream.close()


def test_mother_only_task_keeps_grid_and_marks_missing_tier(tmp_path, recorded_writes):
    root = tmp_path / "root"
    _write(root / "mother/videos" / _vname("MoveCube", 7, 14700, "hard"), 2, 16, 32, COLORS["mother"])
    stats = egv.render_all(root, tmp_path / "out")
    assert stats == {**stats, "videos": 1, "cells": 6, "missing": 5}
    assert Path(recorded_writes[0]["path"]).name == "4.1_MoveCube_ep7_seed14700.mp4"
    cells = egv.build_cells(egv.discover(root)[("MoveCube", 7, 14700)])
    assert [c.status for c in cells] == [egv.OK] + [egv.MISSING] * 5
    assert cells[1].label == "xhard12 | MISSING TIER"
    cells[0].stream.close()


def test_task_seeds_filters_and_duplicate_candidates(tmp_path, recorded_writes):
    root = tmp_path / "root"
    _make_binfill_root(root)
    _write(root / "mother/videos" / _vname("MoveCube", 7, 14700, "hard"), 2, 16, 32, COLORS["mother"])
    egv.render_all(root, tmp_path / "out", task="MoveCube")
    assert [Path(c["path"]).name for c in recorded_writes] == ["4.1_MoveCube_ep7_seed14700.mp4"]
    recorded_writes.clear()
    manifest = {"tasks": {"BinFill": [{"episode": 7, "seed": 4701}]}}
    egv.render_all(root, tmp_path / "out", manifest=manifest)
    assert [Path(c["path"]).name for c in recorded_writes] == ["1.1_BinFill_ep7_seed4701.mp4"]

    # 同一档两个成功候选：报错，不猜
    _write(root / "xhard20/videos" / "BinFill_ep7_seed4701_xhard20_other_goal.mp4", 2, 16, 32, (0, 0, 0))
    with pytest.raises(ValueError, match="多个成功视频"):
        egv.build_cells(egv.discover(root)[("BinFill", 7, 4701)])


def test_main_prints_verdict(tmp_path, recorded_writes, capsys):
    root = tmp_path / "root"
    _make_binfill_root(root)
    assert egv.main(["--root", str(root), "--out-dir", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "EPISODE_GRID_VIDEO=PASS videos=1 cells=6 missing=2"


def test_real_write_uses_original_writer(tmp_path):
    """不 monkeypatch：真正走原版 _video_write_mp4 写出，读回帧数与尺寸。"""
    root = tmp_path / "root"
    _write(root / "mother/videos" / _vname("InsertPeg", 7, 13700, "hard"), 4, 16, 32, COLORS["mother"])
    stats = egv.render_all(root, tmp_path / "out")
    out = Path(stats["outputs"][0])
    assert out.name == "4.2_InsertPeg_ep7_seed13700.mp4"
    reader = imageio.get_reader(out.as_posix())
    frames = [np.asarray(f) for f in reader]
    reader.close()
    assert len(frames) == 4
    assert frames[0].shape[0] % 16 == 0 and frames[0].shape[1] == 64
