"""VideoPlaceButton 的 xhard 派生子类。

旋钮：``self.xhard_knobs["extra_groups"]`` = 额外抓放组数 a（xhard12 a=1、xhard14 a=2）。

实现（计划四.7 表 3.3 行、红线 RL8、RL10、RL12，10-11 裁决 R15、R16）：
- 先完整跑父类 ``_load_scene``（hard：additional_place=False，pre_flag=post_flag=0，母随机流、
  ``task_flag`` 与正确答案 ``target_target`` 全部不变），再重建演示段任务清单：
  - 前侧：在原第一组（抓 → 放 target_0）之前插入 “抓 → 放 target_2” 一组；
  - 后侧：在原 “放 target_1”（按钮后第一落点）之后插入 “抓 → 放 target_3” 一组。
  按钮前最后落点仍是 target_0、按钮后第一落点仍是 target_1，“按钮紧前／紧后”的答案不变。
- a=2：前后各一组；a=1：前侧或后侧各 50% 概率，由 :func:`choose_sides` 用母 seed 与档位数字
  派生的独立随机流 ``np.random.default_rng([seed, 档位数字])`` 抽取（与审查脚本同一取法），
  不消耗母 generator，同 seed 同档可复现。
- 插入后重算 ``recovery_pickup_indices`` / ``recovery_pickup_tasks``；若开启失败注入，
  ``fail_grasp_task_index`` 按插入位置平移，仍指向原被注入的任务。
- 只用场景已有的 target_2、target_3 与目标方块，不新增物体（R15），不搬已撤回的“重复回原位”玩法。
"""

from __future__ import annotations

import numpy as np

from mani_skill.utils.registration import register_env

import importlib
from robomme.robomme_env.VideoPlaceButton import VideoPlaceButton
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin

# 父类模块（只读取其中的工具函数，不改它）。包 __init__ 用同名类遮住了子模块属性，故按模块全名取
_vpb_module = importlib.import_module("robomme.robomme_env.VideoPlaceButton")

FRONT = "front"
BACK = "back"


def tier_number(label: str) -> int:
    """``"xhard12"`` → 12。"""
    return int(str(label).strip().lower().removeprefix("xhard"))


def choose_sides(seed: int, extra_groups: int, label: str) -> list[str]:
    """决定额外抓放组插在哪一侧。a=2 前后各一组；a=1 前／后各 50%，同 seed 同档可复现。"""
    a = int(extra_groups)
    if a == 2:
        return [FRONT, BACK]
    if a == 1:
        rng = np.random.default_rng([int(seed), tier_number(label)])
        return [FRONT if rng.random() < 0.5 else BACK]
    raise ValueError(f"VideoPlaceButton 只支持 extra_groups=1 或 2，收到 {extra_groups!r}（R16 否定更多组）")


def insert_extra_groups(tasks: list, sides: list[str], anchor_back: int, front_group: list, back_group: list):
    """把额外组插进任务清单（纯函数）。

    - ``anchor_back``：原 “放 target_1” 任务在 ``tasks`` 里的下标，后侧组插在它之后；
    - 前侧组插在最前面。
    返回 ``(新清单, shift)``，``shift(i)`` 把原下标映射到新下标。
    """
    if not 0 <= anchor_back < len(tasks):
        raise IndexError(f"anchor_back={anchor_back} 越界（len={len(tasks)}）")
    new = list(tasks)
    n_back = n_front = 0
    if BACK in sides:
        new[anchor_back + 1:anchor_back + 1] = list(back_group)
        n_back = len(back_group)
    if FRONT in sides:
        new[0:0] = list(front_group)
        n_front = len(front_group)

    def shift(i):
        if i is None:
            return None
        return i + n_front + (n_back if i > anchor_back else 0)

    return new, shift


@register_env("VideoPlaceButtonXHard")
class VideoPlaceButtonXHard(XHardMixin, VideoPlaceButton):
    robomme_base_id = "VideoPlaceButton"

    def _make_pick_task(self):
        # 与父类演示段 “pick up the cube” 同一写法（不复制父类字典，避免带上失败注入）
        is_obj_pickup = _vpb_module.is_obj_pickup
        solve_pickup = _vpb_module.solve_pickup
        return {
            "func": (lambda: is_obj_pickup(self, obj=self.target_cube)),
            "name": f"pick up the cube",
            "subgoal_segment": f"pick up the cube at <>",
            "choice_label": "pick up the cube",
            "demonstration": True,
            "failure_func": None,
            "solve": lambda env, planner: solve_pickup(
                env, planner, obj=self.target_cube
            ),
            "segment": self.target_cube,
        }

    def _make_drop_task(self, target_name: str):
        # 与父类演示段 “drop the cube onto target” 同一写法
        is_obj_dropped_onto = _vpb_module.is_obj_dropped_onto
        solve_putonto_whenhold = _vpb_module.solve_putonto_whenhold
        target = getattr(self, target_name)
        return {
            "func": (
                lambda target=target: is_obj_dropped_onto(
                    self, obj=self.target_cube, target=target
                )
            ),
            "name": "drop the cube onto target",
            "subgoal_segment": f"drop the cube onto target at <>",
            "choice_label": "drop onto",
            "demonstration": True,
            "failure_func": None,
            "solve": lambda env, planner, target=target: solve_putonto_whenhold(
                env, planner, target=target
            ),
            "segment": target,
        }

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        if bool(self.pre_flag) or bool(self.post_flag):
            raise SceneGenerationError("母配置意外开启 additional_place，xhard 档要求 pre/post_flag 均为 0")
        for name in ("target_0", "target_1", "target_2", "target_3"):
            if getattr(self, name, None) is None:
                raise SceneGenerationError(f"VideoPlaceButton 缺少 {name}，无法追加抓放组（不新增物体）")

        tasks = list(self.task_list)
        t1_drops = [
            i
            for i, t in enumerate(tasks)
            if t.get("demonstration") and t.get("name") == "drop the cube onto target" and t.get("segment") is self.target_1
        ]
        if len(t1_drops) != 1:
            raise SceneGenerationError(f"演示段“放 target_1”应恰有 1 项，实际 {len(t1_drops)}")
        sides = choose_sides(self.seed, self.xhard_knobs["extra_groups"], self.xhard_label)
        front_group = [self._make_pick_task(), self._make_drop_task("target_2")]
        back_group = [self._make_pick_task(), self._make_drop_task("target_3")]
        new_tasks, shift = insert_extra_groups(tasks, sides, t1_drops[0], front_group, back_group)

        self.xhard_extra_sides = sides
        self.task_list = new_tasks
        self.recovery_pickup_indices, self.recovery_pickup_tasks = _vpb_module.task4recovery(self.task_list)
        self.fail_grasp_task_index = shift(self.fail_grasp_task_index)
