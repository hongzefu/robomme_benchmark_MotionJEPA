"""VideoRepick 的 xhard 派生子类（S2 实现；S0 只建空壳）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoRepick"]``，实例上读 ``self.xhard_knobs``。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoRepick import VideoRepick

from ..base import XHardMixin


@register_env("VideoRepickXHard")
class VideoRepickXHard(XHardMixin, VideoRepick):
    robomme_base_id = "VideoRepick"
