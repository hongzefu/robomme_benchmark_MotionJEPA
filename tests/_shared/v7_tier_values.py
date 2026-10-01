"""v8 档位取值表（1001 方案 §1 表 1；沿用 V7 定值表的文件名与结构）的测试侧副本与「从 decision 块读出各档取值」的读取函数。

测试用，两处共用：

* ``tests/lightweight/test_v7_tier_values.py``：源码类常量／``native_blocks`` 在进程内读出的值等于本表；
* ``tests/lightweight/test_sampling_config_split.py::test_v7_snapshot_matches_source``：
  ``train_split_config.py extract --release newtask-v7`` 导出的快照读出的值等于本表。

除 RouteStick、PatternLock 外，每个维度都是「每档一个定数」：读取函数遇到区间两端不等就直接报错。
v8：RouteStick、PatternLock 的 xhard1～3 改为区间（读出 ``(lo, hi)``，两端相等时仍读成定数）；
SwingXtimes、StopCube 支持 xhard1～5 五档（见 :data:`TASK_TIERS`），其余任务四档；StopCube 入表。
InsertPeg／MoveCube 只有 xhard4、数值不动，不在本表内。
"""

from __future__ import annotations

from typing import Any

#: 新值族的四个公共档（与 ``difficulty.NEWVALUE_DIFFICULTIES`` 一致，v8 不扩）
TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")
#: v8 第五档；只有 SwingXtimes、StopCube 支持
XHARD5 = "xhard5"
#: 只支持五档的任务
FIVE_TIER_TASKS = ("SwingXtimes", "StopCube")
#: 取值按区间读的任务（xhard1～3 为 [lo, hi]）
RANGE_TASKS = ("RouteStick", "PatternLock")

#: 14 个任务 × 各维度 × 该任务支持的各档（顺序同 :func:`tiers_for`）
V7_TIER_VALUES: dict[str, dict[str, tuple]] = {
    # v8：抓放次数 6/7/8/9（xhard4=9 不交付，只保四键结构）
    "PickXtimes": {"number": (6, 7, 8, 9), "distractors": (1, 2, 3, 4)},
    # v8：摆动轮数 4/5/6/7/8，xhard5 干扰 4（只有 4 色）
    "SwingXtimes": {"number": (4, 5, 6, 7, 8), "distractors": (1, 2, 3, 4, 4)},
    # v8：停止序号定值 6/7/8/9/10，速度最快档 60
    "StopCube": {"stop_time": (6, 7, 8, 9, 10), "move_interval": (60, 60, 60, 60, 60)},
    # v8：xhard1 干扰 0 → 4、含 cube 0 → 2
    "VideoUnmask": {"pick": (2, 3, 3, 3), "distractor_count": (4, 4, 8, 12), "distractor_cubes": (2, 2, 4, 6)},
    "ButtonUnmask": {"pick": (2, 3, 3, 3), "distractor_count": (4, 4, 8, 12), "distractor_cubes": (2, 2, 4, 6)},
    "VideoUnmaskSwap": {"swap": (5, 7, 9, 11), "pick": (2, 3, 3, 3), "outer": (2, 4, 6, 8), "outer_cubes": (1, 2, 3, 4)},
    "ButtonUnmaskSwap": {"swap": (3, 5, 7, 9), "pick": (2, 3, 3, 3), "outer": (2, 4, 6, 8), "outer_cubes": (1, 2, 3, 4)},
    "VideoRepick": {"cube": (4, 5, 6, 7), "swap": (4, 6, 8, 10), "repick": (2, 3, 4, 5)},
    # v8：xhard1～3 改区间，xhard4 仍定值 21／19（不交付）
    "PatternLock": {"length": ((9, 12), (13, 15), (16, 18), 21)},
    "RouteStick": {"length": ((8, 10), (11, 13), (14, 16), 19)},
    # 以下四个任务 V7 数值与 v6 相同（方案 §3.2.2「不变」一条）
    "BinFill": {"spawn": (12, 12, 12, 12), "put_in": (6, 7, 8, 9)},
    "PickHighlight": {"spawn": (7, 8, 9, 10), "pick": (4, 5, 6, 7)},
    "VideoPlaceButton": {"demo_objects": (1, 1, 2, 2), "extra_before": (0, 1, 1, 1), "extra_after": (1, 1, 0, 1),
                         "targets": (4, 4, 5, 5)},
    "VideoPlaceOrder": {"visits_total": (5, 6, 7, 8)},
}


#: 各任务支持的新值档（SwingXtimes、StopCube 五档，其余四档）
TASK_TIERS: dict[str, tuple[str, ...]] = {
    task: (*TIERS, XHARD5) if task in FIVE_TIER_TASKS else TIERS for task in V7_TIER_VALUES
}


