#!/usr/bin/env python3
"""轻量测试：PickHighlight 的 V4 xhard 档（NEWTASK_RELEASE_V4_PLAN 2.12）。

纯结构性检查，不起 sapien 场景：

* 原三档 ``configs`` 与 ``_native_decision`` 去掉 xhard 后的部分逐字不变；
* xhard 新值：highlight ``[5,7]``、spawn ``[8,10]``，且 spawn 下界 ≥ highlight 上界；
* xhard 专属 decision 条目放在 ``xhard`` 子键下，守卫放行已申报条目的改值、拒绝申报外新键；
* 源码层面：xhard 分支的静默截断改抛 ``SceneGenerationError``、D4 只在 xhard 包 lambda、
  区间校验函数拒绝写坏的外部配置。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_pickhighlight.py -q
"""

from __future__ import annotations

import copy
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import importlib  # noqa: E402

module = importlib.import_module("robomme.robomme_env.PickHighlight")
from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    _strip_xhard,
    assert_native_decision,
)

CLS = module.PickHighlight

# 改动前（00e2ef4）的原三档与原值 decision，逐字抄录作对照
ORIGINAL_CONFIGS = {
    "hard": {"spawn": 6, "pickup": 3},
    "easy": {"spawn": 3, "pickup": 1},
    "medium": {"spawn": 4, "pickup": 2},
}
ORIGINAL_DECISION = {
    "layout_mode": "native_region",
    "cube_region": {"region_center": [-0.1, 0], "region_half_size": 0.2},
    "highlight_count": {"hard": 3, "easy": 1, "medium": 2},
    "spawn_count": {"hard": 6, "easy": 3, "medium": 4},
    "block_color_policy": "native_per_cube_uniform",
}


def test_原三档配置逐字不变() -> None:
    for difficulty, cfg in ORIGINAL_CONFIGS.items():
        assert CLS.configs[difficulty] == cfg


def test_xhard新值() -> None:
    assert CLS.configs["xhard"] == {"spawn": [8, 10], "pickup": [5, 7]}
    spawn_lo = CLS.configs["xhard"]["spawn"][0]
    highlight_hi = CLS.configs["xhard"]["pickup"][1]
    assert spawn_lo >= highlight_hi


def test_decision去掉xhard后与原值相同() -> None:
    decision, _native = module.native_blocks(CLS)
    assert _strip_xhard(decision) == ORIGINAL_DECISION


def test_decision的xhard条目结构() -> None:
    decision, _native = module.native_blocks(CLS)
    assert decision["highlight_count"]["xhard"] == [5, 7]
    assert decision["spawn_count"]["xhard"] == [8, 10]
    assert decision["xhard"] == {"block_color_policy": "uniform_rgb", "subgoal_color_suffix": "omit"}
    # 导出副本互不共享可变对象（外部改 decision 不能回写类属性）
    decision["spawn_count"]["xhard"][0] = 99
    assert CLS.configs["xhard"]["spawn"] == [8, 10]


def test_native块不变() -> None:
    _decision, native = module.native_blocks(CLS)
    assert native["positions"]["cubes"]["min_gap_factor"] == 2
    assert native["positions"]["cubes"]["region_half_size"] == 0.2
    assert native["positions"]["highlight_window"] == {"start_step": 10, "end_step": 100, "simultaneous": True}


def test_守卫放行已申报xhard条目改值() -> None:
    default, _ = module.native_blocks(CLS)
    for mutate in (
        lambda d: d["highlight_count"].__setitem__("xhard", [7, 7]),
        lambda d: d["spawn_count"].__setitem__("xhard", [8, 8]),
        lambda d: d["xhard"].__setitem__("subgoal_color_suffix", "omit"),
    ):
        decision = copy.deepcopy(default)
        mutate(decision)
        assert_native_decision(decision, default, "PickHighlight")


def test_守卫拒绝原三档改值与申报外新键() -> None:
    default, _ = module.native_blocks(CLS)
    for mutate in (
        lambda d: d["highlight_count"].__setitem__("hard", 4),
        lambda d: d.__setitem__("block_color_policy", "uniform_rgb"),
        lambda d: d["xhard"].__setitem__("distractor", {"count": 3}),
    ):
        decision = copy.deepcopy(default)
        mutate(decision)
        with pytest.raises(SamplingConfigError):
            assert_native_decision(decision, default, "PickHighlight")


def test_区间校验() -> None:
    assert module._closed_range([5, 7], "k") == (5, 7)
    for bad in (7, [7], [7, 5], [0, 3], [5.0, 7], [True, 2], "5,7"):
        with pytest.raises(SamplingConfigError):
            module._closed_range(bad, "k")


def test_源码xhard分支不静默截断且D4只在xhard修() -> None:
    src = inspect.getsource(CLS._load_scene)
    assert "SceneGenerationError" in src
    assert 'self._spec.record("objects.n_cubes_spawned"' in src
    assert "if spawn_lo < highlight_hi" in src
    # 原三档：按钮任务 failure_func 仍是构造时求值（D4 原样保留）；xhard：lambda
    assert "button_failure_func = is_any_obj_pickup(self,[cube for cube in self.all_cubes])" in src
    assert "button_failure_func = lambda: is_any_obj_pickup(self, [cube for cube in self.all_cubes])" in src
    # 原三档的 break 静默截断仍在（H2：原三档行为不变）
    assert "break" in src
