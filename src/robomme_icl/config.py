"""只解析分布配置；素材、时间线和任务判定由原版定义。"""

from __future__ import annotations

import json
import math
from pathlib import Path


TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")
DIFFICULTIES = ("easy", "medium", "hard")
CONFIG_DIRECTORY = Path(__file__).parent / "configs"
TASK_FIELDS = {
    "BinFill": {"pick_count", "spawn_count", "target_color_count", "scene_color_count", "dynamic"},
    "RouteStick": {"walk_steps", "allow_backtracking"},
    "VideoUnmaskSwap": {"container_count", "pick_count", "swap_count"},
    "VideoRepick": {"spawn_count", "repeat_count", "swap_count"},
}


def validate_configs(task_config: dict, position_config: dict) -> None:
    if task_config.get("schema_version") != 1 or position_config.get("schema_version") != 2:
        raise ValueError("任务配置须为版本1，位置配置须为不含几何／时序覆盖的版本2")
    expected_task = {"schema_version", "compiler_seed", "episode_seed_start", "task_order", "episodes_by_difficulty", "tasks"}
    expected_position = {"schema_version", "compiler_seed", "max_candidates", "sampling", "safety_clearance", "table_bounds", "BinFill", "RouteStick", "video_layouts", "VideoRepick"}
    if set(task_config) != expected_task or set(position_config) != expected_position:
        raise ValueError("配置字段不匹配；不得添加原版几何或时序覆盖")
    if task_config["task_order"] != list(TASKS) or set(task_config["tasks"]) != set(TASKS):
        raise ValueError("task_order 必须按固定顺序完整列出四任务")
    quotas = task_config["episodes_by_difficulty"]
    if set(quotas) != set(DIFFICULTIES):
        raise ValueError("必须指定三个难度的条数")
    for value in [*quotas.values(), task_config["compiler_seed"], task_config["episode_seed_start"], position_config["compiler_seed"]]:
        if type(value) is not int or value < 0:
            raise ValueError("条数和随机种子必须为非负整数")
    if sum(quotas.values()) == 0:
        raise ValueError("总配额不得为零")
    if position_config["sampling"] != "stratified":
        raise ValueError("只支持 stratified 分层抽样")
    budget = position_config["max_candidates"]
    if type(budget) is not int or not 1 <= budget <= 1024:
        raise ValueError("候选预算必须为1至1024")
    clearance = position_config["safety_clearance"]
    if type(clearance) not in (float, int) or not math.isfinite(clearance) or clearance < .005:
        raise ValueError("候选筛选间距不得小于0.005米")
    for task in TASKS:
        if set(task_config["tasks"][task]) != set(DIFFICULTIES):
            raise ValueError(f"{task} 必须指定三个难度")
        for difficulty, parameters in task_config["tasks"][task].items():
            if set(parameters) != TASK_FIELDS[task]:
                raise ValueError(f"{task}.{difficulty} 参数字段不匹配")
            for key, values in parameters.items():
                if not isinstance(values, list) or not values or len(set(values)) != len(values):
                    raise ValueError(f"{task}.{difficulty}.{key} 必须为不重复的非空列表")
                for value in values:
                    if key in ("dynamic", "allow_backtracking"):
                        valid = type(value) is bool
                    else:
                        valid = type(value) is int and value >= (0 if key == "swap_count" else 1)
                    if not valid:
                        raise ValueError(f"{task}.{difficulty}.{key} 候选值非法")
            if task == "BinFill" and max(parameters["scene_color_count"] + parameters["target_color_count"]) > 3:
                raise ValueError("BinFill 仅有三个原色")
            if task == "VideoUnmaskSwap" and (not set(parameters["container_count"]) <= {3, 4} or max(parameters["pick_count"]) > 2):
                raise ValueError("原版仅支持3/4容器和1/2次抓取")
            if task in ("VideoUnmaskSwap", "VideoRepick") and max(parameters["swap_count"]) > 3:
                raise ValueError("原版最多支持三次交换")
            if task == "VideoUnmaskSwap" and min(parameters["swap_count"]) == 0:
                raise ValueError("原版 VideoUnmaskSwap 至少一次交换")
            if task == "VideoRepick":
                if parameters["spawn_count"] != ([15] if difficulty == "hard" else [3]):
                    raise ValueError("VideoRepick 原版 easy/medium 为3方块，hard为15方块")
                if difficulty == "hard" and parameters["swap_count"] != [0]:
                    raise ValueError("VideoRepick hard 不交换")
    def check_ranges(value):
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            if key in ("x", "y", "yaw_degrees", "container_yaw_degrees", "cube_yaw_degrees"):
                if not isinstance(child, list) or len(child) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in child) or child[0] > child[1]:
                    raise ValueError(f"{key} 必须为有序有限区间")
            else:
                check_ranges(child)
    check_ranges(position_config)


def load_configs(task_path=None, position_path=None) -> tuple[dict, dict]:
    task_path = Path(task_path) if task_path else CONFIG_DIRECTORY / "task_distribution.json"
    position_path = Path(position_path) if position_path else CONFIG_DIRECTORY / "position_distribution.json"
    task_config = json.loads(task_path.read_text(encoding="utf-8"))
    position_config = json.loads(position_path.read_text(encoding="utf-8"))
    validate_configs(task_config, position_config)
    return task_config, position_config
