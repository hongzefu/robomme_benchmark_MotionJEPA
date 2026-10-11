"""SwingXtimes 的 xhard 派生子类。

旋钮：``self.xhard_knobs["repeats"]`` = 往返次数 n（xhard12..xhard20 依次 4、5、7、8、9）。

只靠配置覆盖即可，子类保持空体（已核实，见 tests/test_s1_configs.py）：
- ``configs[<xhard>]`` 的 ``number_min = number_max = n``，父类 ``__init__`` 用私有
  ``torch.Generator(seed)`` 抽 ``randint(n, n+1)``，结果恒为 n；
- ``max_swings`` 在父类 ``_initialize_episode`` 里按 ``self.num_repeats * 2`` 自动派生，
  不是独立旋钮（计划 1.3 节），``too_many_swings`` 判据随之放宽；
- 任务清单按 ``range(self.num_repeats)`` 生成，子目标名的序数取父类内置的 10 项列表
  （first..tenth，超出才退化为 ``"{i+1}th"``），n ≤ 9 不越界；
- ``task_goal`` 的 SwingXtimes 分支读 ``num_repeats``，``num2words`` 覆盖到 20。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.SwingXtimes import SwingXtimes

from ..base import XHardMixin


@register_env("SwingXtimesXHard")
class SwingXtimesXHard(XHardMixin, SwingXtimes):
    robomme_base_id = "SwingXtimes"
