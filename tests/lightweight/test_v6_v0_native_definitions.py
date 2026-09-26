"""V6 S1 轻量测试：V5/V6 快照的原三档冻结投影。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.parity import v6_v0_native_definitions as gate  # noqa: E402


def _snapshots() -> tuple[dict, dict]:
    """读取仓库内冻结的 V5 与 V6 sampling_config 快照。"""
    v5 = json.loads(gate.DEFAULT_V5.read_text(encoding="utf-8"))
    v6 = json.loads(gate.DEFAULT_V6.read_text(encoding="utf-8"))
    return v5, v6


def test_v0_snapshots_pass_with_only_declared_v6_tier_configs() -> None:
    v5, v6 = _snapshots()
    assert gate.compare_snapshots(v5, v6) == []


def test_newvalue_tier_differences_are_projected_out() -> None:
    v5, v6 = _snapshots()
    v5_block = v5["tasks"]["BinFill"]
    v6_block = v6["tasks"]["BinFill"]

    v5_block["decision"]["configs"]["xhard"]["spawn_cubes"] = [99, 99]
    for tier in gate.V6_TIER_KEYS:
        v6_block["decision"]["configs"][tier]["spawn_cubes"] = [88, 88]
    v5_block["native"]["parameters"]["put_in_color"]["xhard"] = [9, 9]
    for tier in gate.V6_TIER_KEYS:
        v6_block["native"]["parameters"]["put_in_color"][tier] = [8, 8]

    for task in gate.EXPECTED_V6_NATIVE_CONFIGS_TASKS:
        configs = v6["tasks"][task]["native"]["parameters"]["configs"]
        for tier in gate.V6_TIER_KEYS:
            if tier in configs:
                configs[tier] = {"probe": tier}

    assert gate.compare_snapshots(v5, v6) == []


@pytest.mark.parametrize("tier", ("easy", "medium", "hard"))
def test_changes_to_original_decision_tiers_fail(tier: str) -> None:
    v5, v6 = _snapshots()
    v6["tasks"]["BinFill"]["decision"]["configs"][tier]["spawn_cubes"][0] += 1

    paths = gate.compare_snapshots(v5, v6)
    assert f"/tasks/BinFill/decision/configs/{tier}/spawn_cubes/0" in paths


@pytest.mark.parametrize("tier", ("easy", "medium", "hard"))
def test_changes_to_original_native_tiers_fail(tier: str) -> None:
    v5, v6 = _snapshots()
    v6["tasks"]["BinFill"]["native"]["parameters"]["put_in_color"][tier][0] += 1

    paths = gate.compare_snapshots(v5, v6)
    assert f"/tasks/BinFill/native/parameters/put_in_color/{tier}/0" in paths


def test_native_configs_exception_cannot_spread_to_other_tasks() -> None:
    v5, v6 = _snapshots()
    v6["tasks"]["BinFill"]["native"]["parameters"]["configs"] = {"xhard4": {}}

    paths = gate.compare_snapshots(v5, v6)
    assert any(
        path.startswith("/tasks/BinFill/native/parameters/configs")
        for path in paths
    )


def test_missing_expected_native_configs_is_reported() -> None:
    v5, v6 = _snapshots()
    del v6["tasks"]["VideoRepick"]["native"]["parameters"]["configs"]

    paths = gate.compare_snapshots(v5, v6)
    assert "/tasks/VideoRepick/native/parameters/configs (unexpected exception scope)" in paths


@pytest.mark.parametrize(
    ("edit", "expected_path"),
    (
        ("missing", "/tasks/VideoRepick/native/parameters/configs/easy (missing expected tier key)"),
        ("extra", "/tasks/VideoRepick/native/parameters/configs/xhard (unexpected tier key)"),
    ),
)
def test_native_configs_exception_requires_exact_seven_tier_keys(edit: str, expected_path: str) -> None:
    v5, v6 = _snapshots()
    configs = v6["tasks"]["VideoRepick"]["native"]["parameters"]["configs"]
    if edit == "missing":
        del configs["easy"]
    else:
        configs["xhard"] = {}

    assert expected_path in gate.compare_snapshots(v5, v6)


@pytest.mark.parametrize("section", ("decision", "native"))
def test_missing_snapshot_block_fails_even_when_missing_on_both_sides(section: str) -> None:
    v5, v6 = _snapshots()
    del v5["tasks"]["BinFill"][section]
    del v6["tasks"]["BinFill"][section]

    paths = gate.compare_snapshots(v5, v6)
    assert f"/v5/tasks/BinFill/{section}" in paths
    assert f"/v6/tasks/BinFill/{section}" in paths


def test_compare_does_not_mutate_input_snapshots() -> None:
    v5, v6 = _snapshots()
    original_v5 = copy.deepcopy(v5)
    original_v6 = copy.deepcopy(v6)

    gate.compare_snapshots(v5, v6)

    assert v5 == original_v5
    assert v6 == original_v6
