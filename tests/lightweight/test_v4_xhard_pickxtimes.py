#!/usr/bin/env python3
"""轻量测试：V4 步 3b PickXtimes 的 xhard 档（NEWTASK_RELEASE_V4_PLAN 2.4 / 2.21）。

纯 CPU、不起 sapien 场景，只验结构：
* 原三档 ``configs`` 与 decision 可见部分（去掉 xhard 键后）逐字不变；
* xhard 新值：num [6,15]、color 3、独立圆盘区域、三个干扰色（V5 S3f：corner_bias 已删、方块区半宽 0.25、
  新增 min_center_dist_m，断言已改为 V5 语义，详见 tests/lightweight/test_v5_xhard_pickswing.py）；
* 守卫放行 xhard 条目的收窄（口径 14 端点单测、V5 中心距取值），拒绝改原三档；
* 原值快照 ``NATIVE_SAMPLING`` 不被改（颜色池仍只有红蓝绿）；
* 圆盘预制 OBB 的形态能被 ``spawn_random_cube`` 的 avoid 识别；
* 序数表覆盖 num=15 的最后一次抓取。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_pickxtimes.py -q
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    _strip_xhard,
    assert_native_decision,
)
from robomme.robomme_env.utils.subgoal_language import get_subgoal_with_index  # noqa: E402
from robomme.robomme_env.utils.xhard import DISTRACTOR_COLORS  # noqa: E402

MOD = importlib.import_module("robomme.robomme_env.PickXtimes")
CLS = MOD.PickXtimes

# 改动前（00e2ef4）的原三档与 decision 原值，逐字抄录
ORIGINAL_CONFIGS = {
    "hard": {"color": 3, "number_min": 4, "number_max": 5},
    "easy": {"color": 1, "number_min": 1, "number_max": 3},
    "medium": {"color": 3, "number_min": 1, "number_max": 3},
}
ORIGINAL_DECISION = {
    "color": {"hard": 3, "easy": 1, "medium": 3},
    "number_range": {"hard": [4, 5], "easy": [1, 3], "medium": [1, 3]},
    "target_cube_position_policy": {"region_center": [-0.1, 0], "region_half_size": 0.2},
    "goal_position_policy": {"region_center": [-0.1, 0], "region_half_size": 0.2},
    "distractor": None,
}


def test_original_three_configs_unchanged() -> None:
    for difficulty, expected in ORIGINAL_CONFIGS.items():
        assert CLS.configs[difficulty] == expected
    assert set(CLS.configs) == {"easy", "medium", "hard", "xhard"}


def test_xhard_config_values() -> None:
    assert CLS.configs["xhard"] == {"color": 3, "number_min": 6, "number_max": 15}


def test_decision_visible_part_unchanged() -> None:
    decision, _ = MOD.native_blocks(CLS)
    assert _strip_xhard(decision) == ORIGINAL_DECISION


def test_decision_xhard_entries() -> None:
    decision, _ = MOD.native_blocks(CLS)
    assert decision["number_range"]["xhard"] == [6, 15]
    assert decision["color"]["xhard"] == 3
    xhard = decision["xhard"]
    # V5 S3f（计划 2.13）：新增 min_center_dist_m（L44）；删 corner_bias（L43）；方块区半宽 0.25（L46）
    assert set(xhard) == {"target_cube_position_policy", "goal_position_policy", "distractor", "min_center_dist_m"}
    cube = xhard["target_cube_position_policy"]
    assert cube == {"region_center": [-0.1, 0], "region_half_size": 0.25}
    assert xhard["min_center_dist_m"] == 0.08
    # C1：圆盘区域独立一套（值沿用原区域，允许留在中间）
    assert xhard["goal_position_policy"] == {"region_center": [-0.1, 0], "region_half_size": 0.2}
    assert xhard["goal_position_policy"] is not decision["goal_position_policy"]
    # A5/B2：固定三个干扰色，顺序与共用色池一致
    assert xhard["distractor"]["colors"] == [entry["name"] for entry in DISTRACTOR_COLORS]
    assert xhard["distractor"]["colors"] == ["yellow", "cyan", "magenta"]


def test_native_snapshot_unchanged() -> None:
    _, native = MOD.native_blocks(CLS)
    assert [entry["name"] for entry in native["parameters"]["color_pool"]] == ["red", "blue", "green"]
    assert native["parameters"]["cubes_per_color"] == 1
    assert native["positions"]["target_pose"]["radius_factor"] == 2
    assert native["positions"]["target_pose"]["min_gap_factor"] == 2


def test_native_blocks_are_independent_copies() -> None:
    first, _ = MOD.native_blocks(CLS)
    first["xhard"]["target_cube_position_policy"]["region_half_size"] = 0.123
    second, _ = MOD.native_blocks(CLS)
    assert second["xhard"]["target_cube_position_policy"]["region_half_size"] != 0.123


@pytest.mark.parametrize("mutate", [
    lambda d: d["number_range"].__setitem__("xhard", [6, 6]),
    lambda d: d["number_range"].__setitem__("xhard", [15, 15]),
    lambda d: d["xhard"].__setitem__("min_center_dist_m", 0.06),
    lambda d: d["xhard"].__setitem__("min_center_dist_m", 0.10),
])
def test_guard_allows_declared_xhard_narrowing(mutate) -> None:
    default, _ = MOD.native_blocks(CLS)
    decision = copy.deepcopy(default)
    mutate(decision)
    assert_native_decision(decision, default, "PickXtimes")
    # 真实解析入口同样放行
    _, native = MOD.native_blocks(CLS)
    resolved = MOD._resolve_sampling_config(CLS, {"decision": decision, "native": native})
    assert resolved["decision"] == decision


@pytest.mark.parametrize("mutate", [
    lambda d: d["number_range"].__setitem__("hard", [4, 6]),
    lambda d: d.__setitem__("distractor", {"colors": ["yellow"]}),
    lambda d: d["target_cube_position_policy"].__setitem__("corner_bias", 1.0),
    lambda d: d["xhard"].__setitem__("spawn_order", "goal_first"),
    # V5 S3f：corner_bias 已删（L43），再塞回 xhard 属于申报外的键
    lambda d: d["xhard"]["target_cube_position_policy"].__setitem__("corner_bias", 0.5),
])
def test_guard_rejects_original_or_undeclared(mutate) -> None:
    default, _ = MOD.native_blocks(CLS)
    decision = copy.deepcopy(default)
    mutate(decision)
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, default, "PickXtimes")


class _FakePose:
    def __init__(self, xyz):
        self.p = torch.tensor([xyz], dtype=torch.float32)


class _FakeActor:
    def __init__(self, xyz):
        self.pose = _FakePose(xyz)


def test_disk_avoid_obb_shape() -> None:
    c, axes, half = MOD._disk_avoid_obb(_FakeActor([0.05, -0.1, 0.005]), 0.06)
    # spawn_random_cube 的 avoid 只认「三元组且前两项是 ndarray」为预制 OBB
    assert isinstance(c, np.ndarray) and isinstance(axes, np.ndarray)
    assert np.allclose(c, [0.05, -0.1]) and np.allclose(axes, np.eye(2)) and np.allclose(half, [0.06, 0.06])


def test_subgoal_ordinal_covers_num_15() -> None:
    assert get_subgoal_with_index(14, "{idx}") == "fifteenth"
    assert get_subgoal_with_index(5, "{idx}") == "sixth"
