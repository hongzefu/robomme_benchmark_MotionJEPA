"""独立验证用的错误动作策略；通过原版规划和物理动作触发，不改成功标志。"""

import gymnasium as gym

from .planner import make_execution_planner
from robomme.robomme_env.utils.subgoal_planner_func import (
    solve_button,
    solve_pickup,
    solve_pickup_bin,
    solve_putdown_whenhold,
    solve_putonto_whenhold_binspecial,
    solve_swingonto_withDirection,
)

PROBES = (
    "early_button",
    "wrong_target",
    "wrong_order",
    "wrong_direction",
    "incomplete_cycle",
    "wrong_count",
)


class _TerminalReached(BaseException):
    """验证策略在原版包装器返回终止后停止，不能被规划器重试吞掉。"""


class _StopAtTerminal(gym.Wrapper):
    def step(self, action):
        result = self.env.step(action)
        if bool(result[2]) or bool(result[3]):
            raise _TerminalReached()
        return result


def execute_probe(env, probe):
    base = env.unwrapped
    wrapped = _StopAtTerminal(env.native_wrapper)
    planner = make_execution_planner(wrapped, env.task_kind)
    env.recorder.frames[-1]["info"]["probe"] = probe
    try:
        if probe == "early_button" and env.task_kind in ("BinFill", "VideoRepick"):
            solve_button(wrapped, planner, base.button)
        elif (
            probe in ("wrong_target", "wrong_order")
            and env.task_kind == "VideoUnmaskSwap"
        ):
            if probe == "wrong_order" and base.pick_times != 2:
                raise ValueError("错序验证要求两次抓取的场景")
            wrong = (
                base.selected_bins[1]
                if probe == "wrong_order"
                else next(
                    actor
                    for actor in base.spawned_bins
                    if actor is not base.selected_bins[0]
                )
            )
            solve_pickup_bin(wrapped, planner, wrong)
        elif probe == "wrong_target" and env.task_kind == "VideoRepick":
            wrong = next(
                actor for actor in base.spawned_cubes if actor is not base.target_cube_1
            )
            solve_pickup(wrapped, planner, wrong)
        elif probe == "wrong_direction" and env.task_kind == "RouteStick":
            opposite = (
                "counterclockwise"
                if base.swing_directions[0] == "clockwise"
                else "clockwise"
            )
            solve_swingonto_withDirection(
                wrapped,
                planner,
                target=base.selected_buttons[1],
                radius=0.2,
                direction=opposite,
            )
        elif probe == "incomplete_cycle" and env.task_kind == "VideoRepick":
            if base.num_repeats < 2:
                raise ValueError("未完成次数验证要求repeat_count至少为2")
            solve_pickup(wrapped, planner, base.target_cube_1)
            solve_putdown_whenhold(wrapped, planner, release_z=0.01)
            solve_button(wrapped, planner, base.button)
        elif probe == "wrong_count" and env.task_kind == "BinFill":
            choices = [
                (
                    getattr(base, f"{color}_cubes_target_number"),
                    getattr(base, f"{color}_cubes"),
                )
                for color in ("red", "blue", "green")
            ]
            required, actors = next(
                (count, values) for count, values in choices if len(values) > count
            )
            for actor in actors[: required + 1]:
                solve_pickup(wrapped, planner, actor)
                solve_putonto_whenhold_binspecial(
                    wrapped, planner, target=base.board_with_hole
                )
            solve_button(wrapped, planner, base.button)
        else:
            raise ValueError(f"{env.task_kind}不支持验证动作{probe}")
    except _TerminalReached:
        pass
    return env.recorder.frames
