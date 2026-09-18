"""每个字段的**完整合法类别集合**：从契约（``injection_contract_v*.json``）读取值域后**自行重新展开**，
不复用生成器的任何 series——``plan`` 负责按配额铺，``check`` 负责按这张表补零重算，两边都错才会漏。

⚠ 计划第 4.1 节的陷阱：``check`` 必须按完整合法类别**补零**再算计数差。否则
100 条全为 ``True`` 时 ``dynamic`` 只有一个类别、计数差也是 0，会被误判通过
（在途实现曾有此反例）。

字段分两类：

* ``independent``：能独立分配的离散量，判据是**计数差不超过 1**；
* ``coupled``：受几何或动作耦合的量，只报实际频数与未覆盖组合，不声称严格均匀。
"""

from __future__ import annotations

import itertools
from typing import Any

from .contract import Contract


def _lists(values: list[Any]) -> list[Any]:
    """契约 ``values`` 里的 tuple 转 list，与 ``observed_values`` 产出的形状一致。"""
    return [list(v) if isinstance(v, tuple) else v for v in values]


def legal_categories(task: str, difficulty: str, contract: Contract) -> dict[str, dict[str, list[Any]]]:
    """返回 ``{"independent": {...}, "coupled": {...}}``，值是完整合法类别列表。"""
    gc = contract.group(task, difficulty)

    if task == "BinFill":
        pool = tuple(gc.field("colors_present")["domain"]["pool"])
        combos = [[pool[i] for i in combo] for combo in gc.values("colors_present")]
        color_counts = [int(k) for k in gc.values("put_in_color")]
        pools: list[list[str]] = []
        for combo in combos:
            for k in color_counts:
                pools.extend([list(p) for p in itertools.combinations(combo, k)])
        unique_pools = [list(p) for p in dict.fromkeys(tuple(p) for p in pools)]
        return {
            "independent": {
                "dynamic": _lists(gc.values("dynamic")),
                "colors_present": combos,
                "initialize_color_order": _lists(gc.values("initialize_color_order")),
                "spawn_total": _lists(gc.values("spawn_total")),
                "put_in_total": _lists(gc.values("put_in_total")),
            },
            "coupled": {
                "target_pool": unique_pools,
                "spawn_count": [],  # 逐色计数，只报频数
                "target_count": [],
            },
        }

    if task == "RouteStick":
        nodes = [int(v) for v in gc.values("start_node")]
        return {
            "independent": {
                "L": _lists(gc.values("L")),
                "start_node": nodes,
                "direction": _lists(gc.values("direction")),
            },
            "coupled": {
                # 线性邻接下的全部合法有向边（自行按 ±1 展开，不读契约里的 universe）
                "edge": [[nodes[i], nodes[j]] for i in range(len(nodes)) for j in (i - 1, i + 1) if 0 <= j < len(nodes)],
            },
        }

    if task == "VideoUnmaskSwap":
        universe = gc.field("swap_initiators_third")["domain"]["universe"]
        bin_names = list(universe)
        layout = gc.values("layout_type") if gc.allocation("layout_type") == "quota" else [gc.constant("layout_type")]
        return {
            "independent": {
                "n_swaps": _lists(gc.values("n_swaps")),
                "n_picks": _lists(gc.values("n_picks")),
                "layout_type": _lists(layout),
                "selected": _lists(gc.values("selected")),
                "color_order": _lists(gc.values("color_order")),
            },
            "coupled": {
                "swap_pair": [[a, b] for a in bin_names for b in bin_names if a != b],
                "pick_order": [],
                "hidden": [],
            },
        }

    if task == "VideoRepick":
        names = [f"bin_{i}" for i in gc.values("target")]
        return {
            "independent": {
                "n_swaps": _lists(gc.values("n_swaps")),
                "num_repeats": _lists(gc.values("num_repeats")),
                "layout_type": _lists(gc.values("layout_type")),
                "color": _lists(gc.values("color")),
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
