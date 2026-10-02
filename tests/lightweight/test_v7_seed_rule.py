#!/usr/bin/env python3
"""轻量测试：V7 与 V8 seed 规则（0928 方案第二部分 §1.1；v8 方案第二部分 §2.2 第 3 条）。

* v7 四档同一 offset（14e6）：同一 (task, episode, attempt) 在四档里 seed 相同（母布局共用）；v7 只按冻结常量
  ``V7_TIERS`` 遍历，不随全局 ``TIERS`` 变化；
* v7 的 seed 区间与 V5（4e6）在全部合法 episode／attempt 上互不重叠（v8 阶段 1 删 V6 后，v6 比较一并移除）；
* v8 按档偏移（16e6～24e6，步长 2e6）：五档两两不交，也不碰 v5、v7 与旧 v6 段（4e6～15.7e6 整段）；
  ``seed_rule_for(tier, "v8")`` 只用本族登记的档位校验（xhard5 在阶段 3b 前即可用），xhard0／历史 xhard 不接受；
* ``SEED_PROFILES`` 含 v7、v8，不含 v6；xhard0 与历史 ``xhard`` 不接受 v7 规则。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_seed_rule.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.env_record_wrapper import hard_specs as V  # noqa: E402

#: seed = offset + env_code*env_block + episode*100 + attempt；episode*100 必须小于 env_block，故 episode ∈ [0, 1000)
MAX_EPISODE = V.SEED_RULE["env_block"] // V.SEED_RULE["episode_stride"]
#: v5、旧 v6、v7 与探针占用的整段（v8 方案第二部分 §2.2 第 3 条：4e6～15.7e6）
LEGACY_SPAN = (4_000_000, 15_700_000)


def _interval(rule):
    """该规则在 16 任务 × 全部合法 episode／attempt 上的 seed 闭区间。"""
    lo = V.seed_for(V.ALL_TASKS[0], 0, 0, rule)
    hi = V.seed_for(V.ALL_TASKS[-1], MAX_EPISODE - 1, V.MAX_ATTEMPTS - 1, rule)
    return lo, hi


def _disjoint(a, b):
    return a[1] < b[0] or b[1] < a[0]


def test_v7四档同一规则且同候选同seed():
    assert "v7" in V.SEED_PROFILES
    rules = [V.seed_rule_for(tier, "v7") for tier in V.V7_TIERS]
    assert all(rule == rules[0] for rule in rules)
    assert rules[0] == {**V.SEED_RULE, "offset": V.V7_SEED_OFFSET}
    assert V.V7_SEED_OFFSET == 14_000_000
    for task in ("BinFill", "PatternLock", "StopCube"):
        for episode, attempt in ((0, 0), (19, 3), (57, 99)):
            seeds = {V.seed_for(task, episode, attempt, V.seed_rule_for(tier, "v7")) for tier in V.V7_TIERS}
            assert len(seeds) == 1


def test_v7区间与v5互不重叠():
    v7 = _interval(V.seed_rule_for("xhard4", "v7"))
    others = {"v5": _interval(V.SEED_RULE)}
    for name, (lo, hi) in others.items():
        assert hi < v7[0] or v7[1] < lo, (name, (lo, hi), v7)
    # 单任务内 episode*100+attempt 不越过 env_block：同规则下不同任务互不重叠
    rule = V.seed_rule_for("xhard1", "v7")
    per_task = [(V.seed_for(t, 0, 0, rule), V.seed_for(t, MAX_EPISODE - 1, V.MAX_ATTEMPTS - 1, rule)) for t in V.ALL_TASKS]
    for (_, hi), (lo, _) in zip(per_task, per_task[1:]):
        assert hi < lo


def test_v7规则被档位识别_旧档名不接受v7():
    rule = V.seed_rule_for("xhard2", "v7")
    for tier in V.V7_TIERS:
        assert V._known_seed_rule(tier, rule)
    with pytest.raises(V.SpecsError):
        V.seed_rule_for(V.DIFFICULTY, "v7")  # 历史单档 xhard 只认 v5
    with pytest.raises(V.SpecsError):
        V.seed_rule_for(V.XHARD0, "v7")  # xhard0 照抄官方元数据 seed，没有 seed 规则
    # v8 阶段 1：v6 规则族已删除
    assert "v6" not in V.SEED_PROFILES


def test_v8按档偏移两两不交且不碰旧段():
    assert "v8" in V.SEED_PROFILES
    assert V.TIER_SEED_OFFSETS == {"v8": V.V8_SEED_OFFSETS}
    assert tuple(V.V8_SEED_OFFSETS) == V.V8_TIERS
    intervals = {}
    for tier in V.V8_TIERS:
        rule = V.seed_rule_for(tier, "v8")
        assert rule == {**V.SEED_RULE, "offset": V.V8_SEED_OFFSETS[tier]}
        intervals[tier] = _interval(rule)
    names = list(intervals)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert _disjoint(intervals[a], intervals[b]), (a, b, intervals[a], intervals[b])
    for tier, span in intervals.items():
        assert _disjoint(span, LEGACY_SPAN), (tier, span)
        assert _disjoint(span, _interval(V.SEED_RULE))
        assert _disjoint(span, _interval(V.seed_rule_for("xhard1", "v7")))
    # 同一 (task, episode, attempt) 在五档 seed 互不相同（布局独立，R9）
    for task in ("StopCube", "SwingXtimes", "PickXtimes"):
        seeds = {V.seed_for(task, 7, 3, V.seed_rule_for(tier, "v8")) for tier in V.V8_TIERS}
        assert len(seeds) == len(V.V8_TIERS)


def test_v8规则按本族档位校验():
    # v8 规则族只按本族登记的档位校验（不经全局 TIERS）；阶段 3b 换包后全局 TIERS 也含 xhard5
    assert "xhard5" in V.TIERS and V.TIERS == V.V8_TIERS
    assert V.seed_rule_for("xhard5", "v8")["offset"] == 24_000_000
    for tier in V.V8_TIERS:
        rule = V.seed_rule_for(tier, "v8")
        assert V._known_seed_rule(tier, rule)
        # 别档的 v8 规则不被本档认作合法
        for other in V.V8_TIERS:
            if other != tier:
                assert not V._known_seed_rule(other, rule)
    for bad in (V.XHARD0, V.DIFFICULTY, "xhard6"):
        with pytest.raises(V.SpecsError, match="v8"):
            V.seed_rule_for(bad, "v8")
    # v5／v7 报错路径不变（v7 只认冻结的 V7_TIERS，换包后 xhard5 仍拒）
    with pytest.raises(V.SpecsError, match="未知档位"):
        V.seed_rule_for("xhard5", "v7")
    with pytest.raises(V.SpecsError):
        V.seed_rule_for("xhard1", "v5")
