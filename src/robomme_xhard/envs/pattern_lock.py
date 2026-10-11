"""PatternLock 的 xhard 派生子类。

旋钮：``self.xhard_knobs["length"]`` = 路径节点数 L（xhard12..xhard20 依次 7..11），``grid`` = 5。

实现（计划四.7 表 4.3 行、10-11 裁决 R8、R24）：
- ``configs[<xhard>]`` 已把 ``length`` 钉成 ``[L, L]``、``grid`` 为 5；父类 ``_load_scene`` 用私有
  ``torch.Generator(seed)`` 做拒绝采样，固定长度下整条路径重抽（R8：同 seed 不要求与母档同路径）。
- 父类拒绝采样 1000 次耗尽时只记 debug 日志并“用最后一条”，可能是不足长或越界路径——这是静默
  降级。子类在 ``_load_scene`` 之后用 :func:`check_path_length` 核对实际节点数必须恰为 L，否则抛
  ``SceneGenerationError``（不换 seed、不回走、不接受越界路径）。
- 任务清单由父类按 ``selected_buttons`` 构建，不覆写。
"""

from __future__ import annotations

from mani_skill.utils.registration import register_env

from robomme.robomme_env.PatternLock import PatternLock
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin


def check_path_length(path_len: int, length: int) -> None:
    """路径节点数必须恰为 L；父类拒绝采样耗尽时会悄悄留下其它长度，这里响亮失败。"""
    if int(path_len) != int(length):
        raise SceneGenerationError(
            f"PatternLock 拒绝采样未得到 L={length} 的路径（实际 {path_len} 个节点），不换 seed、不降级"
        )


@register_env("PatternLockXHard")
class PatternLockXHard(XHardMixin, PatternLock):
    robomme_base_id = "PatternLock"

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        check_path_length(len(self.selected_buttons), self.xhard_knobs["length"])
