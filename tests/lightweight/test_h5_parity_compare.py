#!/usr/bin/env python3
"""轻量测试：HDF5 全字段逐位对拍器的正例与反例（不加载仿真、不占 GPU）。

对应 NEWTASK_RELEASE_V3_PLAN.md 第二部分「十一」的 `compare_h5_pair`：
两层比较（先整文件 SHA-256、不同再逐字段）、浮点按位模式不设容差、
缺失／额外路径与 dtype／shape 变化必须被抓到、时间步数不同先记差异再比共有步。

    uv run --no-sync python -m pytest tests/lightweight/test_h5_parity_compare.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
# 对拍链路已迁入 scripts/parity/；seed_layout 仍在 scripts/ 顶层，两处都要进 sys.path。
SCRIPTS_DIR = REPO_ROOT / "scripts"
for _entry in (SCRIPTS_DIR, SCRIPTS_DIR / "parity"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import train_split_parity as parity  # noqa: E402


def _write(path: Path, *, joint=None, steps: int = 2, rgb_seed: int = 0, extra: bool = False,
           joint_dtype="float64", text: str = "put_in") -> Path:
    """造一份结构与真实产物同形的小 HDF5（setup + 若干 timestep）。"""
    rng = np.random.default_rng(rgb_seed)
    with h5py.File(path, "w") as handle:
        setup = handle.create_group("episode_0/setup")
        setup.create_dataset("seed", data=np.int64(4000))
        setup.create_dataset("front_camera_intrinsic", data=np.eye(3, dtype=np.float32))
        setup.create_dataset("task_goal", data=text)
        for index in range(steps):
            group = handle.create_group(f"episode_0/timestep_{index}")
            values = np.arange(8, dtype=joint_dtype) + index if joint is None else np.asarray(joint, dtype=joint_dtype)
            group.create_dataset("action/joint_action", data=values)
            group.create_dataset(
                "obs/front_rgb", data=rng.integers(0, 255, size=(4, 4, 3), dtype=np.uint8)
            )
            group.create_dataset("info/is_completed", data=np.bool_(index == steps - 1))
            group.create_dataset("info/grounded_subgoal", data=text)
            if extra:
                group.create_dataset("obs/extra_channel", data=np.zeros(3, dtype=np.float32))
    return path


def test_identical_files_short_circuit_on_sha(tmp_path: Path) -> None:
    left = _write(tmp_path / "a.h5")
    right = _write(tmp_path / "b.h5")
    result = parity.compare_h5_pair(left, right)
    assert result["sha_equal"] == 1
    assert result["field_mismatch"] == 0
    assert result["left_sha256"] == result["right_sha256"]
    # 散列相同即返回，不再打开文件，因此不产生逐字段记录。
    assert result["mismatches"] == []


def test_float_bit_difference_is_caught_without_tolerance(tmp_path: Path) -> None:
    """浮点差到 1 个 ULP 也必须判不同——注入前后不设容差。"""
    base = np.arange(8, dtype=np.float64)
    nudged = base.copy()
    nudged[5] = np.nextafter(nudged[5], np.inf)
    left = _write(tmp_path / "a.h5", joint=base)
    right = _write(tmp_path / "b.h5", joint=nudged)
    result = parity.compare_h5_pair(left, right)
    assert result["sha_equal"] == 0
    assert result["field_mismatch"] > 0
    paths = [item["path"] for item in result["mismatches"]]
    assert any(path.endswith("action/joint_action") for path in paths)
    hit = next(item for item in result["mismatches"] if item["path"].endswith("action/joint_action"))
    assert hit["kind"] == "value"
    assert hit["first_diff_index"] == 5


def test_nan_bit_pattern_compares_equal_to_itself(tmp_path: Path) -> None:
    payload = np.array([np.nan] * 8, dtype=np.float64)
    left = _write(tmp_path / "a.h5", joint=payload)
    right = _write(tmp_path / "b.h5", joint=payload)
    result = parity.compare_h5_pair(left, right)
    assert result["field_mismatch"] == 0


def test_dtype_change_is_caught(tmp_path: Path) -> None:
    left = _write(tmp_path / "a.h5")
    right = _write(tmp_path / "b.h5", joint_dtype="float32")
    result = parity.compare_h5_pair(left, right)
    mismatches = [item for item in result["mismatches"] if item["kind"] == "dtype_or_shape"]
    assert mismatches
    assert mismatches[0]["left_dtype"] == "float64"
    assert mismatches[0]["right_dtype"] == "float32"


def test_extra_and_missing_paths_are_counted(tmp_path: Path) -> None:
    left = _write(tmp_path / "a.h5")
    right = _write(tmp_path / "b.h5", extra=True)
    result = parity.compare_h5_pair(left, right)
    assert result["missing_left"]  # 右边多出的路径
    assert all("extra_channel" in name for name in result["missing_left"])
    assert result["field_mismatch"] >= len(result["missing_left"])


def test_timestep_count_difference_is_recorded_not_truncated(tmp_path: Path) -> None:
    left = _write(tmp_path / "a.h5", steps=2)
    right = _write(tmp_path / "b.h5", steps=3)
    result = parity.compare_h5_pair(left, right)
    assert result["timestep_count"] == {"left": 2, "right": 3}
    # 帧数不同单独计一次，且多出的时间步进入缺失路径清单，不被静默截断。
    assert result["field_mismatch"] > 0
    assert any("timestep_2" in name for name in result["missing_left"])


def test_object_string_dataset_difference_is_caught(tmp_path: Path) -> None:
    left = _write(tmp_path / "a.h5", text="put_in")
    right = _write(tmp_path / "b.h5", text="pick_up")
    result = parity.compare_h5_pair(left, right)
    paths = [item["path"] for item in result["mismatches"]]
    assert any(path.endswith("setup/task_goal") for path in paths)
    assert any(path.endswith("info/grounded_subgoal") for path in paths)


def test_attributes_are_compared(tmp_path: Path) -> None:
    left = _write(tmp_path / "a.h5")
    right = _write(tmp_path / "b.h5")
    with h5py.File(right, "a") as handle:
        handle["episode_0/setup"].attrs["note"] = "changed"
    result = parity.compare_h5_pair(left, right)
    assert any(item["kind"] == "attr_keys" for item in result["mismatches"])
