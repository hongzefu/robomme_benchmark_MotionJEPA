"""把任务名额与布局输入编译成版本2清单，不生成任务行为。"""

from ..specs import COMPILER_VERSION, NATIVE_REFERENCE, EpisodeSpec, content_hash
from .positions import sample_placements


def candidate_for_slot(slot, candidate_index):
    if type(candidate_index) is not int or not 0 <= candidate_index < slot["max_candidates"]:
        raise ValueError("candidate_index 超出固定候选预算")
    placements, layout = sample_placements(slot, candidate_index)
    task = slot["task_kind"]
    return EpisodeSpec.from_dict({
        "schema_version": 2,
        "task_kind": task,
        "seed": slot["seed"],
        "episode": slot["episode"],
        "difficulty": slot["difficulty"],
        "robot_kind": "panda_stick" if task == "RouteStick" else "panda_wristcam",
        "env_id": f"RoboMME-ICL/{task}-v0",
        "task_parameters": slot["parameters"],
        "placements": placements,
        "layout": layout,
        "provenance": {
            "native_reference": NATIVE_REFERENCE,
            "compiler_version": COMPILER_VERSION,
            "task_config_hash": content_hash(slot["task_config"]),
            "position_config_hash": content_hash(slot["position_config"]),
            "candidate_index": candidate_index,
            "slot_id": slot["slot_id"],
        },
    })
