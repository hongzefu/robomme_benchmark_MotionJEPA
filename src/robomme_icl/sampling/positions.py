"""按每档名额分层抽位置，候选重试只在原层内移动。"""

import math

from .random import _Stream


def sample_interval(slot, candidate_index, field, bounds, strata=None):
    count = slot["position_count"]
    layers = list(range(count))
    seed = slot["position_config"]["compiler_seed"]
    group = slot["position_group"]
    if (
        slot["topology"] == "field"
        and count >= 4
        and field.startswith("cube_")
        and field.endswith((".x", ".y"))
    ):
        number = int(field.split(".")[0].removeprefix("cube_"))
        axis = field[-1]
        _Stream(seed, group, f"field.{axis}", "layers").shuffle(layers)
        offset = number if axis == "x" else 3 * (number % count) + number // count
        layer = (layers[slot["position_rank"]] + offset) % count
    else:
        _Stream(seed, group, field, "layers").shuffle(layers)
        layer = layers[slot["position_rank"]]
    low, high = bounds
    width = (high - low) / count
    if strata is not None:
        strata[field] = {
            "index": layer,
            "count": count,
            "support": list(bounds),
            "bounds": [low + layer * width, low + (layer + 1) * width],
        }
    offset = _Stream(seed, slot["slot_id"], candidate_index, field, "offset").uniform()
    return low + (layer + offset) * width


def sample_placements(slot, candidate_index):
    task = slot["task_kind"]
    config = slot["position_config"]
    parameters = slot["parameters"]
    placements = {}
    strata = {}
    layout = {
        "sampling": "stratified",
        "rank": slot["position_rank"],
        "count": slot["position_count"],
        "safety_clearance": config["safety_clearance"],
        "table_bounds": config["table_bounds"],
        "topology": slot["topology"],
        "position_group": slot["position_group"],
        "strata": strata,
        "coordinate_mode": "native_support_fraction",
        "supports": {},
    }

    def point(name, bounds, angles=None):
        yaw = sample_interval(
            slot,
            candidate_index,
            name + ".yaw",
            angles or bounds.get("yaw_degrees", [0.0, 0.0]),
            strata,
        )
        layout["supports"][name] = {axis: list(bounds[axis]) for axis in ("x", "y")}
        return {
            "x_fraction": sample_interval(
                slot, candidate_index, name + ".x", [0.0, 1.0], strata
            ),
            "y_fraction": sample_interval(
                slot, candidate_index, name + ".y", [0.0, 1.0], strata
            ),
            "yaw_degrees": yaw,
        }

    if task == "RouteStick":
        route = config[task]
        layout.update(
            center=route["center"],
            spacing=route["spacing"],
            yaw_degrees=sample_interval(
                slot, candidate_index, "route.yaw", route["yaw_degrees"], strata
            ),
        )
        return placements, layout
    if task in ("BinFill", "VideoRepick"):
        placements["button"] = [point("button", config[task]["button"])]
    if task == "BinFill":
        placements["board"] = [point("board", config[task]["board"])]
        placements["cubes"] = [
            point(f"cube_{i}", config[task]["cubes"])
            for i in range(parameters["spawn_count"])
        ]
    elif task == "VideoRepick" and slot["difficulty"] == "hard":
        placements["cubes"] = [
            point(f"cube_{i}", config[task]["hard_cubes"])
            for i in range(parameters["spawn_count"])
        ]
    else:
        video = config["video_layouts"]
        count = parameters.get("container_count", parameters.get("spawn_count"))
        topology = slot["topology"]
        angle = sample_interval(
            slot, candidate_index, "layout.yaw", video["yaw_degrees"], strata
        )
        theta = math.radians(angle)
        anchors = [
            (
                x * math.cos(theta) - y * math.sin(theta),
                x * math.sin(theta) + y * math.cos(theta),
            )
            for x, y in video[topology]
        ]
        half_window = video["window_half_size"]
        kind = "containers" if task == "VideoUnmaskSwap" else "cubes"
        angle_field = (
            "container_yaw_degrees" if kind == "containers" else "cube_yaw_degrees"
        )
        placements[kind] = []
        for index, (x, y) in enumerate(anchors):
            bounds = {
                "x": [x - half_window, x + half_window],
                "y": [y - half_window, y + half_window],
            }
            sampled = point(f"{kind}_{index}", bounds, video[angle_field])
            placements[kind].append(sampled)
        layout.update(
            topology=topology,
            anchors=anchors,
            yaw_degrees=angle,
            window_half_size=half_window,
        )
    return placements, layout
