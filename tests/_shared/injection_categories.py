"""每个字段的**完整合法类别集合**，来自计划第二节的约定表，不是来自实际出现的值。

⚠ 计划第 4.1 节的陷阱：``check`` 必须按完整合法类别**补零**再算计数差。否则
100 条全为 ``True`` 时 ``dynamic`` 只有一个类别、计数差也是 0，会被误判通过
（在途实现曾有此反例）。因此本模块与生成器分开维护：``plan`` 负责按配额铺，
``check`` 负责按这张表补零重算，两边都错才会漏。

字段分两类：

* ``independent``：能独立分配的离散量，判据是**计数差不超过 1**；
* ``coupled``：受几何或动作耦合的量，只报实际频数与未覆盖组合，不声称严格均匀。
"""

from __future__ import annotations

import itertools
from typing import Any

from .injection_specs import (
    INITIALIZE_COLOR_DEFS,
    REPICK_COLOR_ORDER,
    SPAWN_COLOR_ORDER,
    UNMASK_COLOR_ORDER,
)


def _int_range(pair: Any) -> list[int]:
    lo, hi = (int(v) for v in pair)
    return list(range(lo, hi + 1))


def legal_categories(task: str, difficulty: str, sampling: dict[str, Any]) -> dict[str, dict[str, list[Any]]]:
    """返回 ``{"independent": {...}, "coupled": {...}}``，值是完整合法类别列表。"""
    parameters = sampling["parameters"][task]
    config = parameters["configs"][difficulty]

    if task == "BinFill":
        num_colors = int(config["color"])
        combos = [list(c) for c in itertools.combinations(SPAWN_COLOR_ORDER, num_colors)]
        color_counts = sorted(
            {min(max(1, min(3, k)), max(1, num_colors)) for k in _int_range(config["put_in_color"])}
        )
        pools: list[list[str]] = []
        for combo in combos:
            for k in color_counts:
                pools.extend([list(p) for p in itertools.combinations(combo, k)])
        unique_pools = [list(p) for p in dict.fromkeys(tuple(p) for p in pools)]
        return {
            "independent": {
                "dynamic": [True, False],
                "colors_present": combos,
                "initialize_color_order": [list(p) for p in itertools.permutations(INITIALIZE_COLOR_DEFS)],
                "spawn_total": _int_range(config["spawn_cubes"]),
                "put_in_total": _int_range(config["put_in_numbers"]),
            },
            "coupled": {
                "target_pool": unique_pools,
                "spawn_count": [],  # 逐色计数，只报频数
                "target_count": [],
            },
        }

    if task == "RouteStick":
        walk = parameters["walk"]
        nodes = [int(v) for v in walk["node_indices"]]
        return {
            "independent": {
                "L": _int_range(config["length"]),
                "start_node": nodes,
                "direction": [walk["direction"]["less_than"], walk["direction"]["otherwise"]],
            },
            "coupled": {
                # 线性邻接下的全部合法有向边
                "edge": [[nodes[i], nodes[j]] for i in range(len(nodes)) for j in (i - 1, i + 1) if 0 <= j < len(nodes)],
            },
        }

    if task == "VideoUnmaskSwap":
        n_bins = int(config["bin"])
        bin_names = [f"bin_{i}" for i in range(n_bins)]
        return {
            "independent": {
                "n_swaps": _int_range([config["swap_min"], config["swap_max"]]),
                "n_picks": _int_range([config["pick_min"], config["pick_max"]]),
                "layout_type": ["region3_tri", "region3_line"] if n_bins == 3 else ["region4"],
                "selected": [list(p) for p in itertools.permutations(range(3))],
                "color_order": [list(p) for p in itertools.permutations(UNMASK_COLOR_ORDER)],
            },
            "coupled": {
                "swap_pair": [[a, b] for a in bin_names for b in bin_names if a != b],
                "pick_order": [],
                "hidden": [],
            },
        }

    if task == "VideoRepick":
        n_cubes = int(config["cube"])
        names = [f"bin_{i}" for i in range(n_cubes)]
        repeats = parameters["num_repeats"]
        return {
            "independent": {
                "n_swaps": _int_range([config["swap_min"], config["swap_max"]]),
                "num_repeats": list(range(int(repeats["low"]), int(repeats["high_exclusive"]))),
                "layout_type": ["region3_tri", "region3_line"],
                "color": list(REPICK_COLOR_ORDER),
                "target": names,
            },
            "coupled": {"swap_pair": [[a, b] for a in names for b in names if a != b]},
        }

    raise ValueError(f"未知任务 {task}")


def observed_values(task: str, record: dict[str, Any]) -> dict[str, list[Any]]:
    """把一条规格摊成 ``{字段: [该条贡献的取值...]}``，供计数。

    一条 episode 对同一字段可能贡献多个取值（例如一条路线有 L 段方向、多次交换有
    多个对象对），因此值一律是列表。
    """
    layout = record.get("layout", {})
    objects = record.get("objects", {})
    actions = record.get("actions", {})

    if task == "BinFill":
        return {
            "dynamic": [layout["dynamic"]],
            "colors_present": [list(objects["colors_present"])],
            "initialize_color_order": [list(objects["initialize_color_order"])],
            "spawn_total": [objects["spawn_total"]],
            "put_in_total": [objects["put_in_total"]],
            "target_pool": [list(objects["target_pool"])],
        }
    if task == "RouteStick":
        nodes = actions["nodes"]
        return {
            "L": [objects["L"]],
            "start_node": [nodes[0]],
            "direction": list(actions["directions"]),
            "edge": [[nodes[i], nodes[i + 1]] for i in range(len(nodes) - 1)],
        }
    if task == "VideoUnmaskSwap":
        return {
            "n_swaps": [objects["n_swaps"]],
            "n_picks": [objects["n_picks"]],
            "layout_type": [layout["type"]],
            "selected": [list(objects["selected"])],
            "color_order": [list(objects["color_order"])],
            "swap_pair": [[item["initiator"], item["partner"]] for item in actions["swap_pairs"]],
        }
    if task == "VideoRepick":
        return {
            "n_swaps": [objects["n_swaps"]],
            "num_repeats": [objects["num_repeats"]],
            "layout_type": [layout["type"]],
            "color": [objects["color"]],
            "target": [objects["target"]],
            "swap_pair": [[item["initiator"], item["partner"]] for item in actions["swap_pairs"]],
        }
    raise ValueError(f"未知任务 {task}")
