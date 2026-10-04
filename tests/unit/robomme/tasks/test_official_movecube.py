"""MoveCube 原生三档真值表（C05）：按演示的方式把方块移到目标——peg 钩推、夹爪推、抓起放下三选一。

期望（三种方式各自的在线段）：
- gripper_push：夹爪张开（两指 > 0.02）状态下把方块推到目标（水平距离 <= 0.048 m = 2.4 × 方块半边长 0.02 m）→ 成功；
  拿起方块或拿起 peg → 失败；
- peg_push：先拿起 peg（任一端），再把方块钩到目标且夹爪张开 → 成功；拿 peg 之前方块已到目标 → 失败；
- grasp_putdown：拿起方块再放到目标（0.05 m 内）→ 成功；不拿起直接推到目标 → 失败。
演示结束后由真实 step 的 reset_in_proecess 分支把方块与目标换到第二套位姿（演示数据不污染在线段）。
"""
from __future__ import annotations

import numpy as np
import pytest

from _official_world import OfficialWorld, find_seed

TASK = "MoveCube"
DIFFS = ("easy", "medium", "hard")
PUSH_THRESHOLD = 0.048  # 2 × 1.2 × cube_half_size（panda 方块半边长 0.02 m）


@pytest.fixture
def world():
    with OfficialWorld(TASK) as w:
        yield w


def _online(world, diff, way):
    seed = find_seed(TASK, diff, lambda e: e.way == way)
    ep = world.make(diff, seed=seed)
    env = ep.env
    assert env.cube_half_size == pytest.approx(0.02)
    ep.skip_demo()
    env.reset_in_proecess = True  # solve_strong_reset 期间：真实 step 把方块/目标换到第二套位姿
    ep.step()
    env.reset_in_proecess = False
    np.testing.assert_allclose(env.cube.xyz, env.cube_init_pose_2.p[0].numpy(), atol=1e-6)
    np.testing.assert_allclose(env.goal_site.xyz, env.goal_site_2_pose_p[0], atol=1e-6)
    assert not ep.fail
    return ep, env


def _push_to(ep, env, dx=0.0):
    gx, gy, _ = env.goal_site.xyz
    env.cube.move_to(gx + dx, gy, env.cube_half_size)
    ep.tcp_to(gx + dx - 0.04, gy, 0.03)


@pytest.mark.parametrize("diff", DIFFS)
def test_gripper_push(world, diff):
    ep, env = _online(world, diff, "gripper_push")
    ep.close_gripper()
    _push_to(ep, env)
    ep.step()
    assert not ep.success  # 夹爪闭合时不算推到
    ep.open_gripper()
    ep.step()
    assert ep.success and not ep.fail


@pytest.mark.parametrize("dx, ok", [(PUSH_THRESHOLD - 0.001, True), (PUSH_THRESHOLD + 0.001, False)])
def test_push_distance_threshold(world, dx, ok):
    ep, env = _online(world, "easy", "gripper_push")
    _push_to(ep, env, dx=dx)
    ep.step()
    assert ep.success is ok


@pytest.mark.parametrize("diff", DIFFS)
def test_gripper_push_picking_cube_fails(world, diff):
    ep, env = _online(world, diff, "gripper_push")
    ep.grasp(env.cube)
    ep.step()
    assert ep.fail and not ep.success


def test_gripper_push_picking_peg_fails(world):
    ep, env = _online(world, "easy", "gripper_push")
    ep.grasp(env.peg_tail)
    ep.step()
    assert ep.fail and not ep.success


@pytest.mark.parametrize("diff", DIFFS)
def test_peg_push(world, diff):
    ep, env = _online(world, diff, "peg_push")
    ep.grasp(env.peg_head)  # 任一端都算拿起 peg
    ep.step()
    assert ep.task_index == ep.first_online_index() + 1
    ep.close_gripper()
    _push_to(ep, env)
    ep.step()
    assert not ep.success  # 还攥着 peg（夹爪闭合）不算完成
    ep.open_gripper()
    ep.step()
    assert ep.success and not ep.fail


def test_peg_push_cube_on_goal_before_peg_fails(world):
    ep, env = _online(world, "easy", "peg_push")
    _push_to(ep, env)
    ep.step()
    assert ep.fail and not ep.success


@pytest.mark.parametrize("diff", DIFFS)
def test_grasp_putdown(world, diff):
    ep, env = _online(world, diff, "grasp_putdown")
    ep.grasp(env.cube)
    ep.step()
    ep.place_on(env.cube, env.goal_site)
    ep.step()
    assert ep.success and not ep.fail


def test_grasp_putdown_pushing_fails(world):
    ep, env = _online(world, "easy", "grasp_putdown")
    _push_to(ep, env)
    ep.step()
    assert ep.fail and not ep.success


def test_grasp_putdown_picking_peg_fails(world):
    ep, env = _online(world, "easy", "grasp_putdown")
    ep.grasp(env.peg_head)
    ep.step()
    assert ep.fail and not ep.success


def test_three_ways_reachable_in_every_difficulty():
    for diff in DIFFS:
        for way in ("peg_push", "gripper_push", "grasp_putdown"):
            find_seed(TASK, diff, lambda e, w=way: e.way == w)
