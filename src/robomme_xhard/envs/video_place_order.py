"""VideoPlaceOrder 的 xhard 派生子类。

旋钮：``self.xhard_knobs["num_targets"]`` = 演示段访问的不同目标数 N（xhard12 为 4）。

实现（计划四.7 表 3.4 行、10-11 裁决 R3、R15、R16）：
- 先完整跑父类 ``_load_scene``（母随机流、``which_targets_to_pick`` 母前缀、``which_in_subset``、
  ``target_target``、``button_task_index`` 全部不变），再用 :func:`extend_targets` 把
  ``which_targets_to_pick`` 扩到 N 个不同目标：保留母前缀，按 ``self.targets`` 原顺序追加尚未访问的
  目标（母档 N=3 时只剩唯一一个，等价于 ``randperm(4)[:4]``，与审查脚本相同）；不重复访问（R16）。
- 答案语义不变：``which_in_subset`` 指向的仍是母前缀里的同一目标，按钮仍插在第
  ``button_task_index // 2`` 组之后；追加组都在母前缀之后。
- 不足 N 个不同目标时抛 ``SceneGenerationError``；母前缀本身已多于 N 时同样响亮失败（不截短）。
- 任务清单由父类 ``_initialize_episode`` 按 ``which_targets_to_pick`` 构建，不覆写。
"""

from __future__ import annotations

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoPlaceOrder import VideoPlaceOrder
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin


def extend_targets(prefix: list, all_targets: list, n: int) -> list:
    """保留母前缀 ``prefix``，按 ``all_targets`` 顺序追加未访问目标直到 ``n`` 个不同目标。"""
    n = int(n)
    prefix = list(prefix)
    if len({id(t) for t in prefix}) != len(prefix):
        raise SceneGenerationError("母前缀里有重复目标")
    if len(prefix) > n:
        raise SceneGenerationError(f"母前缀已有 {len(prefix)} 个目标，多于 N={n}（不截短母档）")
    rest = [t for t in all_targets if all(t is not p for p in prefix)]
    need = n - len(prefix)
    if len(rest) < need:
        raise SceneGenerationError(f"场景只有 {len(all_targets)} 个目标，不足以凑满 N={n} 个不同目标")
    return prefix + rest[:need]


@register_env("VideoPlaceOrderXHard")
class VideoPlaceOrderXHard(XHardMixin, VideoPlaceOrder):
    robomme_base_id = "VideoPlaceOrder"

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        mother = list(self.which_targets_to_pick)
        self.xhard_mother_num_targets = len(mother)
        self.which_targets_to_pick = extend_targets(mother, self.targets, self.xhard_knobs["num_targets"])
        # 答案与按钮位置只依赖母前缀，扩展后必须不变
        if self.which_targets_to_pick[self.which_in_subset - 1] is not self.target_target:
            raise SceneGenerationError("扩展目标后 which_in_subset 指向的目标变了")
        if self.button_task_index > 2 * len(mother):
            raise SceneGenerationError("button_task_index 超出母前缀范围")
