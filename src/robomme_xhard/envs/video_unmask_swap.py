"""VideoUnmaskSwap 的 xhard 派生子类（S2）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoUnmaskSwap"]``，实例上读 ``self.xhard_knobs``。

S=4,5,7,9,11：父类 ``_refresh_swap_schedule`` 只写了 1/2/3 次三个分支，S≥4 时 ``swap_schedule``
不会被创建、``step`` 会 AttributeError。子类覆写它，把调度补到 S 次：
- 时间段沿用父类写法：第 k 次交换占 ``[64 + 50(k-1), 64 + 50k)`` 环境步，首尾相接；
- 配对按 K2/K3：父类建场后用独立随机流规划，发起者在参与次数最少的候选中抽取，
  避开上一段的两个对象，搭档取最近邻；全部 1..S 配对经整段扫掠证明后预写。
  原 R6 配对规则不再用于实际交换，循环辅助仅保留为建场时的临时调度占位。
  运行期段起点与物理子步复核失败只记 ``_xhard_fatal``，不截断仿真。
pick 仍为 2（父类 ``pick_times`` 由 hard 配置 pick_min=pick_max=2 抽出）。

本文件里的交换调度辅助函数也供 ``button_unmask_swap.py``、``video_repick.py`` 复用。
"""

from __future__ import annotations

import re

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoUnmaskSwap import VideoUnmaskSwap
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from ..base import XHardMixin
from ..swap_plan import SwapCollisionMixin, certify_swap_plan

# 父类写死的前三次交换数与每段时长
PARENT_MAX_SWAPS = 3
SWAP_DURATION = 50

_EXT_PAIR_ATTR = re.compile(r"^swap_pair(\d+)_idx[12]$")


def swap_windows(swap_times: int, start_step: int, duration: int = SWAP_DURATION) -> list[tuple[int, int]]:
    """第 k 次（k=1..S）交换的环境步区间 ``[start + d(k-1), start + dk)``，与父类 1..3 次分支同式。"""
    if swap_times < 1:
        raise ValueError(f"swap_times 必须 ≥1，收到 {swap_times}")
    return [(start_step + duration * k, start_step + duration * (k + 1)) for k in range(swap_times)]


def cyclic_base_index(k: int) -> int:
    """建场临时调度的配对序号：1,2,3,1,2,3,…；实际配对随后由 K2/K3 证书覆盖。"""
    if k < 1:
        raise ValueError(f"交换序号从 1 开始，收到 {k}")
    return (k - 1) % PARENT_MAX_SWAPS + 1


def clear_extended_swap_pairs(env) -> None:
    """删除上一次 _load_scene 遗留的第 4 次及以后的配对属性（父类每次 _load_scene 都把 1..3 次的 idx2 置 None）。"""
    for name in list(vars(env)):
        m = _EXT_PAIR_ATTR.match(name)
        if m and int(m.group(1)) > PARENT_MAX_SWAPS:
            delattr(env, name)


def build_extended_swap_schedule(env, swap_times: int, start_step: int) -> list[tuple]:
    """泛化到 S 次的调度：缺失的第 k≥4 次 idx1 循环复用前三次，idx2 只在缺失时初始化为 None。"""
    windows = swap_windows(swap_times, start_step)
    schedule = []
    for k in range(1, swap_times + 1):
        idx1_name, idx2_name = f"swap_pair{k}_idx1", f"swap_pair{k}_idx2"
        if k > PARENT_MAX_SWAPS:
            if not hasattr(env, idx1_name):
                setattr(env, idx1_name, getattr(env, f"swap_pair{cyclic_base_index(k)}_idx1"))
            if not hasattr(env, idx2_name):
                setattr(env, idx2_name, None)
        start, end = windows[k - 1]
        schedule.append((getattr(env, idx1_name), getattr(env, idx2_name), start, end))
    return schedule


def check_swap_count(env) -> None:
    """S 必须等于 knobs，调度段数必须等于 S；不符即响亮失败。"""
    expected = int(env.xhard_knobs["swap_count"])
    if int(env.swap_times) != expected:
        raise SceneGenerationError(f"swap_times={env.swap_times} 与 knobs swap_count={expected} 不一致")
    if len(env.swap_schedule) != expected:
        raise SceneGenerationError(f"swap_schedule 段数 {len(env.swap_schedule)} ≠ S={expected}")


@register_env("VideoUnmaskSwapXHard")
class VideoUnmaskSwapXHard(SwapCollisionMixin, XHardMixin, VideoUnmaskSwap):
    robomme_base_id = "VideoUnmaskSwap"
    # 父类 _refresh_swap_schedule 的交换起点（前 64 步是容器抬起放回的演示）
    swap_start_step = 64

    def _load_scene(self, options: dict):
        clear_extended_swap_pairs(self)
        super()._load_scene(options)
        check_swap_count(self)
        if int(self.pick_times) != 2:
            raise SceneGenerationError(f"VideoUnmaskSwap xhard 要求两抓，实际 pick_times={self.pick_times}")
        certify_swap_plan(self, self._swap_actors(), self._bystander_actors(), self.swap_name_prefix)

    def _swap_actors(self):
        return list(self.spawned_bins)

    def _bystander_actors(self):
        # 保证范围仅为参与交换的对象；按钮、机械臂和桌面不入判据。
        return []

    def _refresh_swap_schedule(self):
        if self.swap_times <= PARENT_MAX_SWAPS:
            return super()._refresh_swap_schedule()
        self.swap_schedule = build_extended_swap_schedule(self, self.swap_times, self.swap_start_step)
