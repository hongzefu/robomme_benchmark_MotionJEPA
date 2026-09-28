# robomme_hard：本测试测新值档／改动行为，阶段 3 起 src/robomme 回到官方 1fadc0ec，故改测 robomme_hard（0927 计划 R8 第③类）
#!/usr/bin/env python3
"""轻量测试：decision 守卫的原三档冻结与 V6 新值族结构校验。

* 原三档可见部分（去掉全部新值档键之后）仍须与原值逐键相同；
* 已申报的新值档只允许改值，不许增删申报的档内键；
* 不含新值档的历史快照照旧放行。

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

from robomme_hard.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    assert_native_decision,
)

DEFAULT = {
    "color": {
        "easy": 1, "medium": 3, "hard": 3,
        "xhard1": 3, "xhard2": 3, "xhard3": 3, "xhard4": 3,
    },
    "number_range": {
        "easy": [1, 3], "hard": [4, 5],
        "xhard1": [6, 7], "xhard2": [8, 9], "xhard3": [10, 12], "xhard4": [13, 15],
    },
    "distractor": None,
    "xhard1": {"distractor": {"count": 1}, "min_center_dist_m": 0.08},
    "xhard2": {"distractor": {"count": 2}, "min_center_dist_m": 0.08},
    "xhard3": {"distractor": {"count": 3}, "min_center_dist_m": 0.08},
    "xhard4": {"distractor": {"count": 3}, "min_center_dist_m": 0.08},
}


def test_identical_decision_passes() -> None:
    assert_native_decision(copy.deepcopy(DEFAULT), DEFAULT, "T")


def test_declared_newvalue_entries_may_change() -> None:
    decision = copy.deepcopy(DEFAULT)
    decision["number_range"]["xhard4"] = [15, 15]
    decision["xhard2"]["min_center_dist_m"] = 0.09
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


def test_undeclared_or_missing_newvalue_key_rejected() -> None:
    # 新值档子树下多出申报外的键 → 拒绝
    decision = copy.deepcopy(DEFAULT)
    decision["xhard4"]["colors"] = ["yellow"]
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, DEFAULT, "T")
    # 缺少申报过的新值档键 → 拒绝（环境查表会 KeyError，提前在守卫处挡住）
    decision = copy.deepcopy(DEFAULT)
    decision["number_range"].pop("xhard4")
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, DEFAULT, "T")
    # 原值部分里冒出未申报的新值档节点 → 由新值结构守卫拒绝
    decision = copy.deepcopy(DEFAULT)
    decision["goal"] = {"xhard1": 1}
    with pytest.raises(SamplingConfigError):
        assert_native_decision(decision, DEFAULT, "T")


def test_legacy_snapshot_without_newvalue_passes() -> None:
    legacy = {
        "color": {"easy": 1, "medium": 3, "hard": 3},
        "number_range": {"easy": [1, 3], "hard": [4, 5]},
        "distractor": None,
    }
    assert_native_decision(legacy, DEFAULT, "T")
