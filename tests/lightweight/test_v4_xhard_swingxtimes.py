#!/usr/bin/env python3
"""轻量测试：V4 步 3b SwingXtimes 的 xhard 档（NEWTASK_RELEASE_V4_PLAN 2.5）。

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
    assert set(CLS.configs) == {"easy", "medium", "hard", "xhard"}


def test_xhard_config_values() -> None:
    assert CLS.configs["xhard"] == {"color": 3, "number_min": 4, "number_max": 10}


def test_decision_visible_part_unchanged() -> None:
    decision, _ = MOD.native_blocks(CLS)
    assert _strip_xhard(decision) == ORIGINAL_DECISION


def test_decision_xhard_entries() -> None:
    decision, _ = MOD.native_blocks(CLS)
    assert decision["number_range"]["xhard"] == [4, 10]
    assert decision["color"]["xhard"] == 3
    # V5 S3f（计划 2.14）：新增 min_center_dist_m（L44）
    assert set(decision["xhard"]) == {"distractor", "min_center_dist_m"}
    assert decision["xhard"]["min_center_dist_m"] == 0.08
    dcfg = decision["xhard"]["distractor"]
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
    decision["number_range"]["xhard"] = value
    resolved = MOD._resolve_sampling_config(CLS, {"decision": decision, "native": native})
    assert resolved["decision"]["number_range"]["xhard"] == value


@pytest.mark.parametrize("mutate", [
    lambda d: d["number_range"].__setitem__("hard", [3, 4]),
    lambda d: d.__setitem__("distractor", {"colors": ["yellow"]}),
    lambda d: d["xhard"].__setitem__("corner_bias", 1.0),
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
