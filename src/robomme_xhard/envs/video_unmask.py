"""VideoUnmask 的 xhard 派生子类（S2 实现；S0 只建空壳）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoUnmask"]``，实例上读 ``self.xhard_knobs``。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoUnmask import VideoUnmask

from ..base import XHardMixin


@register_env("VideoUnmaskXHard")
class VideoUnmaskXHard(XHardMixin, VideoUnmask):
    robomme_base_id = "VideoUnmask"
