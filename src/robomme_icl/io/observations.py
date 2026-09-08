"""只读取和复制观测，不调用任务判定或改变物体状态。"""

from __future__ import annotations

import numpy as np

from ..validation.assets import array_copy, pose_value
from .identities import scene_names


def scalar(value):
    if hasattr(value, "item"):
        return value.item()
    return value


def copy_tree(value):
    if isinstance(value, dict):
        return {key: copy_tree(child) for key, child in value.items()}
    if isinstance(value, list):
        return [copy_tree(child) for child in value]
    if isinstance(value, tuple):
        return tuple(copy_tree(child) for child in value)
    if isinstance(value, np.ndarray) or hasattr(value, "detach"):
        return array_copy(value)
    return value


def native_parameters(base):
    """保存原版实际解析结果，不从目标列表反推计数或颜色。"""
    values = {}
    for field in (
        "dynamic",
        "num_repeats",
        "swap_times",
        "pick_times",
        "cube_half_size",
        "red_cubes_target_number",
        "blue_cubes_target_number",
        "green_cubes_target_number",
        "red_cubes_spawn_number",
        "blue_cubes_spawn_number",
        "green_cubes_spawn_number",
        "binfill_language_sequence",
        "color_names",
        "selected_bin_indices",
        "swing_directions",
    ):
        if hasattr(base, field):
            values[field] = copy_tree(getattr(base, field))
    for field in ("selected_buttons", "selected_bins"):
        if hasattr(base, field):
            values[field] = [actor.name for actor in getattr(base, field)]
    return values


def state_snapshot(base):
    actors = {}
    names = scene_names(base)
    for raw_name, actor in sorted(base.scene.actors.items()):
        name = names[raw_name]
        bodies = actor._bodies
        body = bodies[0]
        actors[name] = {"pose": pose_value(actor.pose), "visibility": []}
        for field in ("linear_velocity", "angular_velocity"):
            if hasattr(body, field):
                actors[name][field] = array_copy(getattr(body, field))
        for obj in actor._objs:
            for component in obj.components:
                if hasattr(component, "visibility"):
                    actors[name]["visibility"].append(float(component.visibility))
    articulations = {}
    for name, actor in sorted(base.scene.articulations.items()):
        articulations[name] = {
            "pose": pose_value(actor.pose),
            "qpos": array_copy(actor.get_qpos()),
            "qvel": array_copy(actor.get_qvel()),
        }
    counters = {}
    for name in (
        "timestep",
        "current_task_index",
        "current_task_name",
        "current_task_name_online",
        "current_task_demonstration",
        "current_task_specialflag",
        "current_task_failure",
        "red_cubes_in_bin",
        "blue_cubes_in_bin",
        "green_cubes_in_bin",
        "static_flag",
        "start_step",
    ):
        if hasattr(base, name):
            counters[name] = scalar(getattr(base, name))
    if hasattr(base, "swap_schedule"):
        counters["swap_schedule"] = [
            [
                getattr(first, "name", None),
                getattr(second, "name", None),
                int(start),
                int(end),
            ]
            for first, second, start, end in base.swap_schedule
        ]
    return {"actors": actors, "articulations": articulations, "task_state": counters}


def normalized_observation(raw, base):
    sensors = raw["sensor_data"]
    return {
        "base_rgb": array_copy(sensors["base_camera"]["rgb"])[0],
        "wrist_rgb": array_copy(sensors["hand_camera"]["rgb"])[0],
        "qpos": array_copy(base.agent.robot.get_qpos())[0],
        "qvel": array_copy(base.agent.robot.get_qvel())[0],
        "native_state": state_snapshot(base),
    }


def normalized_info(native_info, base):
    demonstration = bool(getattr(base, "current_task_demonstration", False))
    subgoal = getattr(base, "current_task_name", "Unknown")
    return {
        "success": bool(
            scalar(native_info.get("success", getattr(base, "successflag", False)))
        ),
        "fail": bool(
            scalar(native_info.get("fail", getattr(base, "failureflag", False)))
        ),
        "step": int(base.elapsed_steps.item()),
        "phase": "demonstration" if demonstration else "evaluation",
        "is_demonstration": demonstration,
        "subgoal_index": int(getattr(base, "current_task_index", 0)),
        "subgoal": subgoal,
        "subgoal_segment": getattr(base, "current_subgoal_segment", None),
        "choice_label": getattr(base, "current_choice_label", None),
        "deliver_frame": subgoal != "NO RECORD",
        "specialflag": getattr(base, "current_task_specialflag", None),
    }


def task_inventory(base):
    def names(value):
        if isinstance(value, (list, tuple)):
            return [names(child) for child in value]
        return getattr(value, "name", None)

    return [
        {
            "name": entry["name"],
            "subgoal_segment": entry.get("subgoal_segment"),
            "choice_label": entry.get("choice_label"),
            "demonstration": entry["demonstration"],
            "specialflag": entry.get("specialflag"),
            "segment": names(entry.get("segment")),
            "has_failure_func": entry.get("failure_func") is not None,
        }
        for entry in base.task_list
    ]
