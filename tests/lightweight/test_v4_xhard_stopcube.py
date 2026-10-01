# robomme_hard：本测试测新值档／改动行为，阶段 3 起 src/robomme 回到官方 1fadc0ec，故改测 robomme_hard（0927 计划 R8 第③类）
#!/usr/bin/env python3
"""轻量测试：StopCube 的 V4 xhard 档（docs/plans/0922-newtask-release-v4-plan.md 2.6，用户决策 A6 / C4）。

不起 sapien 场景，只查结构与公式：

* ``configs`` 三档同值且等于改动前的全局常量；v8（1001 方案 §1 表 1）新值档 xhard1～5 为
  「速度最快档 [60]、stop_time 定值 6／7／8／9／10」（v7 只有 xhard4、[6,15] 随机）；
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

from robomme_hard.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    assert_native_decision,
)

# 包的 __init__ 做了 ``from .StopCube import *``，属性名会被同名类遮住，必须按模块路径取
MODULE = importlib.import_module("robomme_hard.robomme_env.StopCube")
CLS = MODULE.StopCube

# 改动前（00e2ef4）_native_decision 的逐字返回值
V3_DECISION = {
    "move_interval_choices": [60, 80, 120],
    "stop_time_range": {"low": 2, "high_exclusive": 6},
}
# v8（1001 方案 §1 表 1 / §2.1）：五个新值档，stop_time 各一个定数 k（半开写 low=k, high_exclusive=k+1）
XHARD_STOP_TIME = {"xhard1": 6, "xhard2": 7, "xhard3": 8, "xhard4": 9, "xhard5": 10}
XHARD_TIERS = {
    tier: {"move_interval_choices": [60], "stop_time_range": {"low": k, "high_exclusive": k + 1}}
    for tier, k in XHARD_STOP_TIME.items()
}
#: xhard4 一档（旧快照兜底的默认值）
XHARD = XHARD_TIERS["xhard4"]
INTERVAL = 30  # NATIVE_SAMPLING.parameters.interval_sample.overridden_to


def test_configs_three_same_and_xhard_new() -> None:
    # v8（1001 方案 §2.1）：StopCube 扩至 xhard1～5，共 8 档（v6／v7 只有 xhard4）
    assert set(CLS.configs) == {"easy", "medium", "hard", *XHARD_TIERS}
    assert list(CLS.configs)[:4] == ["easy", "medium", "hard", "xhard4"]
    for difficulty in ("easy", "medium", "hard"):
        assert CLS.configs[difficulty] == V3_DECISION, difficulty
    for tier, expected in XHARD_TIERS.items():
        assert CLS.configs[tier] == expected, tier
    assert CLS.configs["xhard4"] == XHARD
    # 三档是各自独立的副本，改一档不会串到另一档
    assert CLS.configs["easy"] is not CLS.configs["hard"]


def test_native_decision_visible_part_unchanged() -> None:
    decision, native = MODULE.native_blocks(CLS)
    # v8：暴露五个新值子键；去掉它们后与 V3 快照逐字相同
    assert {k: v for k, v in decision.items() if k not in XHARD_TIERS} == V3_DECISION
    for tier, expected in XHARD_TIERS.items():
        assert decision[tier] == expected, tier
    assert decision["xhard4"] == XHARD
    # native 块本轮一个键都没动
    assert native["parameters"]["motion_segments"] == 5


def test_guard_allows_xhard_narrowing_rejects_original_change() -> None:
    decision, native = MODULE.native_blocks(CLS)
    narrowed = copy.deepcopy(decision)
    narrowed["xhard4"]["stop_time_range"] = {"low": 15, "high_exclusive": 16}
    resolved = MODULE._resolve_sampling_config(CLS, {"decision": narrowed, "native": native})
    assert resolved["decision"]["xhard4"]["stop_time_range"] == {"low": 15, "high_exclusive": 16}

    broken = copy.deepcopy(decision)
    broken["move_interval_choices"] = [60]
    with pytest.raises(SamplingConfigError):
        MODULE._resolve_sampling_config(CLS, {"decision": broken, "native": native})

    extra = copy.deepcopy(decision)
    extra["xhard4"]["press_lead"] = 20
    with pytest.raises(SamplingConfigError):
        assert_native_decision(extra, decision, "StopCube")


def test_old_snapshot_without_xhard_gets_default() -> None:
    _, native = MODULE.native_blocks(CLS)
    resolved = MODULE._resolve_sampling_config(
        CLS, {"decision": copy.deepcopy(V3_DECISION), "native": native}
    )
    assert resolved["decision"]["xhard4"] == XHARD
    assert resolved["decision"]["move_interval_choices"] == [60, 80, 120]


def test_step_keeps_literal_range5_for_original_three() -> None:
    """原三档分支必须逐字保留 ``range(5)``；xhard 分支按 ``self.motion_segments`` 展开。"""
    source = (REPO_ROOT / "src/robomme_hard/robomme_env/StopCube.py").read_text(encoding="utf-8")
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
    # v8：五个新值档 stop_time 6～10 全覆盖
    for tier, cfg in XHARD_TIERS.items():
        for mi in cfg["move_interval_choices"]:
            for st in range(cfg["stop_time_range"]["low"], cfg["stop_time_range"]["high_exclusive"]):
                yield tier, mi, st


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
    if tier != "orig":
        # 60×15 下 remain static 最多 9 条（计划 2.6 实施要点）；v8 最大 60×10，更少
        assert len(expected) <= 9


def test_vqa_combos_cover_stop_time_6_to_10() -> None:
    """v8：新值档的检查点组合恰好覆盖 stop_time 6～10（每档一个）。"""
    xhard = [(tier, st) for tier, _mi, st in _combos() if tier != "orig"]
    assert xhard == [(tier, k) for tier, k in XHARD_STOP_TIME.items()]
    assert sorted(st for _tier, st in xhard) == [6, 7, 8, 9, 10]


@pytest.mark.parametrize("st", range(6, 16))  # v8 实际只用 6～10；保留 v7 的 6～15 作为上界回归
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


@pytest.mark.parametrize("tier", list(XHARD_TIERS))
def test_v8_five_tiers_accepted_with_values(tier, monkeypatch) -> None:
    """v8（1001 方案 §2.1）：原「拒绝 xhard1～3」反转为「五档都接受、值正确」。

    ``__init__`` 不再调用 ``require_xhard4_only``；把 ``BaseEnv.__init__`` 换成空函数（不起 sapien 场景），
    检查本实例的难度与解析出的 decision 子树。"""
    monkeypatch.setattr(MODULE.BaseEnv, "__init__", lambda self, *args, **kwargs: None)
    env = CLS(difficulty=tier)
    assert env.difficulty == tier
    sub = env._sampling["decision"][tier]
    assert sub == XHARD_TIERS[tier]
    low, high = sub["stop_time_range"]["low"], sub["stop_time_range"]["high_exclusive"]
    assert list(range(low, high)) == [XHARD_STOP_TIME[tier]]
    assert sub["move_interval_choices"] == [60]


def test_v8_init_no_longer_calls_require_xhard4_only() -> None:
    source = (REPO_ROOT / "src/robomme_hard/robomme_env/StopCube.py").read_text(encoding="utf-8")
    assert "require_xhard4_only" not in source.replace("不再调用 require_xhard4_only", "")
    assert "NEWVALUE_DIFFICULTIES[-1]" not in source.replace("不再用 NEWVALUE_DIFFICULTIES[-1]", "")
