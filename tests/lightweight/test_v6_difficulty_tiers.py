# robomme_hard：本测试测新值档／改动行为，阶段 3 起 src/robomme 回到官方 1fadc0ec，故改测 robomme_hard（0927 计划 R8 第③类）
#!/usr/bin/env python3
"""V6 S1 轻量测试：难度档管道改造（docs/plans/0925-newtask-release-v6-plan.md 2.0，口径 3/11）。

覆盖：族判断与档位号、decision 守卫的新值键集合与按档结构核对、旧快照补齐、v4_specs 的档位与按档 seed 规则
（默认参数与 V5 逐字节相同）、runner 的身份硬校验。纯 CPU，不起模拟器。

    uv run --no-sync python -m pytest tests/lightweight/test_v6_difficulty_tiers.py -q
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
for extra in (REPO_ROOT / "src", REPO_ROOT / "scripts", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from robomme_hard.robomme_env.utils.difficulty import (  # noqa: E402
    NEWVALUE_DIFFICULTIES,
    VALID_DIFFICULTIES,
    is_newvalue_difficulty,
    newvalue_tier,
    normalize_robomme_difficulty,
    require_xhard4_only,
)
from robomme_hard.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    _strip_xhard,
    assert_native_decision,
    fill_missing_newvalue,
)
sys.path.insert(0, str(REPO_ROOT / "scripts" / "injection-dev"))
import _draw  # noqa: E402
from robomme_hard.env_record_wrapper import hard_specs as V  # noqa: E402  seed 规则由 v4_specs 下沉到包内

TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")


def test_family_and_tier_order() -> None:
    assert NEWVALUE_DIFFICULTIES == TIERS
    assert VALID_DIFFICULTIES == {"easy", "medium", "hard", *TIERS}
    assert [newvalue_tier(t) for t in TIERS] == [1, 2, 3, 4]
    for native in ("easy", "medium", "hard", None, "xhard", 3):
        assert not is_newvalue_difficulty(native)
        assert newvalue_tier(native) == 0
    assert is_newvalue_difficulty(" XHard2 ")
    assert normalize_robomme_difficulty(" XHARD3 ") == "xhard3"
    with pytest.raises(ValueError):
        normalize_robomme_difficulty("xhard")


def test_require_xhard4_only() -> None:
    for ok in ("easy", "medium", "hard", "xhard4", None):
        require_xhard4_only(ok, "StopCube")
    for bad in ("xhard1", "xhard2", "xhard3"):
        with pytest.raises(ValueError):
            require_xhard4_only(bad, "StopCube")


def _default():
    return {
        "number_range": {"easy": [1, 3], "hard": [4, 5], "xhard4": [13, 15], "xhard1": [6, 7],
                         "xhard2": [8, 9], "xhard3": [10, 12]},
        "plain": 1,
        "xhard4": {"a": 1, "b": {"c": 2}},
        "xhard1": {"a": 0, "b": {"c": 0}},
        "xhard2": {"a": 0, "b": {"c": 1}},
        "xhard3": {"a": 1, "b": {"c": 1}},
    }


def test_strip_removes_whole_family() -> None:
    assert _strip_xhard(_default()) == {"number_range": {"easy": [1, 3], "hard": [4, 5]}, "plain": 1}


def test_guard_accepts_v5_style_snapshot_and_fill() -> None:
    default = _default()
    v5 = copy.deepcopy(default)
    v5["number_range"]["xhard"] = v5["number_range"].pop("xhard4")
    v5["xhard"] = v5.pop("xhard4")
    for tier in ("xhard1", "xhard2", "xhard3"):
        del v5[tier]
        del v5["number_range"][tier]
    assert_native_decision(v5, default, "T")  # V5 的旧 xhard 只参与历史键剥离
    filled = fill_missing_newvalue(copy.deepcopy(v5), default)
    assert filled == v5  # 历史 xhard 不会被误作 xhard4，也不会触发自动补档
    partial = copy.deepcopy(default)
    for tier in ("xhard1", "xhard2", "xhard3"):
        del partial[tier]
        del partial["number_range"][tier]
    assert fill_missing_newvalue(partial, default) == default
    # V4 以前的快照（没有 xhard4）：一个键都不补。
    old = _strip_xhard(copy.deepcopy(default))
    assert fill_missing_newvalue(copy.deepcopy(old), default) == old


def test_guard_rejects_native_change_and_bad_tier_shape() -> None:
    default = _default()
    changed = copy.deepcopy(default)
    changed["number_range"]["hard"] = [4, 6]
    with pytest.raises(SamplingConfigError):
        assert_native_decision(changed, default, "T")
    bad = copy.deepcopy(default)
    bad["xhard2"]["extra"] = 1  # 申报外的新键
    with pytest.raises(SamplingConfigError):
        assert_native_decision(bad, default, "T")
    missing = copy.deepcopy(default)
    del missing["xhard1"]["b"]  # 出现了的档必须结构完整
    with pytest.raises(SamplingConfigError):
        assert_native_decision(missing, default, "T")
    tuned = copy.deepcopy(default)
    tuned["xhard3"]["a"] = 7  # 只改新值，放行
    assert_native_decision(tuned, default, "T")


def test_v4_specs_defaults_are_v5_bytes() -> None:
    assert V.DIFFICULTY == "xhard"
    assert V.SEED_RULE["offset"] == 4_000_000
    assert V.seed_rule_for() == V.SEED_RULE
    assert V.seed_for("BinFill", 3, 2) == V.seed_for("BinFill", 3, 2, V.SEED_RULE)
    # build_draw_header 与 V5 默认档 env_kwargs 随 v4_specs 删除（新值档 env_kwargs 必须显式传档位）
    assert _draw.env_kwargs(123, 0, "xhard3")["difficulty"] == "xhard3"


def test_v6_seed_rule_offsets_disjoint() -> None:
    offsets = {t: V.seed_rule_for(t, "v6")["offset"] for t in TIERS}
    assert offsets == {"xhard4": 6_000_000, "xhard1": 8_000_000, "xhard2": 10_000_000, "xhard3": 12_000_000}
    from seed_layout import ALL_TASKS  # noqa: PLC0415

    seen = {V.seed_for(t, e, a) for t in ALL_TASKS for e in range(10) for a in range(60)}
    for tier in TIERS:
        rule = V.seed_rule_for(tier, "v6")
        seeds = {V.seed_for(t, e, a, rule) for t in ALL_TASKS for e in range(10) for a in range(60)}
        assert not seeds & seen, tier
        seen |= seeds
    with pytest.raises(V.SpecsError):
        V.seed_rule_for("xhard2", "v5")  # 新档必须显式用 v6 规则
    assert V._known_seed_rule("xhard2", V.seed_rule_for("xhard2", "v6"))
    assert not V._known_seed_rule("xhard2", V.seed_rule_for("xhard1", "v6"))
    assert V._known_seed_rule("xhard", V.SEED_RULE)
    assert not V._known_seed_rule("xhard4", V.SEED_RULE)
    assert V._known_seed_rule("xhard4", V.seed_rule_for("xhard4", "v6"))


def test_draw_rows_carry_tier_and_rule() -> None:
    rule = V.seed_rule_for("xhard3", "v6")
    calls = []

    def fake(task, seed, episode, sampling):
        calls.append(seed)
        return True, {"spec_kind": "native-newvalue/2", "task": task}, None, None

    rows = _draw.draw_task("PatternLock", {}, 2, 5, fake, "xhard3", rule)
    assert [r["difficulty"] for r in rows] == ["xhard3", "xhard3"]
    assert calls == [V.seed_for("PatternLock", 0, 0, rule), V.seed_for("PatternLock", 1, 0, rule)]
    assert _draw.merge_task_rows(["PatternLock"], {"PatternLock": rows}, rule) == rows
    with pytest.raises(V.SpecsError):
        _draw.merge_task_rows(["PatternLock"], {"PatternLock": rows})  # 用错规则必须拒绝
