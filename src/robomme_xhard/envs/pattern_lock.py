"""PatternLock 的 xhard 派生子类（S1 实现；S0 只建空壳）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["PatternLock"]``，实例上读 ``self.xhard_knobs``。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.PatternLock import PatternLock

from ..base import XHardMixin


@register_env("PatternLockXHard")
class PatternLockXHard(XHardMixin, PatternLock):
    robomme_base_id = "PatternLock"
