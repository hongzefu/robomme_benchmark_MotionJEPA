"""VideoUnmaskSwap 新值档真值表（xhard1、xhard2）：容器经多次交换后，抓起仍藏着目标颜色方块的那个容器（跟随身份）。

经真实 ``step`` 走完揭示与全部交换窗口（方块随容器移动由生产的停放／落回逻辑完成），再按交换后的几何藏物关系抓放：
正例成功；抓「目标方块交换前所在位置」上现在的容器（若已换成别的容器）即失败；抬干扰容器即失败；
交换没走完（静止项未完成）之前抓对的容器不推进。
"""
from __future__ import annotations

import pytest

from .. import offline_scene as O
from ..world import World, cpu_world
from . import swap_driver as S
from . import unmask_driver as D

TASK = "VideoUnmaskSwap"
TIERS = O.tiers_of(TASK)


@pytest.fixture
def world():
    with cpu_world():
        yield lambda tier: World.build(TASK, tier)


@pytest.mark.parametrize("tier", TIERS)
def test_follow_identity_through_swaps_succeeds(world, tier):
    w = world(tier)
    S.run_through_swaps(w)
    assert w.stage == 1, "交换全部走完后静止项完成"
    bins = S.bins_in_order(w)
    assert [b.name for b in bins] == [w.env.selected_bins[i].name for i in range(w.env.pick_times)]
    assert S.pick_sequence(w, bins) == {"success": True, "fail": False}


@pytest.mark.parametrize("tier", TIERS[:1])
def test_original_position_is_a_trap(world, tier):
    w = world(tier)
    origin = S.run_through_swaps(w)
    target = D.colour_cubes(w.env)[0]
    right = S.bins_in_order(w)[0]
    impostor = S.bin_at(w, origin[target.name], w.env.spawned_bins)
    if impostor is None or impostor is right:
        pytest.skip("未验证：本局目标容器交换后回到原位或原位空着，原位置陷阱不成立")
    D.lift(w, impostor)
    assert w.tick() == {"success": False, "fail": True}


@pytest.mark.parametrize("tier", TIERS[:1])
def test_distractor_container_after_swaps_fails(world, tier):
    w = world(tier)
    S.run_through_swaps(w)
    D.lift(w, w.env.distractor_bins[0])
    assert w.tick() == {"success": False, "fail": True}


@pytest.mark.parametrize("tier", TIERS[:1])
def test_picking_before_swaps_finish_does_not_advance(world, tier):
    w = world(tier)
    right = w.env.selected_bins[0]
    D.lift(w, right)
    for _ in range(5):
        assert w.tick() == S.OK
    assert w.stage == 0
