#!/usr/bin/env python3
"""轻量测试：V6 语义审查修复在 scripts/ 侧的两处改动（docs/plans/0926-v6-audit-fix-plan.md §8.2 非 src 项）。

* N14：MoveCube 新值档按运动方式分层选局（``v4_specs.stratified_select``）；其他环境与原三档沿用 ``select``。
* N2 落地：``--task-max-reset-attempts`` 的 ``TASK[@TIER]=N`` 解析与 ``draw_rows`` 的按环境尝试上限。

    uv run --no-sync python -m pytest tests/lightweight/test_audit_fix_scripts.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "injection-dev"))
import _draw  # noqa: E402
import _freeze  # noqa: E402
from robomme_hard.env_record_wrapper.hard_specs import SpecsError, seed_rule_for  # noqa: E402


def _row(episode, way_last, way_first=0):
    return {"episode": episode, "spec": {"initializations": {"0": {"way_idx": way_first}, "1": {"way_idx": way_last}}}}


def test_movecube_way_reads_last_initialization() -> None:
    """录像局用的是最后一次 reset 的 way_idx（审查 N14：候选 4/7/9 的 initializations.1 才是 peg_push）。"""
    assert _freeze._movecube_way(_row(0, 2, 0)["spec"]) == 2
    assert _freeze._movecube_way({"initializations": {}}) is None
    assert _freeze._movecube_way({}) is None


def test_stratified_select_one_per_way_for_movecube_newvalue() -> None:
    """N14：xhard4 MoveCube 每种运动方式取编号最小候选（0=peg_push,1=gripper_push,2=grasp_putdown）。"""
    rows = [_row(0, 1), _row(1, 2), _row(2, 2), _row(3, 1), _row(4, 0), _row(5, 2), _row(6, 2), _row(7, 0), _row(9, 0)]
    assert _freeze.stratified_select("MoveCube", "xhard4", rows, (0, 3, 6)) == [0, 1, 4]


def test_stratified_select_fills_missing_way_from_default_indices() -> None:
    """缺某种方式时按 select 顺序补齐，不另抽候选。"""
    rows = [_row(e, 1) for e in range(10)]
    assert _freeze.stratified_select("MoveCube", "xhard4", rows, (0, 3, 6)) == [0, 3, 6]


def test_stratified_select_default_for_other_tasks_and_native() -> None:
    rows = [_row(e, 0) for e in range(8)]
    assert _freeze.stratified_select("BinFill", "xhard4", rows, (0, 3, 6)) == [0, 3, 6]
    assert _freeze.stratified_select("MoveCube", "hard", rows, (0, 3, 6)) == [0, 3, 6]


def test_parse_task_max_reset_attempts_tier_filter() -> None:
    text = "VideoPlaceButton@xhard3=120,VideoPlaceButton@xhard4=120,BinFill=70"
    assert _draw.parse_task_max_reset_attempts(text, "xhard3") == {"VideoPlaceButton": 120, "BinFill": 70}
    assert _draw.parse_task_max_reset_attempts(text, "xhard1") == {"BinFill": 70}
    assert _draw.parse_task_max_reset_attempts(None, "xhard1") == {}
    with pytest.raises(SpecsError):
        _draw.parse_task_max_reset_attempts("VideoPlaceButton@xhard3", "xhard3")


def test_draw_rows_applies_per_task_attempts() -> None:
    """按环境尝试上限只作用于被点名的环境；假 reset 永远失败，行数 = 尝试数。"""
    def fake_draw_one(task, seed, episode, sampling):
        return False, None, "SceneGenerationError", "fake"

    samplings = {"VideoPlaceButton": {}, "BinFill": {}}
    rows, stats = _draw.draw_rows(["VideoPlaceButton", "BinFill"], samplings, 3, 5, workers=1, draw_one=fake_draw_one,
                                  difficulty="xhard3", seed_rule=seed_rule_for("xhard3", "v7"),
                                  max_reset_attempts_by_task={"VideoPlaceButton": 9})
    assert stats["attempted"] == 14 and stats["ok"] == 0
    counts = {}
    for row in rows:
        counts[row["task"]] = counts.get(row["task"], 0) + 1
    assert counts == {"VideoPlaceButton": 9, "BinFill": 5}
