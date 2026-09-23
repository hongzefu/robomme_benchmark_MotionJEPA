#!/usr/bin/env python3
"""轻量测试：StopCube 的 V4 xhard 档（NEWTASK_RELEASE_V4_PLAN 2.6，用户决策 A6 / C4）。

不起 sapien 场景，只查结构与公式：

* ``configs`` 三档同值且等于改动前的全局常量，xhard 为「速度最快档 [60]、stop_time 闭区间 [6,15]」；
* ``_native_decision`` 去掉 ``xhard`` 后与 V3 快照逐字相同，守卫放行 xhard 收窄、拒绝改原三档；
* 旧快照（无 xhard 条目）解析后补上源码申报的 xhard 默认值；
* xhard 段数规则 ``max(5, stop_time)`` 覆盖第 stop_time 次经过目标，停止窗口与按压时刻自洽；
* ``vqa_options._options_stopcube`` 的「remain static」检查点与环境侧 ``static_checkpoints`` 公式逐项一致
  （原三档全部组合与 xhard 全部组合都查）。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_stopcube.py -q
"""

from __future__ import annotations

import ast
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

from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    assert_native_decision,
)

# 包的 __init__ 做了 ``from .StopCube import *``，属性名会被同名类遮住，必须按模块路径取
MODULE = importlib.import_module("robomme.robomme_env.StopCube")
CLS = MODULE.StopCube

# 改动前（00e2ef4）_native_decision 的逐字返回值
V3_DECISION = {
    "move_interval_choices": [60, 80, 120],
    "stop_time_range": {"low": 2, "high_exclusive": 6},
}
XHARD = {
    "move_interval_choices": [60],
    "stop_time_range": {"low": 6, "high_exclusive": 16},
}
INTERVAL = 30  # NATIVE_SAMPLING.parameters.interval_sample.overridden_to


def test_configs_three_same_and_xhard_new() -> None:
    assert set(CLS.configs) == {"easy", "medium", "hard", "xhard"}
    for difficulty in ("easy", "medium", "hard"):
        assert CLS.configs[difficulty] == V3_DECISION, difficulty
    assert CLS.configs["xhard"] == XHARD
    # 三档是各自独立的副本，改一档不会串到另一档
    assert CLS.configs["easy"] is not CLS.configs["hard"]


def test_native_decision_visible_part_unchanged() -> None:
    decision, native = MODULE.native_blocks(CLS)
    assert {k: v for k, v in decision.items() if k != "xhard"} == V3_DECISION
    assert decision["xhard"] == XHARD
    # native 块本轮一个键都没动
    assert native["parameters"]["motion_segments"] == 5


def test_guard_allows_xhard_narrowing_rejects_original_change() -> None:
    decision, native = MODULE.native_blocks(CLS)
    narrowed = copy.deepcopy(decision)
    narrowed["xhard"]["stop_time_range"] = {"low": 15, "high_exclusive": 16}
    resolved = MODULE._resolve_sampling_config(CLS, {"decision": narrowed, "native": native})
    assert resolved["decision"]["xhard"]["stop_time_range"] == {"low": 15, "high_exclusive": 16}

    broken = copy.deepcopy(decision)
    broken["move_interval_choices"] = [60]
    with pytest.raises(SamplingConfigError):
        MODULE._resolve_sampling_config(CLS, {"decision": broken, "native": native})

    extra = copy.deepcopy(decision)
    extra["xhard"]["press_lead"] = 20
    with pytest.raises(SamplingConfigError):
        assert_native_decision(extra, decision, "StopCube")


def test_old_snapshot_without_xhard_gets_default() -> None:
    _, native = MODULE.native_blocks(CLS)
    resolved = MODULE._resolve_sampling_config(
        CLS, {"decision": copy.deepcopy(V3_DECISION), "native": native}
    )
    assert resolved["decision"]["xhard"] == XHARD
    assert resolved["decision"]["move_interval_choices"] == [60, 80, 120]


def test_step_keeps_literal_range5_for_original_three() -> None:
    """原三档分支必须逐字保留 ``range(5)``；xhard 分支按 ``self.motion_segments`` 展开。"""
    source = (REPO_ROOT / "src/robomme/robomme_env/StopCube.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    step = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "step"
    )
    text = ast.unparse(step)
    assert "segments = range(5)" in text
    assert "segments = range(self.motion_segments)" in text
    assert "segment % 2 == 0" in text


def _env_static_checkpoints(move_interval: int, stop_time: int) -> list:
    """与 StopCube._initialize_episode 的 static_checkpoints 公式逐字同构。"""
    steps_press = move_interval * (stop_time) - move_interval / 2
    final_abs_timestep = steps_press - INTERVAL
    checkpoints = list(range(100, int(final_abs_timestep), 100))
    if not checkpoints or checkpoints[-1] != final_abs_timestep:
        checkpoints.append(final_abs_timestep)
    return checkpoints


def _combos():
    for mi in V3_DECISION["move_interval_choices"]:
        for st in range(V3_DECISION["stop_time_range"]["low"], V3_DECISION["stop_time_range"]["high_exclusive"]):
            yield "orig", mi, st
    for mi in XHARD["move_interval_choices"]:
        for st in range(XHARD["stop_time_range"]["low"], XHARD["stop_time_range"]["high_exclusive"]):
            yield "xhard", mi, st


@pytest.mark.parametrize("tier,mi,st", list(_combos()))
def test_vqa_checkpoints_match_env(tier, mi, st) -> None:
    from tests.lightweight.test_StopcubeIncrement import (
        _DummyBase,
        _DummyEnv,
        _get_remain_static_solver,
        _load_vqa_options_module,
    )

    expected = _env_static_checkpoints(mi, st)
    module, hold_calls = _load_vqa_options_module()
    base = _DummyBase(steps_press=mi * st - mi / 2, interval=INTERVAL)
    options = module._options_stopcube(_DummyEnv(0), planner=None, require_target=lambda: None, base=base)
    solve = _get_remain_static_solver(options)
    for _ in range(len(expected)):
        solve()
    assert hold_calls == [int(v) for v in expected]
    if tier == "xhard":
        # 60×15 下 remain static 最多 9 条（计划 2.6 实施要点）
        assert len(expected) <= 9


@pytest.mark.parametrize("st", range(6, 16))
def test_xhard_segments_cover_stop_pass(st) -> None:
    mi = 60
    segments = max(5, st)
    steps_press = mi * st - mi / 2
    window = (mi * (st - 1), mi * st)
    # 第 st 次经过目标 = 第 st 段（0 起为 st-1）的中点，必须落在已展开的段内
    assert st - 1 < segments
    assert mi * (st - 1) <= steps_press <= mi * segments
    assert window[0] <= steps_press <= window[1]
    # 评估超时判据 move_interval*stop_time 最大 900 步，低于 scripts/evaluation.py 的 max_steps=1300
    assert mi * st <= 900
