"""RouteStick 的 xhard 派生子类。

旋钮：``self.xhard_knobs["length"]`` = 路径边数 S（xhard12..xhard20 依次 6..10）。

实现（计划四.7 表 4.4 行、10-11 裁决 R8）：
- ``configs[<xhard>]`` 已把 ``length`` 钉成 ``[S, S]``，``backtrack=True`` 等其它 hard 键原样继承；
  父类 ``_load_scene`` 抽 ``steps = randint(S, S+1) = S``，``generate_dynamic_walk`` 每步必有相邻
  候选，恒生成 S 条边、S+1 个节点，随后按路径逐边抽旋转方向并构建演示与执行两段任务清单。
  同 seed 整条路径按固定长度重抽，不要求与母档同路径（R8）。
- 子类只在 ``_load_scene`` 之后用 :func:`check_route_length` 核对边数恰为 S、方向数与边数一致，
  不符即抛 ``SceneGenerationError``（防御性检查，父类正确时不触发）。
"""

from __future__ import annotations

from mani_skill.utils.registration import register_env

from robomme.robomme_env.RouteStick import RouteStick
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin


def check_route_length(n_nodes: int, n_directions: int, length: int) -> None:
    """边数（节点数 − 1）必须恰为 S，旋转方向数必须等于边数。"""
    edges = int(n_nodes) - 1
    if edges != int(length) or int(n_directions) != edges:
        raise SceneGenerationError(
            f"RouteStick 路径边数 {edges}、方向数 {n_directions} 与要求 S={length} 不符"
        )


@register_env("RouteStickXHard")
class RouteStickXHard(XHardMixin, RouteStick):
    robomme_base_id = "RouteStick"

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        check_route_length(len(self.selected_buttons), len(self.swing_directions), self.xhard_knobs["length"])