def tiers_for(task: str) -> tuple[str, ...]:
    """任务支持的新值档。"""
    return TASK_TIERS[task]


class NotFixedValue(AssertionError):
    """某维度在某档仍是区间（两端不等），而该任务要求定数。"""


def _point(lo: Any, hi: Any, label: str, *, allow_range: bool = False):
    """两端相等读成定数；``allow_range``（RouteStick／PatternLock）时两端不等读成 ``(lo, hi)``，否则报错。"""
    lo, hi = int(lo), int(hi)
    if lo == hi:
        return lo
    if allow_range and lo < hi:
        return (lo, hi)
    raise NotFixedValue(f"{label} 仍是区间 [{lo}, {hi}]，该任务要求每档一个定数")


def _tier_values(task: str, decision: dict, tier: str) -> dict[str, int]:
    """按任务读 ``decision``（header 里的 decision 块）中本档各维度的定值。"""
    lab = f"{task}@{tier}"
    if task in ("PickXtimes", "SwingXtimes"):
        return {"number": _point(*decision["number_range"][tier], f"{lab}.number_range"),
                "distractors": len(decision[tier]["distractor"]["colors"])}
    if task in ("VideoUnmask", "ButtonUnmask"):
        dist = decision[tier]["distractor"]
        return {"pick": int(decision["pick_count"][tier]), "distractor_count": int(dist["count"]),
                "distractor_cubes": _point(*dist["cube_count_range"], f"{lab}.cube_count_range")}
    if task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        dist = decision[tier]["distractor"]
        return {"swap": _point(*decision["swap_count_range"][tier], f"{lab}.swap_count_range"),
                "pick": _point(*decision["pick_count_range"][tier], f"{lab}.pick_count_range"),
                "outer": int(dist["count"]),
                "outer_cubes": _point(*dist["cube_count_range"], f"{lab}.cube_count_range")}
    if task == "VideoRepick":
        swap, rep = decision["swap"][tier], decision["num_repeats_range"][tier]
        return {"cube": int(decision[tier]["layout"]["cube_count"]),
                "swap": _point(swap["swap_min"], swap["swap_max"], f"{lab}.swap"),
                # randint(low, high_exclusive) 只剩一个点 ⇔ high_exclusive == low + 1
                "repick": _point(rep["low"], int(rep["high_exclusive"]) - 1, f"{lab}.num_repeats_range")}
    if task == "StopCube":
        sub = decision[tier]
        moves = list(sub["move_interval_choices"])
        if len(moves) != 1:
            raise NotFixedValue(f"{lab}.move_interval_choices 不是单值: {moves}")
        stop = sub["stop_time_range"]
        # randint(low, high_exclusive) 只剩一个点 ⇔ high_exclusive == low + 1
        return {"stop_time": _point(stop["low"], int(stop["high_exclusive"]) - 1, f"{lab}.stop_time_range"),
                "move_interval": int(moves[0])}
    if task == "PatternLock":
        return {"length": _point(*decision["path_length_range"][tier], f"{lab}.path_length_range", allow_range=True)}
    if task == "RouteStick":
        return {"length": _point(*decision[tier]["segment_count_range"], f"{lab}.segment_count_range",
                                 allow_range=True)}
    if task == "BinFill":
        cfg = decision["configs"][tier]
        return {"spawn": _point(*cfg["spawn_cubes"], f"{lab}.spawn_cubes"),
                "put_in": _point(*cfg["put_in_numbers"], f"{lab}.put_in_numbers")}
    if task == "PickHighlight":
        return {"spawn": _point(*decision["spawn_count"][tier], f"{lab}.spawn_count"),
                "pick": _point(*decision["highlight_count"][tier], f"{lab}.highlight_count")}
    if task == "VideoPlaceButton":
        sub = decision[tier]
        return {"demo_objects": int(sub["demo_object_count"]), "extra_before": int(sub["extra_place_before"]),
                "extra_after": int(sub["extra_place_after"]), "targets": int(decision["targets"][tier])}
    if task == "VideoPlaceOrder":
        return {"visits_total": sum(int(v) for v in decision[tier]["visit_counts"])}
    raise KeyError(f"定值表不含任务 {task}")


def summarize(task: str, decision: dict) -> dict[str, tuple]:
    """把一个任务的 decision 块读成与 :data:`V7_TIER_VALUES` 同形的 ``{维度: (该任务各档)}``。"""
    per_tier = [_tier_values(task, decision, tier) for tier in tiers_for(task)]
    return {dim: tuple(values[dim] for values in per_tier) for dim in per_tier[0]}
