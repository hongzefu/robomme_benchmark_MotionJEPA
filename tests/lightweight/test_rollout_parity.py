"""固定键与同帧数错配的视频诊断，不把诊断状态混进 HDF5 判据。"""
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from scripts.injection.rollout.parity import check_keys, compare_video
from scripts.injection.rollout.state import ROOT


def test_key_gate_rejects_duplicate_missing_and_extra():
    expected = {("RouteStick", "easy", 0), ("RouteStick", "easy", 1)}
    row = {"task": "RouteStick", "difficulty": "easy", "episode": 0}
    result = check_keys(expected, [row, row], "L3")
    assert not result["passed"] and result["duplicates"] == 1 and result["missing"] == 1
    result = check_keys(expected, [row, {**row, "episode": 2}], "L3")
    assert not result["passed"] and result["extra"] == result["missing"] == 1


def test_equal_frame_count_does_not_hide_wrong_video():
    parent = ROOT / "artifacts/test-tmp"
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="video-parity-", dir=parent))
    for name, value in (("left", 0), ("right", 200)):
        writer = cv2.VideoWriter(str(root / f"{name}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 20, (64, 64))
        assert writer.isOpened()
        for _ in range(4):
            writer.write(np.full((64, 64, 3), value, dtype=np.uint8))
        writer.release()
    result = compare_video(root / "left.mp4", root / "right.mp4", root / "evidence", time.monotonic() + 30)
    assert result["status"] == "DIFFERENT"
    assert result["frames"] == [4, 4] and result["different_frames"] == 4
    assert result["complete_decode"] and result["first_difference"] == 0
    assert Path(result["left_copy"]).is_file() and Path(result["right_copy"]).is_file()
    assert (root / "evidence/left_first_difference.png").is_file()
    skipped = compare_video(root / "left.mp4", root / "right.mp4", root / "budget", time.monotonic() - 1)
    assert skipped["status"] == "NOT_RUN"
