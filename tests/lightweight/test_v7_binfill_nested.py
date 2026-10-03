#!/usr/bin/env python3
"""轻量测试：BinFill 低档逐色投入数的嵌套派生 ``nest_binfill_targets``（0928 方案 D-15）。

不变量：逐色 ``target_i ≤ 母 target_i``；母档投入过的颜色本档至少留 1 块；总数等于本档抽到的总数
（母 9 → 6／7／8）；同 seed＋同档确定、不消耗环境随机流；不同 seed／档至少有时不同；总数超母档或会让某色归零即报错。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_binfill_nested.py -q
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.robomme_env.utils.episode_spec import (  # noqa: E402
    NEST_RULES,
    EpisodeSpecError,
    nest_binfill_targets,
)

#: 母档（xhard4）投入 9 块的若干种逐色分布（含某色为 0、三色都有）
PARENTS = [[3, 3, 3], [5, 4, 0], [1, 4, 4], [7, 1, 1], [0, 0, 9], [2, 0, 7]]
TIER_TOTALS = {"xhard1": 6, "xhard2": 7, "xhard3": 8}


def _drawn(total):
    """本档抽到的逐色值只有总和参与派生；这里给一个总和正确的任意分布。"""
    return [total, 0, 0]


@pytest.mark.parametrize("parent", PARENTS)
@pytest.mark.parametrize("tier", sorted(TIER_TOTALS))
def test_嵌套不变量(parent, tier):
    total = TIER_TOTALS[tier]
    for seed in (14_000_000, 14_400_300, 14_401_907, 123):
        out = nest_binfill_targets(parent, _drawn(total), seed=seed, tier=tier)
        assert len(out) == len(parent)
        assert sum(out) == total
        assert all(0 <= o <= p for o, p in zip(out, parent)), (parent, out)
        assert all(o >= 1 for o, p in zip(out, parent) if p >= 1), (parent, out)
        assert all(o == 0 for o, p in zip(out, parent) if p == 0)


def test_母档本身不变():
    for parent in PARENTS:
        assert nest_binfill_targets(parent, [9, 0, 0], seed=1, tier="xhard4") == parent


def test_同seed同档确定_且不消耗全局随机流():
    torch.manual_seed(0)
    before = torch.rand(3)
    torch.manual_seed(0)
    a = nest_binfill_targets([3, 3, 3], [6, 0, 0], seed=77, tier="xhard1")
    after = torch.rand(3)
    assert torch.equal(before, after)  # 独立生成器，不碰全局 RNG
    for _ in range(3):
        assert nest_binfill_targets([3, 3, 3], [6, 0, 0], seed=77, tier="xhard1") == a
    # 本档抽到值的逐色分布不影响结果，只看总数
    assert nest_binfill_targets([3, 3, 3], [2, 2, 2], seed=77, tier="xhard1") == a


def test_不同seed或档至少有时不同():
    parent = [3, 3, 3]
    by_seed = {tuple(nest_binfill_targets(parent, [7, 0, 0], seed=s, tier="xhard2")) for s in range(40)}
    assert len(by_seed) > 1
    # 同一 seed，不同档名（总数相同时）派生也可以不同：换档名等于换生成器种子
    by_tier = {tuple(nest_binfill_targets(parent, [7, 0, 0], seed=s, tier=t))
               for s, t in itertools.product(range(10), ("xhard1", "xhard2", "xhard3"))}
    assert len(by_tier) > 1


def test_非法输入报错():
    with pytest.raises(EpisodeSpecError, match="超过母档"):
        nest_binfill_targets([3, 3, 3], [10, 0, 0], seed=1, tier="xhard1")
    # 母 [1,1,7] 去掉 8 块才到 1：会让某色归零
    with pytest.raises(EpisodeSpecError, match="归零"):
        nest_binfill_targets([1, 1, 7], [1, 0, 0], seed=1, tier="xhard1")
    # 恰好能留每色 1 块时合法
    assert nest_binfill_targets([1, 1, 7], [3, 0, 0], seed=1, tier="xhard1") == [1, 1, 1]


def test_N表登记了BinFill投入数():
    assert NEST_RULES["objects.target_numbers"] is nest_binfill_targets
