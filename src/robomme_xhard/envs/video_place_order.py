"""VideoPlaceOrder 的 xhard 派生子类（S1 实现；S0 只建空壳）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoPlaceOrder"]``，实例上读 ``self.xhard_knobs``。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoPlaceOrder import VideoPlaceOrder

from ..base import XHardMixin


@register_env("VideoPlaceOrderXHard")
class VideoPlaceOrderXHard(XHardMixin, VideoPlaceOrder):
    robomme_base_id = "VideoPlaceOrder"
