"""StopCube 的 xhard 派生子类。

旋钮：``self.xhard_knobs["stop_k"]`` = 第几次经过时按停，``self.xhard_knobs["move_interval"]`` =
单程间隔步数（xhard14 4/80、xhard16 5/80、xhard18 7/60、xhard20 6/80；StopCube 没有 configs 字典）。

实现（计划四.7 表 1.4 行、10-11 裁决 R13、R16）：
1. ``_initialize_episode``：先完整跑父类（私有 ``torch.Generator(seed)`` 的全部抽取——interval、
   move_interval 下标、stop_time、旋转角——次数与顺序原样不变，方块起点、终点不变），
   再只把抽到的 ``move_interval`` 与 ``stop_time`` 换成旋钮值，按父类同一公式同步派生量
   ``steps_press``、``stop_time_range``，并重建任务清单中依赖 ``steps_press`` 的 “remain static”
   检查点（首项 “move to the top of the button to prepare” 与末项按按钮任务原样复用）。
   母档原值另存 ``xhard_mother_stop_time`` / ``xhard_mother_move_interval`` 供留档。
2. ``step``：父类写死 ``range(5)`` 只让方块走 5 程，k=6、7 需要更多程。R13 已批准只在子类覆写：
   函数体逐字复制父类 ``StopCube.step``，只改两处（已在行尾注释标出）：
   ``range(5)`` → ``range(move_segment_count(self.stop_time))``（= max(5, k)，k ≤ 5 时与父类完全相同）；
   ``super().step`` → ``super(StopCube, self).step``（跳过父类 step 本身，调用 BaseEnv.step）。
"""

from __future__ import annotations

from typing import Dict, Union

import numpy as np
import torch

from mani_skill.utils.registration import register_env

import importlib
from robomme.robomme_env.StopCube import StopCube

from ..base import XHardMixin

# 父类模块（只读取其中的工具函数，不改它）。robomme.robomme_env 包的 __init__ 用同名类遮住了
# 子模块属性，``import robomme.robomme_env.StopCube as m`` 拿到的是类，故按模块全名取
_stopcube_module = importlib.import_module("robomme.robomme_env.StopCube")

# 父类 step 写死的程数
PARENT_MOVE_SEGMENTS = 5


def stopcube_schedule(stop_k: int, move_interval: int, interval: int = 30) -> dict:
    """按父类 ``StopCube._initialize_episode`` 的同一公式算派生量（纯函数，便于不起仿真测试）。

    返回 ``steps_press``、``stop_time_range``、``static_checkpoints``。
    """
    stop_k = int(stop_k)
    move_interval = int(move_interval)
    if stop_k < 1 or move_interval < 1:
        raise ValueError(f"stop_k={stop_k}、move_interval={move_interval} 必须为正")
    steps_press = move_interval * (stop_k) - move_interval / 2
    stop_time_range = (move_interval * (stop_k - 1), move_interval * (stop_k))
    final_abs_timestep = steps_press - interval
    static_checkpoints = list(range(100, int(final_abs_timestep), 100))
    if not static_checkpoints or static_checkpoints[-1] != final_abs_timestep:
        static_checkpoints.append(final_abs_timestep)
    return {
        "steps_press": steps_press,
        "stop_time_range": stop_time_range,
        "static_checkpoints": static_checkpoints,
    }


def move_segment_count(stop_time: int) -> int:
    """step 里让方块往返的程数：至少覆盖父类的 5 程，k 更大时扩到 k 程。"""
    return max(PARENT_MOVE_SEGMENTS, int(stop_time))


@register_env("StopCubeXHard")
class StopCubeXHard(XHardMixin, StopCube):
    robomme_base_id = "StopCube"

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        super()._initialize_episode(env_idx, options)

        stop_k = int(self.xhard_knobs["stop_k"])
        move_interval = int(self.xhard_knobs["move_interval"])
        self.xhard_mother_stop_time = self.stop_time
        self.xhard_mother_move_interval = self.move_interval

        sched = stopcube_schedule(stop_k, move_interval, self.interval)
        self.move_interval = move_interval
        self.stop_time = stop_k
        self.steps_press = sched["steps_press"]
        self.stop_time_range = sched["stop_time_range"]

        old = list(self.task_list)
        head, tail = old[0], old[-1]
        if head.get("name") != "move to the top of the button to prepare" or tail.get(
            "name"
        ) != "press the button to stop the cube on the target":
            raise RuntimeError(
                "StopCube 父类任务清单结构与预期不符，拒绝重建：" f"{[t.get('name') for t in old]}"
            )
        before_absTimestep = _stopcube_module.before_absTimestep
        solve_hold_obj_absTimestep = _stopcube_module.solve_hold_obj_absTimestep
        statics = []
        # 与父类同一写法生成 “remain static” 检查点任务
        for target_timestep in sched["static_checkpoints"]:
            statics.append({
                                "func": lambda target_timestep=target_timestep: before_absTimestep(self, absTimestep=target_timestep),
                                "name": "remain static",
                                "subgoal_segment": "remain static",
                                "choice_label": "remain static",
                                "demonstration": False,
                                "failure_func": None,
                                "specialflag":"swap",
                                "solve": lambda env, planner, target_timestep=target_timestep: solve_hold_obj_absTimestep(env, planner,absTimestep=target_timestep),
                                },)
        self.task_list = [head] + statics + [tail]

    # 以下函数体逐字复制自父类 StopCube.step，只改两处（行尾注释“xhard 改动”）
    def step(self, action: Union[None, np.ndarray, torch.Tensor, Dict]):
        is_button_pressed = _stopcube_module.is_button_pressed
        move_straight_line = _stopcube_module.move_straight_line

        if is_button_pressed(self, obj=self.button):# Chronological issue, MUST be placed before super!!!
            self.stop=True


        obs, reward, terminated, truncated, info = super(StopCube, self).step(action)  # xhard 改动：super() → super(StopCube, self)


        # Use the rotated xy coordinates calculated in _initialize_episode
        start_pos = [self.start_pos_xy[0], self.start_pos_xy[1], self.cube_half_size / 2]
        end_pos = [self.end_pos_xy[0], self.end_pos_xy[1], self.cube_half_size / 2]

        # Alternate between the two waypoints so the cube makes five passes
        for segment in range(move_segment_count(self.stop_time)):  # xhard 改动：range(5) → range(max(5, k))（R13 已批）
            move_straight_line(
                self,
                cube=self.cube,
                start_step=self.move_interval * segment,
                end_step=self.move_interval * (segment + 1),
                cur_step=int(self.elapsed_steps),
                start_pos=start_pos if segment % 2 == 0 else end_pos,
                end_pos=end_pos if segment % 2 == 0 else start_pos,
                stop=self.stop,
            )
        return obs, reward, terminated, truncated, info
