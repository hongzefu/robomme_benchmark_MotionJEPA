"""ButtonUnmaskSwap 的 xhard 派生子类（S2）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["ButtonUnmaskSwap"]``，实例上读 ``self.xhard_knobs``。

P/S：xhard12 3/4、xhard14 4/6、xhard16 4/8、xhard18 5/10、xhard20 6/12。
- 交换：``swap_min=swap_max=S`` 由配置给出；调度泛化同 VideoUnmaskSwap，配对按 K2/K3
  在父类建场后用独立流预写并证明，不再沿用原 R6 配对。运行复核只记录首条 fatal。
- 按按钮：右起左右交替按 P 次。R27 方案甲（硬约束）：右按钮 ``button_right`` 一律叫
  “press the first button”、左按钮 ``button_left`` 一律叫 “press the second button”，
  ``subgoal_segment`` / ``choice_label`` 同原任务，交替多次也只用这两个名字，使录像器能匹配原 vqa 选项 a/b。
  first / second 指按钮身份而非按压次序。
- 判定：私有边沿计数器（``AlternatingPressCounter``）在每次 ``evaluate`` 前读两侧按钮是否按下，
  只在“期望一侧从释放到按下、另一侧未按下”时推进一次；按住不重复计，错侧或同时按不推进，
  同一物理状态下多次 ``evaluate`` 不多计；每次 reset（``_initialize_episode``）清零。
- 末次交换实际落定早于第一抓：第一抓的 solve 先用现有静止求解器 ``solve_hold_obj``
  等到 ``swap_schedule[-1][3] + 1``，再调父类原 ``solve_pickup_bin``；不新增任务项，故不需要新的 choice_label。
- 两抓尾段（抓 selected_bins[0] → 放下 → 抓 selected_bins[1]）原样保留。

语言契约（主会话 task_goal 派生分支读取）：``xhard_knobs["press_count"]`` = P；``swap_times`` = 实际 S；
``color_names[0..1]`` = 两次抓取对应方块颜色（selected_bins[i] 下是 color_names[i]）；``pick_times`` = 2。
"""

from __future__ import annotations

import torch
from mani_skill.utils.registration import register_env

from robomme.robomme_env.ButtonUnmaskSwap import ButtonUnmaskSwap
from robomme.robomme_env.utils import reset_panda, task4recovery
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
from robomme.robomme_env.utils.subgoal_evaluate_func import (
    is_any_bin_pickup,
    is_bin_pickup,
    is_bin_putdown,
    is_button_pressed,
)
from robomme.robomme_env.utils.subgoal_planner_func import (
    solve_button,
    solve_hold_obj,
    solve_pickup_bin,
    solve_putdown_whenhold,
)

from ..base import XHardMixin
from ..swap_plan import SwapCollisionMixin, certify_swap_plan
from .video_unmask import reject_failure_recovery
from .video_unmask_swap import (
    PARENT_MAX_SWAPS,
    build_extended_swap_schedule,
    check_swap_count,
    clear_extended_swap_pairs,
)

# R27 方案甲：按按钮步骤只用原任务的两个名字（按钮身份，不是次序）
SIDE_BUTTON_NAME = {
    "right": "press the first button",
    "left": "press the second button",
}


def press_sides(press_count: int) -> list[str]:
    """右起左右交替的 P 次按压侧：right, left, right, …"""
    if press_count < 1:
        raise ValueError(f"press_count 必须 ≥1，收到 {press_count}")
    return ["right" if i % 2 == 0 else "left" for i in range(press_count)]


def swap_settle_step(swap_schedule) -> int:
    """末次交换落定后的第一步：父类最后一段动画在 ``end_step`` 结束，取其后一步作为第一抓最早起点。"""
    return int(swap_schedule[-1][3]) + 1


class AlternatingPressCounter:
    """右起交替按压的边沿计数状态机（纯 Python，可在 CPU 上单测）。

    ``update(right_pressed, left_pressed)`` 每次读入两侧按钮当前是否按下：
    - 只有“期望一侧从释放变为按下，且另一侧此刻未按下”才推进一次；
    - 按住不放不会重复推进（只看上升沿）；
    - 错侧上升沿、两侧同时按下都不推进；
    - 同一状态重复调用（多次 evaluate）不多计；
    - ``reset()`` 清空计数与上一状态。
    """

    def __init__(self, sides):
        self.sides = tuple(sides)
        self.reset()

    def reset(self) -> None:
        self.count = 0
        self._prev = {"right": False, "left": False}

    @property
    def done(self) -> bool:
        return self.count >= len(self.sides)

    def update(self, right_pressed: bool, left_pressed: bool) -> int:
        now = {"right": bool(right_pressed), "left": bool(left_pressed)}
        rising = [s for s in ("right", "left") if now[s] and not self._prev[s]]
        self._prev = now
        if not self.done and len(rising) == 1:
            side = rising[0]
            other = "left" if side == "right" else "right"
            if side == self.sides[self.count] and not now[other]:
                self.count += 1
        return self.count


def build_press_tasks(env, press_count: int) -> list[dict]:
    """P 个按按钮任务项；第 i 项完成判据是计数器已推进到 i+1。每项闭包绑定自己的序号与 actor。

    字段写法照抄父类 ``_initialize_episode`` 里的两项按钮任务，只把 func 换成边沿计数判据（父类的
    ``is_any_button_pressed_removelist`` 每个按钮只认一次，无法支持重复按同一侧）。
    """
    tasks = []
    for i, side in enumerate(press_sides(press_count)):
        name = SIDE_BUTTON_NAME[side]
        button = getattr(env, f"button_{side}")
        tasks.append({
            "func": (lambda i=i: env._xhard_press_counter.count >= i + 1),
            "name": name,
            "subgoal_segment": f"{name} at <>",
            "choice_label": name,
            "demonstration": False,
            "failure_func": None,
            "solve": (lambda e, planner, button=button: solve_button(e, planner, obj=button)),
            "segment": env.cap_links[f"button_{side}"],
        })
    return tasks


