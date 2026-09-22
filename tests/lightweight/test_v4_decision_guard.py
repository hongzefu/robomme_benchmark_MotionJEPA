#!/usr/bin/env python3
"""轻量测试：V4 步 2 的 decision 守卫分叉（NEWTASK_RELEASE_V4_PLAN 3.5）。

* 原三档可见的部分（去掉全部 ``xhard`` 键之后）仍须与原值逐键相同；
* 只允许偏离源码里已申报的 ``xhard`` 条目，不许新增申报外的 ``xhard`` 键；
* v2/v3 旧快照（还没有 ``xhard`` 条目）照旧放行。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_decision_guard.py -q
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    assert_native_decision,
)

DEFAULT = {
    "color": {"easy": 1, "medium": 3, "hard": 3, "xhard": 3},
    "number_range": {"easy": [1, 3], "hard": [4, 5], "xhard": [6, 15]},
    "distractor": None,
    "xhard": {"distractor": {"count": 3}, "corner_bias": 0.5},
}


def test_identical_decision_passes() -> None:
    assert_native_decision(copy.deepcopy(DEFAULT), DEFAULT, "T")


def test_declared_xhard_entries_may_change() -> None:
    decision = copy.deepcopy(DEFAULT)
    decision["number_range"]["xhard"] = [15, 15]
    decision["xhard"]["corner_bias"] = 1.0
    assert_native_decision(decision, DEFAULT, "T")


def test_original_three_must_not_change() -> None:
    for mutate in (
        lambda d: d["number_range"].__setitem__("hard", [4, 6]),
        lambda d: d.__setitem__("distractor", {"count": 3}),
        lambda d: d["color"].pop("easy"),
    ):
        decision = copy.deepcopy(DEFAULT)
        mutate(decision)
        with pytest.raises(SamplingConfigError):
            assert_native_decision(decision, DEFAULT, "T")


def test_undeclared_or_missing_xhard_key_rejected() -> None:
    # xhard 子树下多出申报外的键 → 拒绝
    decision = copy.deepcopy(DEFAULT)
    decision["xhard"]["colors"] = ["yellow"]
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, DEFAULT, "T")
    # 缺少申报过的 xhard 键 → 拒绝（环境查表会 KeyError，提前在守卫处挡住）
    decision = copy.deepcopy(DEFAULT)
    decision["number_range"].pop("xhard")
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, DEFAULT, "T")
    # 原值部分里冒出新的 xhard 节点 → 去掉 xhard 后多出空字典，被原值比对拒绝
    decision = copy.deepcopy(DEFAULT)
    decision["goal"] = {"xhard": 1}
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, DEFAULT, "T")


def test_legacy_snapshot_without_xhard_passes() -> None:
    legacy = {
        "color": {"easy": 1, "medium": 3, "hard": 3},
        "number_range": {"easy": [1, 3], "hard": [4, 5]},
        "distractor": None,
    }
    assert_native_decision(legacy, DEFAULT, "T")
