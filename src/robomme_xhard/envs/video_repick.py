"""VideoRepick 的 xhard 派生子类（S2）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoRepick"]``，实例上读 ``self.xhard_knobs``。

- 母来源是 medium 三方块分支（``SOURCE_DIFFICULTY["VideoRepick"] == "medium"``）；对外 difficulty
  为 xhard 值，父类 ``self.difficulty == "hard"`` 为假，自然走 medium 分支，``configs[...]['cube']==3``。
- 交换 S=5,7,10,13,15：``swap_min=swap_max=S`` 由配置给出（父类 ``torch.randint`` 调用次数不变）；
  父类 ``_refresh_swap_schedule(start_step)`` 只写了 1/2/3 次，子类泛化到 S 次，配对规则同
  VideoUnmaskSwap（R6：前三次保留，第 4 次起循环复用 idx1，idx2 仍由父类 ``step`` 动态取最近块）。
  演示段的 S 个 static 任务由父类 ``_initialize_episode`` 按 ``swap_times`` 自动生成。
- 重抓 R 固定为 2：父类 ``__init__`` 里 ``torch.randint(1, 4, …)`` 照常调用（随机流消耗不变），
  只把赋给 ``self.num_repeats`` 的结果替换为 ``xhard_knobs["repick_count"]``（属性拦截，不改父类代码）。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoRepick import VideoRepick
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin
from .video_unmask_swap import (
    PARENT_MAX_SWAPS,
    build_extended_swap_schedule,
    check_swap_count,
    clear_extended_swap_pairs,
)


@register_env("VideoRepickXHard")
class VideoRepickXHard(XHardMixin, VideoRepick):
    robomme_base_id = "VideoRepick"

    @property
    def num_repeats(self):
        return self.__dict__.get("_xhard_num_repeats")

    @num_repeats.setter
    def num_repeats(self, value):
        knobs = self.__dict__.get("xhard_knobs")
        if knobs is not None:
            # 父类抽到的 1..3 被替换为固定重抓次数（R=2）；抽样调用本身已经发生，随机流不变
            value = int(knobs["repick_count"])
        self.__dict__["_xhard_num_repeats"] = value

    def _load_scene(self, options: dict):
        clear_extended_swap_pairs(self)
        super()._load_scene(options)
        if self.configs[self.difficulty]["cube"] != 3:
            raise SceneGenerationError("VideoRepick xhard 必须走 medium 三方块分支")
        check_swap_count(self)
        if self.num_repeats != int(self.xhard_knobs["repick_count"]):
            raise SceneGenerationError(f"num_repeats={self.num_repeats} 与 knobs repick_count 不一致")

    def _refresh_swap_schedule(self, start_step=400):
        if self.swap_times <= PARENT_MAX_SWAPS:
            return super()._refresh_swap_schedule(start_step)
        self.swap_schedule = build_extended_swap_schedule(self, self.swap_times, start_step)
