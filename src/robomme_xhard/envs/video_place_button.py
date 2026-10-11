"""VideoPlaceButton 的 xhard 派生子类（S1 实现；S0 只建空壳）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoPlaceButton"]``，实例上读 ``self.xhard_knobs``。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoPlaceButton import VideoPlaceButton

from ..base import XHardMixin


@register_env("VideoPlaceButtonXHard")
class VideoPlaceButtonXHard(XHardMixin, VideoPlaceButton):
    robomme_base_id = "VideoPlaceButton"
