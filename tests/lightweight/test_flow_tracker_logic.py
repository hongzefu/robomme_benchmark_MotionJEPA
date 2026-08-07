"""flow 采集与落盘的纯逻辑把关测试。

覆盖三件不需要仿真也能验证、但错了会静默污染整份数据集的事：

1. **compound dtype 的结构与哨兵语义**：字段名、dtype、以及 bool / NaN 能否在 h5 里原样往返。
2. **位移的 NaN 规则**：末帧、断点、深度非正三种情况必须写 NaN，其余必须写真实差分。
   这条最容易出错——断点两侧的差分是假位移，一旦漏判就会往数据集里掺进物理上不存在的运动。
3. **断点判定本身**：`elapsed_steps` 差不等于 1（中间隔了 `NO RECORD` 段），或 `is_video_demo`
   翻转（demo 与执行相位之间发生过场景重置）。

本文件是纯 numpy / h5py 计算，不需要 GPU 也不需要仿真，因此不标 gpu marker，会进默认档。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import h5py
import numpy as np
import pytest

from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]


def _load_module(module_name: str, relative_path: str):
    repo_root = find_repo_root(__file__)
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 必须先注册进 sys.modules 再执行：@dataclass 装饰器会通过 cls.__module__
    # 回查 sys.modules 来解析类型注解，模块不在表里就会挂
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


flow_mod = _load_module(
    "flow_tracker_under_test",
    "scripts/data-generation-v2/flow_tracker.py",
)


EXPECTED_FIELDS = (
    "pos_3d",
    "pos_2d_uv",
    "pos_2d_yx",
    "z_cam",
    "in_frame",
    "seg_pixel_count",
    "point_unoccluded",
    "flow_2d_uv",
    "flow_2d_yx",
)


def _frame(
    elapsed_steps: int,
    is_video_demo: bool,
    uv: tuple[float, float] | None,
    key: str = "cube__7",
) -> dict:
    """造一个逐帧采集结果；uv 传 None 表示深度非正（不可投影）。"""
    if uv is None:
        record = {
            "pos_3d": np.zeros(3, dtype=np.float64),
            "pos_2d_uv": np.full(2, np.nan, dtype=np.float64),
            "pos_2d_yx": np.full(2, -1, dtype=np.int32),
            "z_cam": float("nan"),
            "in_frame": False,
            "seg_pixel_count": 0,
            "point_unoccluded": False,
        }
    else:
        record = {
            "pos_3d": np.asarray([0.1, 0.2, 0.3], dtype=np.float64),
            "pos_2d_uv": np.asarray(uv, dtype=np.float64),
            "pos_2d_yx": np.asarray(
                [int(np.rint(uv[1])), int(np.rint(uv[0]))], dtype=np.int32
            ),
            "z_cam": 0.5,
            "in_frame": True,
            "seg_pixel_count": 42,
            "point_unoccluded": True,
        }
    return {
        "elapsed_steps": elapsed_steps,
        "is_video_demo": is_video_demo,
        "records": {key: record},
    }


def test_flow_dtype_field_layout():
    """字段名与形状是数据集的对外契约，改动必须是有意识的。"""
    dtype = flow_mod.FLOW_DTYPE
    assert dtype.names == EXPECTED_FIELDS
    assert dtype["pos_3d"].shape == (3,)
    assert dtype["pos_2d_uv"].shape == (2,)
    assert dtype["pos_2d_yx"].shape == (2,)
    assert dtype["pos_2d_yx"].base == np.dtype(np.int32)
    assert dtype["in_frame"] == np.dtype(bool)
    assert dtype["point_unoccluded"] == np.dtype(bool)
    assert flow_mod.FLOW_SCHEMA_VERSION == "flow-2d-v1"


def test_compound_record_roundtrips_through_h5():
    """bool 字段与 NaN 哨兵必须能原样存进 h5 再读回来。"""
    record = np.zeros((), dtype=flow_mod.FLOW_DTYPE)
    record["pos_3d"] = [1.5, -2.5, 0.25]
    record["pos_2d_uv"] = [12.75, 200.5]
    record["pos_2d_yx"] = [201, 13]
    record["z_cam"] = 0.87
    record["in_frame"] = True
    record["seg_pixel_count"] = 4231
    record["point_unoccluded"] = False
    record["flow_2d_uv"] = [np.nan, np.nan]
    record["flow_2d_yx"] = [0.5, -0.25]

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "roundtrip.h5"
        with h5py.File(path, "w") as handle:
            handle.create_dataset("flow/cube__7", data=record)
        with h5py.File(path, "r") as handle:
            restored = handle["flow/cube__7"][()]

    assert restored.dtype.names == EXPECTED_FIELDS
    assert bool(restored["in_frame"]) is True
    assert bool(restored["point_unoccluded"]) is False
    assert np.all(np.isnan(restored["flow_2d_uv"]))
    for name in EXPECTED_FIELDS:
        assert np.array_equal(restored[name], record[name], equal_nan=True), name


def test_breakpoint_detection():
    """两种断点：elapsed_steps 不连续、demo 相位翻转。"""
    base = _frame(10, False, (100.0, 100.0))

    assert not flow_mod._is_breakpoint(base, _frame(11, False, (101.0, 100.0)))
    # NO RECORD 段：中间隔了未记录的物理步
    assert flow_mod._is_breakpoint(base, _frame(18, False, (101.0, 100.0)))
    # 相邻记录帧步数倒退也算断点
    assert flow_mod._is_breakpoint(base, _frame(10, False, (101.0, 100.0)))
    # demo -> 执行相位切换，中间发生过场景重置
    assert flow_mod._is_breakpoint(base, _frame(11, True, (101.0, 100.0)))


def test_flow_is_real_difference_on_contiguous_frames():
    """连续帧之间必须写真实差分，且两套轴序互相对应。"""
    frames = [
        _frame(1, False, (100.0, 50.0)),
        _frame(2, False, (103.5, 48.25)),
        _frame(3, False, (104.0, 48.00)),
    ]
    built = flow_mod.build_frame_arrays(frames, ["cube__7"])

    first = built[0]["cube__7"]
    assert np.allclose(first["flow_2d_uv"], [3.5, -1.75])
    # yx 轴序就是 uv 的两个分量互换
    assert np.allclose(first["flow_2d_yx"], [-1.75, 3.5])

    second = built[1]["cube__7"]
    assert np.allclose(second["flow_2d_uv"], [0.5, -0.25])


def test_flow_is_nan_on_last_frame():
    """末帧没有「下一个记录帧」，位移必须是 NaN 而不是 0。"""
    frames = [_frame(1, False, (10.0, 10.0)), _frame(2, False, (11.0, 10.0))]
    built = flow_mod.build_frame_arrays(frames, ["cube__7"])
    assert np.all(np.isnan(built[-1]["cube__7"]["flow_2d_uv"]))
    assert np.all(np.isnan(built[-1]["cube__7"]["flow_2d_yx"]))


def test_flow_is_nan_across_breakpoint():
    """断点两侧的差分是假位移，必须写 NaN。"""
    frames = [
        _frame(1, False, (10.0, 10.0)),
        _frame(9, False, (200.0, 200.0)),  # elapsed_steps 跳变 = NO RECORD 段
        _frame(10, True, (201.0, 200.0)),  # demo 相位翻转 = 场景重置
    ]
    built = flow_mod.build_frame_arrays(frames, ["cube__7"])
    assert np.all(np.isnan(built[0]["cube__7"]["flow_2d_uv"])), "NO RECORD 段两侧应为 NaN"
    assert np.all(np.isnan(built[1]["cube__7"]["flow_2d_uv"])), "相位翻转两侧应为 NaN"


def test_flow_is_nan_when_either_frame_is_unprojectable():
    """深度非正的帧参与的差分必须是 NaN。

    ManiSkill 会把尚未登场的物体藏到 (10, 10, 10) 附近，藏匿期间深度为负；从藏匿到登场
    那一帧的「位移」是纯粹的瞬移假象，靠这条规则自动屏蔽。
    """
    frames = [
        _frame(1, False, None),  # 藏匿中
        _frame(2, False, (120.0, 120.0)),  # 登场
        _frame(3, False, (120.5, 120.0)),
    ]
    built = flow_mod.build_frame_arrays(frames, ["cube__7"])
    assert np.all(np.isnan(built[0]["cube__7"]["flow_2d_uv"])), "藏匿→登场应为 NaN"
    assert np.allclose(built[1]["cube__7"]["flow_2d_uv"], [0.5, 0.0]), "登场之后应是真实位移"


def test_key_naming_and_exclusion_reasons():
    """key 规则与剔除原因是可回溯性的基础。"""
    assert flow_mod._make_key("button_cap", 19) == "button_cap__19"
    assert flow_mod._make_key("panda_hand_tcp", -1) == "panda_hand_tcp__-1"
    assert flow_mod.REASON_ROBOT_LINK == "robot_link"
    assert flow_mod.REASON_BACKGROUND == "background_prop"
    assert "table-workspace" in flow_mod.DEFAULT_BACKGROUND_NAMES
    assert "ground" in flow_mod.DEFAULT_BACKGROUND_NAMES


def test_write_flow_groups_rejects_frame_count_mismatch():
    """flow 帧数与 timestep 数对不上时必须报错，不能猜着对齐。"""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "mismatch.h5"
        with h5py.File(path, "w") as handle:
            episode = handle.create_group("episode_0")
            episode.create_group("setup")
            for index in range(3):
                episode.create_group(f"timestep_{index}")

            meta = {"schema_version": flow_mod.FLOW_SCHEMA_VERSION, "objects": [], "excluded": []}
            with pytest.raises(ValueError, match="不一致"):
                flow_mod.write_flow_groups(
                    episode,
                    [_frame(1, False, (1.0, 1.0)), _frame(2, False, (2.0, 2.0))],
                    meta,
                )


def test_write_flow_groups_rejects_missing_capture():
    """有记录帧没采集到 flow 时必须报错，否则会写出错位的数据。"""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "missing.h5"
        with h5py.File(path, "w") as handle:
            episode = handle.create_group("episode_0")
            episode.create_group("setup")
            episode.create_group("timestep_0")

            meta = {"schema_version": flow_mod.FLOW_SCHEMA_VERSION, "objects": [], "excluded": []}
            with pytest.raises(ValueError, match="没有采集到 flow"):
                flow_mod.write_flow_groups(episode, [None], meta)
