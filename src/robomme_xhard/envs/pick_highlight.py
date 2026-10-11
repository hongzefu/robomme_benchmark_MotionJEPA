"""PickHighlight 的 xhard 派生子类。

旋钮：``self.xhard_knobs["pickup"]`` = 高亮（须抓）块数，``self.xhard_knobs["spawn"]`` = 生成块数
（xhard12 4/6、xhard16 5/6、xhard18 6/6；xhard14、xhard20 缺档）。

实现（计划四.7 表 3.1 行、10-11 裁决 R5、R15）：
- ``configs[<xhard>]`` 已覆盖 ``spawn``、``pickup``，父类 ``_load_scene`` 据此生成方块、
  ``randperm(len(all_cubes))[:pickup]`` 选高亮目标并构建任务清单；``step`` 的高亮数取
  ``min(pickup, len(target_cubes))``，也随配置同步。
- 父类在方块生成失败时只记日志、少生成，``randperm(...)[:pickup]`` 也会悄悄少选；子类在
  ``_load_scene`` 之后核对实际方块数 = spawn、高亮目标数 = pickup，不足即抛
  ``SceneGenerationError``，不降级。
- R5：pickup = 6 = spawn 时六块全高亮，记忆要求退化为“全抓”，按裁决保留。
- 不新增第七个方块（R15）。
"""

from __future__ import annotations

from mani_skill.utils.registration import register_env

from robomme.robomme_env.PickHighlight import PickHighlight
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin


def check_highlight_counts(n_cubes: int, n_targets: int, spawn: int, pickup: int) -> None:
    """实际方块数与高亮目标数必须分别等于 spawn 与 pickup，否则响亮失败。"""
    if int(n_cubes) != int(spawn):
        raise SceneGenerationError(f"PickHighlight 实际生成 {n_cubes} 块，要求 spawn={spawn}")
    if int(n_targets) != int(pickup):
        raise SceneGenerationError(f"PickHighlight 实际高亮 {n_targets} 块，要求 pickup={pickup}")


@register_env("PickHighlightXHard")
class PickHighlightXHard(XHardMixin, PickHighlight):
    robomme_base_id = "PickHighlight"

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        check_highlight_counts(
            len(self.all_cubes),
            len(self.target_cubes),
            self.xhard_knobs["spawn"],
            self.xhard_knobs["pickup"],
        )
