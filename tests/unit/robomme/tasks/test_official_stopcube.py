"""StopCube 原生三档真值表（C05、C06 计时与场景运动）。

方块在两端点之间往返（真实 move_straight_line，每段 move_interval 步，smoothstep 插值），每段正中经过目标中心，
即第 k 次到达目标发生在 cur_step = mi·(k−1) + mi/2。期望（目标语言：「stop the cube … for the k-th time」）：
- 先把 tcp 悬到按钮上方（准备子任务），在第 stop_time 次到达时按下 → 成功，且之后继续步进保持成功；
- 第 stop_time−1 次到达时按 → 失败（停止步不在窗口 [mi·(st−1), mi·st] 内）；方块不在目标上时按 → 立即失败；
- 一直不按 → elapsed 超过 mi·st 即失败。三档在官方实现里共用同一逻辑（难度不参与取值）。
"""
from __future__ import annotations

import pytest

from _official_world import OfficialWorld, goal_text

TASK = "StopCube"
DIFFS = ("easy", "medium", "hard")
ORDINALS = {2: "second", 3: "third", 4: "fourth", 5: "fifth"}


@pytest.fixture
def world():
    with OfficialWorld(TASK) as w:
        yield w


def _visit_step(env, k):
    """第 k 次到达目标中心时 move_straight_line 的 cur_step（手算：每段正中）。"""
    return env.move_interval * (k - 1) + env.move_interval // 2


def _hover(ep):
    bx, by, _ = ep.env.button.xyz
    ep.tcp_to(bx, by, 0.1)


def _run_to(ep, elapsed):
    while int(ep.env.elapsed_steps) < elapsed:
        ep.step()


def _press_at_visit(ep, k):
    """推进到第 k 次经过目标的那一步按下按钮（下一步 evaluate 看到的方块位置正是目标中心）。"""
    _run_to(ep, _visit_step(ep.env, k))
    ep.press(ep.env.button)
    ep.step()
    ep.unpress(ep.env.button)


def _seed_with_stop_time(world, diff, predicate):
    for seed in range(64):
        ep = world.make(diff, seed=seed)
        if predicate(ep.env):
            return ep
    pytest.fail("找不到满足条件的 stop_time")


@pytest.mark.parametrize("diff", DIFFS)
def test_stop_on_the_nth_visit_succeeds_and_persists(world, diff):
    ep = _seed_with_stop_time(world, diff, lambda e: e.stop_time >= 2)
    env = ep.env
    st = env.stop_time
    goals = goal_text(env)
    assert f"for the {ORDINALS[st]} time" in goals[0] and f"on its {ORDINALS[st]} visit" in goals[1]
    _hover(ep)
    ep.step()
    assert ep.task_index == 1  # 准备子任务完成
    _press_at_visit(ep, st)
    ep.step(3)
    assert ep.success and not ep.fail
    locked = env.stop_timestep
    assert env.move_interval * (st - 1) <= locked <= env.move_interval * st
    ep.step(env.move_interval + 5)  # 成功后继续：越过 mi·st 仍成功，停止步不被改写
    assert ep.success and not ep.fail
    assert env.stop_timestep == locked


@pytest.mark.parametrize("diff", DIFFS)
def test_stop_on_previous_visit_fails(world, diff):
    ep = _seed_with_stop_time(world, diff, lambda e: e.stop_time >= 2)
    env = ep.env
    _hover(ep)
    ep.step()
    _press_at_visit(ep, env.stop_time - 1)
    _run_to(ep, env.move_interval * env.stop_time)
    assert any(f for _, f, _ in ep.history)
    assert not ep.success


@pytest.mark.parametrize("diff", DIFFS)
def test_press_off_target_fails_immediately(world, diff):
    ep = world.make(diff, seed=1)
    env = ep.env
    _hover(ep)
    ep.step()
    _run_to(ep, _visit_step(env, 1) - env.move_interval // 3)  # 方块离目标还有一段
    ep.press(env.button)
    ep.step()
    assert ep.fail and not ep.success


@pytest.mark.parametrize("diff", DIFFS)
def test_never_pressing_times_out(world, diff):
    ep = world.make(diff, seed=1)
    env = ep.env
    _hover(ep)
    deadline = env.move_interval * env.stop_time
    _run_to(ep, deadline)
    assert not ep.fail
    ep.step()
    assert ep.fail and not ep.success


def test_without_hover_the_final_subgoal_is_never_reached(world):
    ep = _seed_with_stop_time(world, "easy", lambda e: e.stop_time >= 2)
    env = ep.env
    _press_at_visit(ep, env.stop_time)  # 没先悬停按钮：指针停在准备子任务，正确时刻按也不算
    _run_to(ep, env.move_interval * env.stop_time + 1)
    assert ep.fail and not ep.success


def test_stop_freezes_cube(world):
    ep = _seed_with_stop_time(world, "easy", lambda e: e.stop_time >= 2)
    env = ep.env
    _hover(ep)
    ep.step()
    _press_at_visit(ep, env.stop_time)
    frozen = env.cube.xyz.copy()
    ep.step(10)
    assert (env.cube.xyz == frozen).all()
