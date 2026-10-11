"""VideoUnmaskSwap 的 xhard 派生子类（S2 实现；S0 只建空壳）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoUnmaskSwap"]``，实例上读 ``self.xhard_knobs``。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoUnmaskSwap import VideoUnmaskSwap

from ..base import XHardMixin


@register_env("VideoUnmaskSwapXHard")
class VideoUnmaskSwapXHard(XHardMixin, VideoUnmaskSwap):
    robomme_base_id = "VideoUnmaskSwap"
