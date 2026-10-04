"""VideoPlaceOrder 新值档真值表（xhard1、xhard2）：执行段把被问方块放到它在演示里「第 k 次」放到的目标台（时间序）。

答案由演示段实际发生的放置事件推出：被问方块按时间排的第 ``which_in_subset`` 次目标台放置（k 是题面里的序数）。
目标台在演示收尾时交换位置，答案跟随台的身份。错误与边界：第一次／最后一次（若不是第 k 次）冒充、
答案台交换前所在位置上现在的台、执行段抓别的方块均为失败；按钮插在放置序列中间不影响序数。
"""
from __future__ import annotations

import pytest

from .. import offline_scene as O
from ..world import World, cpu_world
from . import demo_driver as DD
from .swap_driver import bin_at

TASK = "VideoPlaceOrder"
TIERS = O.tiers_of(TASK)
OK = {"success": False, "fail": False}


@pytest.fixture
def world():
    with cpu_world():
        yield lambda tier, k=0: World.build(TASK, tier, k)


def _visits(w, log):
    return [t for t, _ in DD.target_placements(log, w.env.target_cube, w.env.targets)]


def _place(w, target):
    cube = w.env.target_cube
    w.grasp(cube)
    assert w.step() == OK
    w.release_onto(cube, w.xyz(target)[:2])
    return w.step()


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("k", range(2))
def test_place_onto_kth_visit_succeeds(world, tier, k):
    w = world(tier, k)
    log = DD.run_demo(w)
    assert log.button_at is not None, "演示里按过按钮"
    visits = _visits(w, log)
    answer = visits[w.env.which_in_subset - 1]
    assert answer is w.env.target_target
    assert _place(w, answer) == {"success": True, "fail": False}


@pytest.mark.parametrize("tier", TIERS)
def test_other_ordinal_fails(world, tier):
    w = world(tier)
    log = DD.run_demo(w)
    visits = _visits(w, log)
    answer = visits[w.env.which_in_subset - 1]
    decoy = next((t for t in (visits[0], visits[-1]) if t is not answer), None)
    if decoy is None:
        pytest.skip("未验证：本局首末两次都落在答案台上，序数冒充无从构造")
    assert _place(w, decoy) == {"success": False, "fail": True}


@pytest.mark.parametrize("tier", TIERS[:1])
def test_answer_old_position_and_wrong_cube_fail(world, tier):
    w = world(tier)
    pre = {t.name: w.xyz(t)[:2].copy() for t in w.env.targets}
    log = DD.run_demo(w)
    answer = _visits(w, log)[w.env.which_in_subset - 1]
    impostor = bin_at(w, pre[answer.name], w.env.targets)
    if impostor is not None and impostor is not answer:
        assert _place(w, impostor) == {"success": False, "fail": True}
    w = World.build(TASK, tier)
    DD.run_demo(w)
    w.grasp(w.env.non_target_cubes[0])
    assert w.step() == {"success": False, "fail": True}
