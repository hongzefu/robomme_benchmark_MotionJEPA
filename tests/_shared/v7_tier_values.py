"""V7 定值表（0928 方案 §3.2.2）的测试侧副本与「从 decision 块读出各档定值」的读取函数。

测试用，两处共用：

* ``tests/lightweight/test_v7_tier_values.py``：源码类常量／``native_blocks`` 在进程内读出的值等于本表；
* ``tests/lightweight/test_sampling_config_split.py::test_v7_snapshot_matches_source``：
  ``train_split_config.py extract --release newtask-v7`` 导出的快照读出的值等于本表。

每个维度都是「每档一个定数」：读取函数遇到区间两端不等就直接报错（V7 口径：无区间）。
StopCube／InsertPeg／MoveCube 只有 xhard4、数值不动，不在本表内。
"""

from __future__ import annotations

from typing import Any

TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")

#: 13 个梯度任务 × 各维度 × 四档（xhard1..4）
V7_TIER_VALUES: dict[str, dict[str, tuple[int, ...]]] = {
    "PickXtimes": {"number": (7, 10, 12, 15), "distractors": (1, 2, 3, 4)},
    "SwingXtimes": {"number": (5, 7, 9, 11), "distractors": (1, 2, 3, 4)},
    "VideoUnmask": {"pick": (2, 3, 3, 3), "distractor_count": (0, 4, 8, 12), "distractor_cubes": (0, 2, 4, 6)},
    "ButtonUnmask": {"pick": (2, 3, 3, 3), "distractor_count": (0, 4, 8, 12), "distractor_cubes": (0, 2, 4, 6)},
    "VideoUnmaskSwap": {"swap": (5, 7, 9, 11), "pick": (2, 3, 3, 3), "outer": (2, 4, 6, 8), "outer_cubes": (1, 2, 3, 4)},
    "ButtonUnmaskSwap": {"swap": (3, 5, 7, 9), "pick": (2, 3, 3, 3), "outer": (2, 4, 6, 8), "outer_cubes": (1, 2, 3, 4)},
    "VideoRepick": {"cube": (4, 5, 6, 7), "swap": (4, 6, 8, 10), "repick": (2, 3, 4, 5)},
    # 用户 2026-09-29 定「直接改 12/15/18/21」（不是方案附表的 24）
    "PatternLock": {"length": (12, 15, 18, 21)},
    "RouteStick": {"length": (10, 13, 16, 19)},
    # 以下四个任务 V7 数值与 v6 相同（方案 §3.2.2「不变」一条）
    "BinFill": {"spawn": (12, 12, 12, 12), "put_in": (6, 7, 8, 9)},
    "PickHighlight": {"spawn": (7, 8, 9, 10), "pick": (4, 5, 6, 7)},
    "VideoPlaceButton": {"demo_objects": (1, 1, 2, 2), "extra_before": (0, 1, 1, 1), "extra_after": (1, 1, 0, 1),
                         "targets": (4, 4, 5, 5)},
    "VideoPlaceOrder": {"visits_total": (5, 6, 7, 8)},
}


class NotFixedValue(AssertionError):
    """某维度在某档仍是区间（两端不等）。"""


def _point(lo: Any, hi: Any, label: str) -> int:
    if int(lo) != int(hi):
        raise NotFixedValue(f"{label} 仍是区间 [{lo}, {hi}]，V7 要求每档一个定数")
    return int(lo)


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
    if task == "PatternLock":
        return {"length": _point(*decision["path_length_range"][tier], f"{lab}.path_length_range")}
    if task == "RouteStick":
        return {"length": _point(*decision[tier]["segment_count_range"], f"{lab}.segment_count_range")}
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
    raise KeyError(f"V7 定值表不含任务 {task}")


def summarize(task: str, decision: dict) -> dict[str, tuple[int, ...]]:
    """把一个任务的 decision 块读成与 :data:`V7_TIER_VALUES` 同形的 ``{维度: (xhard1..4)}``。"""
    per_tier = [_tier_values(task, decision, tier) for tier in TIERS]
    return {dim: tuple(values[dim] for values in per_tier) for dim in per_tier[0]}
