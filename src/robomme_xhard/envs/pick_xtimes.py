"""PickXtimes 的 xhard 派生子类。

旋钮：``self.xhard_knobs["repeats"]`` = 抓放次数 n（xhard12..xhard20 依次 6..10）。

只靠配置覆盖即可，子类保持空体（已核实，见 tests/test_s1_configs.py）：
- ``configs[<xhard>]`` 的 ``number_min = number_max = n``，父类 ``__init__`` 用私有
  ``torch.Generator(seed)`` 抽 ``randint(n, n+1)``，结果恒为 n，不影响母场景随机流；
- 任务清单按 ``range(self.num_repeats)`` 生成，序数取 ``subgoal_language.get_subgoal_with_index``，
  其上限是第 10 次（idx 0..9），n ≤ 10 不越界（计划：10 次是序数语言上限，不增到 11）；
- ``task_goal`` 的 PickXtimes 分支读 ``num_repeats``，``num2words`` 覆盖到 20；
- 父类没有其它依赖次数的上限，也没有 ``difficulty == "hard"`` 字面比较。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.PickXtimes import PickXtimes

from ..base import XHardMixin


@register_env("PickXtimesXHard")
class PickXtimesXHard(XHardMixin, PickXtimes):
    robomme_base_id = "PickXtimes"
