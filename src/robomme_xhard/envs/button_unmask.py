"""ButtonUnmask 的 xhard 派生子类（S2）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["ButtonUnmask"]``，实例上读 ``self.xhard_knobs``。

xhard14（pick_count=3）：仍是“先按一次按钮再抓”；父类生成“按按钮 → 抓 bin_0 → 放下 → 抓 bin_1”，
子类在其后追加“放下 bin_1 → 抓 bin_2”（R17）。不新增物体（R15），不加干扰容器（RL10）。

语言契约：``self.color_names[0..2]`` 依次是三次抓取对应的方块颜色（颜色 ``color_names[i]``
的方块在 ``bin_i`` 下）。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.ButtonUnmask import ButtonUnmask

from ..base import XHardMixin
from .video_unmask import append_extra_picks, reject_failure_recovery


@register_env("ButtonUnmaskXHard")
class ButtonUnmaskXHard(XHardMixin, ButtonUnmask):
    robomme_base_id = "ButtonUnmask"

    def __init__(self, *args, **kwargs):
        reject_failure_recovery(type(self).__name__, kwargs)
        super().__init__(*args, **kwargs)

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        append_extra_picks(self)
