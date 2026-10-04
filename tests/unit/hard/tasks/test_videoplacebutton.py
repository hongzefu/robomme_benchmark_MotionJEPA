"""VideoPlaceButton 新值档真值表（xhard1、xhard2）：执行段把被问方块放到「按钮前最后一次／按钮后第一次」放过的那个目标台。

答案由演示段实际发生的放置事件按手写规则推出（before → 按钮前该方块最后落到的目标台；after → 按钮后第一次），
目标台在演示收尾时会交换位置，答案跟随台的身份。错误与边界：before／after 反转、放到答案台交换前所在位置上
现在的台、执行段抓别的方块均为失败。
"""
from __future__ import annotations

import pytest

from .. import offline_scene as O
from ..world import World, cpu_world
from . import demo_driver as DD
from .swap_driver import bin_at

TASK = "VideoPlaceButton"
TIERS = O.tiers_of(TASK)
OK = {"success": False, "fail": False}


@pytest.fixture
def world():
    with cpu_world():
        yield lambda tier, k=0: World.build(TASK, tier, k)


def _answer(w, log):
    seq = DD.target_placements(log, w.env.target_cube, w.env.targets)
    if w.env.target_target_language == "before":
        return [t for t, after in seq if not after][-1], [t for t, after in seq if after][0]
    return [t for t, after in seq if after][0], [t for t, after in seq if not after][-1]


def _place(w, target):
    cube = w.env.target_cube
    w.grasp(cube)
    assert w.step() == OK
    w.release_onto(cube, w.xyz(target)[:2])
    return w.step()


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("k", range(2))
def test_place_onto_answer_target_succeeds(world, tier, k):
    w = world(tier, k)
    log = DD.run_demo(w)
    answer, _ = _answer(w, log)
    assert answer is w.env.target_target
    assert _place(w, answer) == {"success": True, "fail": False}


@pytest.mark.parametrize("tier", TIERS)
def test_before_after_swapped_fails(world, tier):
    w = world(tier)
    log = DD.run_demo(w)
    answer, mirror = _answer(w, log)
    if mirror is answer:
        pytest.skip("未验证：本局按钮前后放的是同一个台，before／after 反转无从区分")
    assert _place(w, mirror) == {"success": False, "fail": True}


@pytest.mark.parametrize("tier", TIERS[:1])
def test_answer_old_position_and_wrong_cube_fail(world, tier):
    w = world(tier)
    pre = {t.name: w.xyz(t)[:2].copy() for t in w.env.targets}
    log = DD.run_demo(w)
    answer, _ = _answer(w, log)
    impostor = bin_at(w, pre[answer.name], w.env.targets)
    if impostor is not None and impostor is not answer:
        assert _place(w, impostor) == {"success": False, "fail": True}
    w = World.build(TASK, tier)
    DD.run_demo(w)
    w.grasp(w.env.non_target_cubes[0])
    assert w.step() == {"success": False, "fail": True}
