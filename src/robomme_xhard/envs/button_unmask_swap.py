"""ButtonUnmaskSwap 的 xhard 派生子类（S2 实现；S0 只建空壳）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["ButtonUnmaskSwap"]``，实例上读 ``self.xhard_knobs``。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.ButtonUnmaskSwap import ButtonUnmaskSwap

from ..base import XHardMixin


@register_env("ButtonUnmaskSwapXHard")
class ButtonUnmaskSwapXHard(XHardMixin, ButtonUnmaskSwap):
    robomme_base_id = "ButtonUnmaskSwap"
