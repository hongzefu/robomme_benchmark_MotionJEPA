#!/usr/bin/env python3
"""轻量测试：V4 BinFill xhard（计划 2.3、D1、D6），纯 CPU、不起 sapien 场景。

* 原三档 ``config_easy/medium/hard`` 逐字不变；``_native_decision`` 剥掉 xhard 后与改动前逐字相同；
* ``config_xhard`` 与计划 2.3 的新值一致（clutter、12 块、3 色、投入 [5,7]）；
* 守卫：xhard 条目允许改值（收窄到端点）、不许改 layout_mode 到未实现模式、不许新增申报外键、
  原三档任何改动照旧拒绝；没有 xhard 条目的旧快照照旧放行。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_binfill.py -q
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

binfill = importlib.import_module("robomme.robomme_env.BinFill")
from robomme.robomme_env.utils.sampling_config import SamplingConfigError  # noqa: E402

CLS = binfill.BinFill

# 改动前（00e2ef4）的原三档字面量，逐字抄录
ORIGINAL = {
    "easy": {"color": 1, "spawn_cubes": [4, 6], "put_in_color": [1, 1], "put_in_numbers": [1, 3]},
    "medium": {"color": 2, "spawn_cubes": [8, 10], "put_in_color": [1, 2], "put_in_numbers": [2, 4]},
    "hard": {"color": 3, "spawn_cubes": [10, 12], "put_in_color": [2, 3], "put_in_numbers": [3, 5]},
}
ORIGINAL_DECISION = {
    "layout_mode": "native_dynamic",
    "configs": {
        d: {"color": c["color"], "spawn_cubes": c["spawn_cubes"], "put_in_numbers": c["put_in_numbers"]}
        for d, c in ORIGINAL.items()
    },
}


def _override(mutate):
    decision, native = binfill.native_blocks(CLS)
    decision = copy.deepcopy(decision)
    mutate(decision)
    return {"decision": decision, "native": native}


def test_original_three_configs_unchanged() -> None:
    for difficulty, expected in ORIGINAL.items():
        assert CLS.configs[difficulty] == expected
    assert CLS.config_easy == ORIGINAL["easy"]
    assert CLS.config_medium == ORIGINAL["medium"]
    assert CLS.config_hard == ORIGINAL["hard"]


def test_native_decision_without_xhard_is_original() -> None:
    decision = binfill._native_decision(CLS)
    stripped = copy.deepcopy(decision)
    stripped["configs"].pop("xhard")
    assert stripped == ORIGINAL_DECISION
    # 原三档条目里不许冒出 layout_mode 之类的新键
    for difficulty in ORIGINAL:
        assert set(decision["configs"][difficulty]) == {"color", "spawn_cubes", "put_in_numbers"}


def test_xhard_values_match_plan() -> None:
    assert CLS.config_xhard == {
        "color": 3, "spawn_cubes": [12, 12], "put_in_color": [2, 3],
        "put_in_numbers": [5, 7], "layout_mode": "clutter",
    }
    decision = binfill._native_decision(CLS)
    assert decision["configs"]["xhard"] == {
        "color": 3, "spawn_cubes": [12, 12], "put_in_numbers": [5, 7], "layout_mode": "clutter",
    }
    # D6：clutter ⇒ dynamic 固定 False；只实现了这一种模式
    assert binfill.XHARD_LAYOUT_DYNAMIC == {"clutter": False}
    _, native = binfill.native_blocks(CLS)
    assert native["parameters"]["put_in_color"]["xhard"] == [2, 3]
    # B1：区域与间距不动
    cubes = native["positions"]["cubes"]
    assert cubes["region_center"] == [-0.1, 0] and cubes["region_half_size"] == [0.2, 0.25]
    assert cubes["min_gap_value"] == 0.02


def test_default_resolution_merges_xhard() -> None:
    resolved = binfill._resolve_sampling_config(CLS, None)
    assert resolved["parameters"]["configs"]["xhard"] == {
        "color": 3, "spawn_cubes": [12, 12], "put_in_numbers": [5, 7],
        "layout_mode": "clutter", "put_in_color": [2, 3],
    }
    for difficulty, expected in ORIGINAL.items():
        assert resolved["parameters"]["configs"][difficulty] == expected


@pytest.mark.parametrize("endpoint", [[5, 5], [7, 7]])
def test_guard_allows_narrowing_xhard(endpoint) -> None:
    config = _override(lambda d: d["configs"]["xhard"].__setitem__("put_in_numbers", endpoint))
    resolved = binfill._resolve_sampling_config(CLS, config)
    assert resolved["parameters"]["configs"]["xhard"]["put_in_numbers"] == endpoint


@pytest.mark.parametrize("mode", ["native_dynamic", "grid", None])
def test_guard_rejects_unimplemented_xhard_layout(mode) -> None:
    config = _override(lambda d: d["configs"]["xhard"].__setitem__("layout_mode", mode))
    with pytest.raises(SamplingConfigError, match="layout_mode"):
        binfill._resolve_sampling_config(CLS, config)


def test_guard_rejects_undeclared_xhard_key_and_original_changes() -> None:
    with pytest.raises(SamplingConfigError, match="xhard"):
        binfill._resolve_sampling_config(
            CLS, _override(lambda d: d["configs"]["xhard"].__setitem__("dynamic", True)))
    with pytest.raises(SamplingConfigError):
        binfill._resolve_sampling_config(
            CLS, _override(lambda d: d["configs"]["hard"].__setitem__("put_in_numbers", [5, 7])))
    with pytest.raises(SamplingConfigError):
        binfill._resolve_sampling_config(CLS, _override(lambda d: d.__setitem__("layout_mode", "clutter")))


def test_old_snapshot_without_xhard_still_accepted() -> None:
    config = _override(lambda d: d["configs"].pop("xhard"))
    config["native"]["parameters"]["put_in_color"].pop("xhard")
    resolved = binfill._resolve_sampling_config(CLS, config)
    assert set(resolved["parameters"]["configs"]) == {"easy", "medium", "hard"}
