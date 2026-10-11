"""VideoUnmask 的 xhard 派生子类（S2）。

旋钮取值见 ``robomme_xhard.configs.TIER_CONFIGS["VideoUnmask"]``，实例上读 ``self.xhard_knobs``。

xhard14（pick_count=3）：父类 ``_load_scene`` 按 ``configs[...]["pick"] > 1`` 生成原两抓
（抓 bin_0 → 放下 → 抓 bin_1）；子类在其后追加“放下 bin_1 → 抓 bin_2”，即第三抓
（R17 批准的“原本执行不到的动作”）。不新增任何容器或方块（R15），不加 V9 干扰容器（RL10）。

语言契约：``self.color_names[0..2]`` 依次是三次抓取所对应容器下的方块颜色
（父类把颜色 ``color_names[i]`` 的方块放在 ``bin_i`` 下，三抓依次抓 bin_0、bin_1、bin_2）。
"""

from mani_skill.utils.registration import register_env

from robomme.robomme_env.VideoUnmask import VideoUnmask
from robomme.robomme_env.utils import task4recovery
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
from robomme.robomme_env.utils.subgoal_evaluate_func import (
    is_any_bin_pickup,
    is_bin_pickup,
    is_bin_putdown,
)
from robomme.robomme_env.utils.subgoal_planner_func import (
    solve_pickup_bin,
    solve_putdown_whenhold,
)

from ..base import XHardMixin


def reject_failure_recovery(env_cls_name: str, kwargs: dict) -> None:
    """派生档改写了任务清单，父类的失败注入随机流无法按新清单复现：开启即响亮失败（R11 母 seed 已避开）。"""
    if kwargs.get("robomme_failure_recovery"):
        raise ValueError(
            f"{env_cls_name} 不支持 robomme_failure_recovery=True（xhard 改写了任务清单，"
            "父类失败注入无法按新清单复现；计划 R11 要求选母 seed 时避开 FailRecover）"
        )


def extra_pick_tasks(env, pick_count: int) -> list[dict]:
    """生成第 3..pick_count 抓的任务项：每抓之前先放下上一个容器。

    每项写法照抄父类第二抓的 put down / pick up 两项，只把 bin_0/bin_1、color_names[1]
    换成本轮序号；actor 用默认参数绑定在闭包里（每项绑定自己的序号与 actor）。
    """
    bins = list(getattr(env, "spawned_bins", []))
    colors = list(getattr(env, "color_names", []))
    if len(bins) < pick_count or len(colors) < pick_count:
        raise SceneGenerationError(
            f"xhard 需要至少 {pick_count} 个藏方块的容器，实际容器 {len(bins)} 个、颜色 {len(colors)} 个"
        )
    tasks: list[dict] = []
    for j in range(2, pick_count):
        prev_bin = getattr(env, f"bin_{j - 1}")
        cur_bin = getattr(env, f"bin_{j}")
        color = env.color_names[j]
        tasks.append({
            "func": (lambda prev_bin=prev_bin: is_bin_putdown(env, obj=prev_bin)),
            "name": "put down the container",
            "subgoal_segment": "put down the container",
            "choice_label": "put down the container",
            "demonstration": False,
            "failure_func": (lambda prev_bin=prev_bin: is_any_bin_pickup(
                env, [b for b in env.spawned_bins if b != prev_bin])),
            "solve": lambda e, planner: solve_putdown_whenhold(e, planner),
        })
        tasks.append({
            "func": (lambda cur_bin=cur_bin: is_bin_pickup(env, obj=cur_bin)),
            "name": f"pick up the container that hides the {color} cube",
            "subgoal_segment": f"pick up the container at <> that hides the {color} cube",
            "choice_label": "pick up the container",
            "demonstration": False,
            "failure_func": (lambda cur_bin=cur_bin: is_any_bin_pickup(
                env, [b for b in env.spawned_bins if b != cur_bin])),
            "solve": (lambda e, planner, cur_bin=cur_bin: solve_pickup_bin(e, planner, obj=cur_bin)),
            "segment": cur_bin,
        })
    return tasks


def append_extra_picks(env) -> None:
    """在父类任务清单尾部追加第三抓并重算 recovery 索引；任一前提不符即响亮失败。"""
    pick_count = int(env.xhard_knobs["pick_count"])
    cfg_pick = env.configs[env.difficulty]["pick"]
    if cfg_pick != pick_count:
        raise SceneGenerationError(f"configs pick={cfg_pick} 与 knobs pick_count={pick_count} 不一致")
    # 父类在 pick>1 时只生成两抓：静态/按钮前缀之外应恰有 [抓 bin_0, 放下, 抓 bin_1]
    pick_names = [t["name"] for t in env.task_list if t.get("choice_label") == "pick up the container"]
    if len(pick_names) != 2:
        raise SceneGenerationError(f"父类任务清单应恰有两抓，实际 {pick_names}")
    env.task_list.extend(extra_pick_tasks(env, pick_count))
    env.recovery_pickup_indices, env.recovery_pickup_tasks = task4recovery(env.task_list)


@register_env("VideoUnmaskXHard")
class VideoUnmaskXHard(XHardMixin, VideoUnmask):
    robomme_base_id = "VideoUnmask"

    def __init__(self, *args, **kwargs):
        reject_failure_recovery(type(self).__name__, kwargs)
        super().__init__(*args, **kwargs)

    def _load_scene(self, options: dict):
        super()._load_scene(options)
        append_extra_picks(self)
