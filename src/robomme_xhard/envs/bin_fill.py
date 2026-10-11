"""BinFill 的 xhard 派生子类。

旋钮：``self.xhard_knobs["target_total"]`` = 投入总块数 K（xhard12..xhard20 依次 5..9）。

实现（计划四.7 表 1.1 行、10-11 裁决 R7、R15、R20）：
1. 先完整跑父类 ``_load_scene``：母布局、母库存（实际生成成功的方块）、母随机流全部不变；
2. 再用纯函数 :func:`allocate_targets` 把红/蓝/绿目标数改成总数 K：
   先在母档已有目标的颜色里按 red→blue→green 轮流逐块追加，某色库存用尽即跳过；
   母档活跃色都满后，再扩到其它有库存的颜色（R7：允许把母档原本没有目标的颜色选为目标）；
   总库存不足 K 则抛 ``SceneGenerationError``（不换 seed、不降级）。
3. 不新生成任何方块（R15）。父类 ``_initialize_episode`` 按 ``*_target_number`` 构建任务清单，
   ``task_goal.get_language_goal`` 的 BinFill 分支也读这三个属性，因此任务清单与语言随之同步，
   ``_initialize_episode`` 不需要覆写。
"""

from __future__ import annotations

from mani_skill.utils.registration import register_env

from robomme.robomme_env.BinFill import BinFill
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin


def allocate_targets(mother_targets, inventory, total):
    """按 R7 规则把目标数扩到总数 ``total``，返回新的 [red, blue, green] 目标数。

    - ``mother_targets``：母档 [red, blue, green] 目标数；
    - ``inventory``：每色实际生成成功的方块数（库存）；
    - ``total``：目标总数 K。

    先在母档活跃色（目标数 > 0）里按 red→blue→green 轮流逐块追加，某色达到库存即跳过；
    活跃色都满后再按同顺序扩到其它有库存的颜色。K 小于母目标总数或总库存不足时抛
    ``SceneGenerationError``，不悄悄降级。
    """
    mother = [int(x) for x in mother_targets]
    inv = [int(x) for x in inventory]
    k = int(total)
    if len(mother) != 3 or len(inv) != 3:
        raise ValueError(f"需要三色计数，收到 mother={mother!r} inventory={inv!r}")
    if any(m > i for m, i in zip(mother, inv)):
        raise SceneGenerationError(f"母目标 {mother} 超过库存 {inv}，母场景本身不合法")
    if k < sum(mother):
        raise SceneGenerationError(f"K={k} 小于母目标总数 {sum(mother)}（只增不减）")
    active = [i for i in range(3) if mother[i] > 0]
    others = [i for i in range(3) if mother[i] == 0 and inv[i] > 0]
    new = list(mother)
    for pool in (active, others):
        while sum(new) < k and any(new[i] < inv[i] for i in pool):
            for i in pool:
                if sum(new) < k and new[i] < inv[i]:
                    new[i] += 1
    if sum(new) < k:
        raise SceneGenerationError(f"库存 {inv}（合计 {sum(inv)}）不足以分配 K={k}，不换 seed")
    return new


@register_env("BinFillXHard")
class BinFillXHard(XHardMixin, BinFill):
    robomme_base_id = "BinFill"

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        mother = [
            self.red_cubes_target_number,
            self.blue_cubes_target_number,
            self.green_cubes_target_number,
        ]
        inventory = [len(self.red_cubes), len(self.blue_cubes), len(self.green_cubes)]
        new = allocate_targets(mother, inventory, self.xhard_knobs["target_total"])
        # 留档用：母目标与库存
        self.xhard_mother_targets_rgb = mother
        self.xhard_inventory_rgb = inventory
        (
            self.red_cubes_target_number,
            self.blue_cubes_target_number,
            self.green_cubes_target_number,
        ) = new
