#!/usr/bin/env python3
"""轻量测试：V4 步 3b SwingXtimes 的 xhard 档（docs/plans/0922-newtask-release-v4-plan.md 2.5）。

纯 CPU、不起 sapien 场景，只验结构：
* 原三档 ``configs`` 与 decision 可见部分（去掉 xhard 键后）逐字不变；
* xhard 新值：number [4,10]、color 3、三个干扰色；
* 守卫放行 number 端点收窄，拒绝改原三档与申报外键；
* 干扰色**没有**并入 ``native.color_pool``（并入会平移原三档 randperm）。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_swingxtimes.py -q
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
from robomme.robomme_env.utils.xhard import DISTRACTOR_COLORS  # noqa: E402

MOD = importlib.import_module("robomme.robomme_env.SwingXtimes")
CLS = MOD.SwingXtimes

ORIGINAL_CONFIGS = {
    "hard": {"color": 3, "number_min": 3, "number_max": 3},
    "easy": {"color": 1, "number_min": 1, "number_max": 3},
    "medium": {"color": 3, "number_min": 1, "number_max": 2},
}
ORIGINAL_DECISION = {
    "number_range": {"hard": [3, 3], "easy": [1, 3], "medium": [1, 2]},
    "color": {"hard": 3, "easy": 1, "medium": 3},
    "distractor": None,
}


def test_original_three_configs_unchanged() -> None:
    for difficulty, expected in ORIGINAL_CONFIGS.items():
        assert CLS.configs[difficulty] == expected
    # V6（计划 2.8）：新增 xhard1/2/3，共 7 档
    assert set(CLS.configs) == {"easy", "medium", "hard", "xhard4", "xhard1", "xhard2", "xhard3"}
    assert list(CLS.configs)[:4] == ["hard", "easy", "medium", "xhard4"]


def test_xhard_config_values() -> None:
    assert CLS.configs["xhard4"] == {"color": 3, "number_min": 10, "number_max": 11}


def test_decision_visible_part_unchanged() -> None:
    decision, _ = MOD.native_blocks(CLS)
    assert _strip_xhard(decision) == ORIGINAL_DECISION


def test_decision_xhard_entries() -> None:
    decision, _ = MOD.native_blocks(CLS)
    assert decision["number_range"]["xhard4"] == [10, 11]
    assert decision["color"]["xhard4"] == 3
    # V5 S3f（计划 2.14）：新增 min_center_dist_m（L44）
    assert set(decision["xhard4"]) == {"distractor", "min_center_dist_m"}
    assert decision["xhard4"]["min_center_dist_m"] == 0.08
    dcfg = decision["xhard4"]["distractor"]
    assert dcfg["colors"] == [entry["name"] for entry in DISTRACTOR_COLORS] == ["yellow", "cyan", "magenta"]
    # 干扰方块区域沿用原方块区域
    _, native = MOD.native_blocks(CLS)
    assert dcfg["region_center"] == native["positions"]["cubes"]["region_center"]
    assert dcfg["region_half_size"] == native["positions"]["cubes"]["region_half_size"]


def test_distractor_colors_not_merged_into_color_pool() -> None:
    _, native = MOD.native_blocks(CLS)
    assert [entry["name"] for entry in native["parameters"]["color_pool"]] == ["red", "blue", "green"]


@pytest.mark.parametrize("value", [[4, 4], [10, 10], [4, 10]])
def test_guard_allows_number_endpoints(value) -> None:
    default, native = MOD.native_blocks(CLS)
    decision = copy.deepcopy(default)
    decision["number_range"]["xhard4"] = value
    resolved = MOD._resolve_sampling_config(CLS, {"decision": decision, "native": native})
    assert resolved["decision"]["number_range"]["xhard4"] == value


@pytest.mark.parametrize("mutate", [
    lambda d: d["number_range"].__setitem__("hard", [3, 4]),
    lambda d: d.__setitem__("distractor", {"colors": ["yellow"]}),
    lambda d: d["xhard4"].__setitem__("corner_bias", 1.0),
])
def test_guard_rejects_original_or_undeclared(mutate) -> None:
    default, _ = MOD.native_blocks(CLS)
    decision = copy.deepcopy(default)
    mutate(decision)
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, default, "SwingXtimes")


class _FakePose:
    def __init__(self, xyz):
        self.p = torch.tensor([xyz], dtype=torch.float32)


class _FakeActor:
    def __init__(self, xyz):
        self.pose = _FakePose(xyz)


def test_disk_avoid_obb_shape() -> None:
    c, axes, half = MOD._disk_avoid_obb(_FakeActor([-0.1, 0.2, 0.005]), 0.04)
    assert isinstance(c, np.ndarray) and isinstance(axes, np.ndarray)
    assert np.allclose(c, [-0.1, 0.2]) and np.allclose(half, [0.04, 0.04])


# ---------------------------------------------------------------------------
# V6（计划 2.8）：新值族 xhard1/2/3——次数区间内插、干扰块数 1/2/3（DISTRACTOR_COLORS 前 k 个），其余字段沿用 xhard
# ---------------------------------------------------------------------------
V6_NUMBER_RANGE = {'xhard1': (4, 5), 'xhard2': (6, 7), 'xhard3': (8, 9), 'xhard4': (10, 11)}
V6_DISTRACTOR_COUNT = {"xhard1": 1, "xhard2": 2, "xhard3": 3, "xhard4": min(4, len(DISTRACTOR_COLORS))}


@pytest.mark.parametrize("tier", ["xhard1", "xhard2", "xhard3"])
def test_v6_newvalue_config_values(tier) -> None:
    lo, hi = V6_NUMBER_RANGE[tier]
    assert CLS.configs[tier] == {"color": 3, "number_min": lo, "number_max": hi}


@pytest.mark.parametrize("tier", ["xhard1", "xhard2", "xhard3", "xhard4"])
def test_v6_newvalue_decision_subtree(tier) -> None:
    decision, _ = MOD.native_blocks(CLS)
    # 键结构与 xhard 完全相同；只有干扰色列表按档截取前 k 个
    assert set(decision[tier]) == set(decision["xhard4"])
    k = V6_DISTRACTOR_COUNT[tier]
    assert decision[tier]["distractor"]["colors"] == [entry["name"] for entry in DISTRACTOR_COLORS[:k]]
    other = {key: value for key, value in decision[tier].items() if key != "distractor"}
    assert other == {key: value for key, value in decision["xhard4"].items() if key != "distractor"}
    dcfg = {key: value for key, value in decision[tier]["distractor"].items() if key != "colors"}
    assert dcfg == {key: value for key, value in decision["xhard4"]["distractor"].items() if key != "colors"}
    lo, hi = V6_NUMBER_RANGE[tier]
    assert decision["number_range"][tier] == [lo, hi]
    assert decision["color"][tier] == 3


def test_v6_partial_snapshot_with_xhard4_is_filled() -> None:
    """只有已有 xhard4 的 V6 决策块才自动补齐 xhard1/2/3。"""
    decision, native = MOD.native_blocks(CLS)
    old = copy.deepcopy(decision)
    for tier in ("xhard1", "xhard2", "xhard3"):
        old.pop(tier)
        old["number_range"].pop(tier)
        old["color"].pop(tier)
    resolved = MOD._resolve_sampling_config(CLS, {"decision": old, "native": native})
    assert resolved["decision"]["xhard1"] == decision["xhard1"]
    assert resolved["decision"]["xhard4"] == decision["xhard4"]