@register_env("ButtonUnmaskSwapXHard")
class ButtonUnmaskSwapXHard(SwapCollisionMixin, XHardMixin, ButtonUnmaskSwap):
    robomme_base_id = "ButtonUnmaskSwap"
    # 父类 _refresh_swap_schedule 的交换起点
    swap_start_step = 64

    def __init__(self, *args, **kwargs):
        # 第一抓 solve 外包了“等交换落定”；父类失败注入会绕过它直接调 solve_pickup_bin，故拒绝
        reject_failure_recovery(type(self).__name__, kwargs)
        super().__init__(*args, **kwargs)

    def _load_scene(self, options: dict):
        clear_extended_swap_pairs(self)
        super()._load_scene(options)
        check_swap_count(self)
        if int(self.pick_times) != 2:
            raise SceneGenerationError(f"ButtonUnmaskSwap xhard 要求两抓，实际 pick_times={self.pick_times}")
        certify_swap_plan(self, self._swap_actors(), self._bystander_actors(), self.swap_name_prefix)

    def _swap_actors(self):
        return list(self.spawned_bins)

    def _bystander_actors(self):
        # 按钮是关节体，不伪造盒体；保证范围仅为参与交换的对象。
        return []

    def _refresh_swap_schedule(self):
        if self.swap_times <= PARENT_MAX_SWAPS:
            return super()._refresh_swap_schedule()
        self.swap_schedule = build_extended_swap_schedule(self, self.swap_times, self.swap_start_step)

    def _hold_until_swaps_settled(self, env, planner) -> None:
        """第一抓之前用现有静止求解器等到末次交换落定（已过则不等）。"""
        remaining = swap_settle_step(self.swap_schedule) - int(self.elapsed_steps)
        if remaining > 0:
            solve_hold_obj(env, planner, static_steps=remaining, close=True)

    def _update_press_counter(self) -> None:
        counter = self.__dict__.get("_xhard_press_counter")
        if counter is None:
            return
        counter.update(
            is_button_pressed(self, self.button_right),
            is_button_pressed(self, self.button_left),
        )

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        # —— 以下几行照抄父类 _initialize_episode ——
        with torch.device(self.device):
            b = len(env_idx)  # noqa: F841  照抄父类
            self.table_scene.initialize(env_idx)
            qpos = reset_panda.get_reset_panda_param("qpos")
            self.agent.reset(qpos)
        # 【改】每次 reset 清零按压计数与上一状态
        press_count = int(self.xhard_knobs["press_count"])
        self._xhard_press_counter = AlternatingPressCounter(press_sides(press_count))

        # 【改】父类两项按钮任务（first=右、second=左各一次，removelist 判据）→ P 项右起交替按压
        tasks = build_press_tasks(self, press_count)

        # 【改】父类第一抓 solve 为 [solve_pickup_bin(...)]；改为先等末次交换落定再调同一 solve_pickup_bin
        def solve_first_pick(env, planner):
            self._hold_until_swaps_settled(env, planner)
            return solve_pickup_bin(env, planner, obj=self.selected_bins[0])

        # —— 以下任务项除第一抓 "solve" 外照抄父类 ——
        tasks.append(
            {
                "func": (lambda: is_bin_pickup(self, obj=self.selected_bins[0])),
                "name": f"pick up the container that hides the {self.color_names[0]} cube",
                "subgoal_segment": f"pick up the container at <> that hides the {self.color_names[0]} cube",
                "choice_label": "pick up the container",
                "demonstration": False,
                "failure_func": lambda: is_any_bin_pickup(self, [bin for bin in self.spawned_bins if bin != self.selected_bins[0]]),
                "solve": solve_first_pick,  # 【改】见上
                "segment": self.selected_bins[0],
            }
        )
        if self.pick_times == 2:
            tasks.append({
                "func": (lambda: is_bin_putdown(self, obj=self.selected_bins[0])),
                "name": "put down the container",
                "subgoal_segment": "put down the container",
                "choice_label": "put down the container",
                "demonstration": False,
                "failure_func": lambda: is_any_bin_pickup(self, [bin for bin in self.spawned_bins if bin != self.selected_bins[0]]),
                "solve": lambda env, planner: solve_putdown_whenhold(env, planner),
            })
            tasks.append(
                {
                    "func": (lambda: is_bin_pickup(self, obj=self.selected_bins[1])),
                    "name": f"pick up the container that hides the {self.color_names[1]} cube",
                    "subgoal_segment": f"pick up the container at <> that hides the {self.color_names[1]} cube",
                    "choice_label": "pick up the container",
                    "demonstration": False,
                    "failure_func": lambda: is_any_bin_pickup(self, [bin for bin in self.spawned_bins if bin != self.selected_bins[1]]),
                    "solve": lambda env, planner: solve_pickup_bin(env, planner, obj=self.selected_bins[1]),
                    "segment": self.selected_bins[1],
                })

        self.task_list = tasks
        self.recovery_pickup_indices, self.recovery_pickup_tasks = task4recovery(self.task_list)
        # 【改】父类此处按 robomme_failure_recovery 注入失败抓取；本子类在 __init__ 已拒绝该开关
        self.fail_grasp_task_index = None

    def evaluate(self, solve_complete_eval=False):
        # 【改】先按当前物理状态推进边沿计数，再走父类 evaluate（sequential_task_check）
        self._update_press_counter()
        return super().evaluate(solve_complete_eval=solve_complete_eval)
