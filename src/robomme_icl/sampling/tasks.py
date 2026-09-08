"""先固定每档任务配额，再为位置采样提供独立名额。"""

from collections import Counter, defaultdict
import copy
import itertools

from ..config import TASKS, DIFFICULTIES, validate_configs
from .random import _Stream


def _legal_combinations(task, choices):
    keys = sorted(choices)
    result = []
    for values in itertools.product(*(choices[key] for key in keys)):
        row = dict(zip(keys, values))
        if task == "BinFill":
            if not row["pick_count"] <= row["spawn_count"]:
                continue
            if (
                row["scene_color_count"] < row["target_color_count"]
                or row["spawn_count"]
                < row["pick_count"]
                + row["scene_color_count"]
                - row["target_color_count"]
            ):
                continue
        if task == "VideoUnmaskSwap" and row["pick_count"] >= row["container_count"]:
            continue
        result.append(row)
    return result


def _quota_rows(task, choices, count, stream):
    """先完整轮转联合组合，余数按边际缺额选择且不重复组合。"""
    combinations = _legal_combinations(task, choices)
    base, remainder = divmod(count, len(combinations))
    rows = [copy.deepcopy(row) for row in combinations for _ in range(base)]
    pool = copy.deepcopy(combinations)
    stream.shuffle(pool)
    marginal = {key: Counter(row[key] for row in rows) for key in choices}
    # 动态两态的精确均衡具有优先级；其他维度使用相同的缺额代价。
    dynamic_targets = {}
    if "dynamic" in choices:
        values = list(choices["dynamic"])
        stream.shuffle(values)
        dynamic_targets = {
            v: count // len(values) + (i < count % len(values))
            for i, v in enumerate(values)
        }
    for _ in range(remainder):
        eligible = [
            row
            for row in pool
            if not dynamic_targets
            or marginal["dynamic"][row["dynamic"]] < dynamic_targets[row["dynamic"]]
        ]
        if not eligible:
            raise ValueError("动态配额与合法次数组合无法同时满足")
        row = min(
            eligible,
            key=lambda item: sum(
                (2 * marginal[key][item[key]] + 1) * len(choices[key])
                for key in choices
            ),
        )
        rows.append(copy.deepcopy(row))
        pool.remove(row)
        for key in choices:
            marginal[key][row[key]] += 1
    stream.shuffle(rows)
    return rows


def plan_slots(task_config, position_config, tasks=None, episodes_per_task=None):
    """任务过滤不改变其他任务的seed区段；拒绝候选不改变已选次数。"""
    validate_configs(task_config, position_config)
    selected = list(TASKS) if tasks is None else list(tasks)
    if (
        not selected
        or len(set(selected)) != len(selected)
        or not set(selected) <= set(TASKS)
    ):
        raise ValueError("tasks 必须为不重复的已知任务")
    quotas = dict(task_config["episodes_by_difficulty"])
    if episodes_per_task is not None:
        if type(episodes_per_task) is not int or episodes_per_task < 1:
            raise ValueError("episodes_per_task 必须为正整数")
        quotas = {
            name: episodes_per_task // 3 + (index < episodes_per_task % 3)
            for index, name in enumerate(DIFFICULTIES)
        }
    per_task = sum(quotas.values())
    if task_config["episode_seed_start"] + per_task * len(TASKS) > 2**31:
        raise ValueError("episode seed 区段超出32位范围")
    slots = []
    for task_index, task in enumerate(TASKS):
        if task not in selected:
            continue
        episode = 0
        for difficulty in DIFFICULTIES:
            count = quotas[difficulty]
            if count == 0:
                continue
            choices = task_config["tasks"][task][difficulty]
            stream = _Stream(task_config["compiler_seed"], task, difficulty, "quota")
            if not _legal_combinations(task, choices):
                raise ValueError(f"{task}.{difficulty} 没有合法参数组合")
            for rank, parameters in enumerate(
                _quota_rows(task, choices, count, stream)
            ):
                object_count = parameters.get(
                    "container_count", parameters.get("spawn_count", 0)
                )
                if task == "BinFill" or object_count == 15:
                    topology = "field"
                elif task == "RouteStick":
                    topology = "route"
                elif object_count == 4:
                    topology = "rectangle"
                else:
                    topologies = position_config["video_layouts"][
                        "three_object_topologies"
                    ]
                    topology = topologies[rank % len(topologies)]
                slots.append(
                    {
                        "slot_id": f"{task}/{difficulty}/{rank}",
                        "task_kind": task,
                        "difficulty": difficulty,
                        "episode": episode,
                        "seed": task_config["episode_seed_start"]
                        + task_index * per_task
                        + episode,
                        "parameters": parameters,
                        "topology": topology,
                        "position_rank": rank,
                        "position_count": count,
                        "max_candidates": position_config["max_candidates"],
                        "task_config": copy.deepcopy(task_config),
                        "position_config": copy.deepcopy(position_config),
                    }
                )
                episode += 1
    groups = defaultdict(list)
    for slot in slots:
        object_count = slot["parameters"].get(
            "spawn_count", slot["parameters"].get("container_count", 0)
        )
        group = (slot["task_kind"], slot["difficulty"], slot["topology"], object_count)
        groups[group].append(slot)
    for group, members in groups.items():
        for rank, slot in enumerate(members):
            slot["position_group"] = list(group)
            slot["position_rank"] = rank
            slot["position_count"] = len(members)
    return slots


def distribution_summary(slots):
    """只统计已固定输入，实际原版对象和事件由运行报告记录。"""
    counts = Counter((slot["task_kind"], slot["difficulty"]) for slot in slots)
    return {
        "episodes": len(slots),
        "by_task_difficulty": {
            f"{task}/{difficulty}": count
            for (task, difficulty), count in sorted(counts.items())
        },
    }
