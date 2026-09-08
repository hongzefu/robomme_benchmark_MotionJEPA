"""按每档名额分层抽位置，候选重试只在原层内移动。"""

import math

from .random import _Stream


def sample_interval(slot, candidate_index, field, bounds):
    count = slot["position_count"]
    layers = list(range(count))
    seed = slot["position_config"]["compiler_seed"]
    group = (slot["task_kind"], slot["difficulty"])
    _Stream(seed, group, field, "layers").shuffle(layers)
    layer = layers[slot["position_rank"]]
    low, high = bounds
    width = (high - low) / count
    offset = _Stream(seed, slot["slot_id"], candidate_index, field, "offset").uniform()
    return low + (layer + offset) * width


def sample_placements(slot, candidate_index):
    task = slot["task_kind"]
    config = slot["position_config"]
    parameters = slot["parameters"]
    placements = {}
    layout = {"sampling": "stratified", "rank": slot["position_rank"],
              "count": slot["position_count"], "safety_clearance": config["safety_clearance"],
              "table_bounds": config["table_bounds"]}

    def point(name, bounds, angles=None):
        yaw = sample_interval(slot, candidate_index, name + ".yaw", angles or bounds.get("yaw_degrees", [0., 0.]))
        return {"x": sample_interval(slot, candidate_index, name + ".x", bounds["x"]),
                "y": sample_interval(slot, candidate_index, name + ".y", bounds["y"]),
                "yaw_degrees": yaw}

    if task == "RouteStick":
        route = config[task]
        layout.update(center=route["center"], spacing=route["spacing"],
                      yaw_degrees=sample_interval(slot, candidate_index, "route.yaw", route["yaw_degrees"]))
        return placements, layout
    if task in ("BinFill", "VideoRepick"):
        placements["button"] = [point("button", config[task]["button"])]
    if task == "BinFill":
        placements["board"] = [point("board", config[task]["board"])]
        placements["cubes"] = [point(f"cube_{i}", config[task]["cubes"])
                                for i in range(parameters["spawn_count"])]
    elif task == "VideoRepick" and slot["difficulty"] == "hard":
        placements["cubes"] = [point(f"cube_{i}", config[task]["hard_cubes"])
                                for i in range(parameters["spawn_count"])]
    else:
        video = config["video_layouts"]
        count = parameters.get("container_count", parameters.get("spawn_count"))
        if count == 4:
            topology = "rectangle"
        else:
            topologies = video["three_object_topologies"]
            topology = topologies[slot["position_rank"] % len(topologies)]
        angle = sample_interval(slot, candidate_index, "layout.yaw", video["yaw_degrees"])
        theta = math.radians(angle)
        anchors = [(x * math.cos(theta) - y * math.sin(theta),
                    x * math.sin(theta) + y * math.cos(theta)) for x, y in video[topology]]
        half_window = video["window_half_size"]
        kind = "containers" if task == "VideoUnmaskSwap" else "cubes"
        angle_field = "container_yaw_degrees" if kind == "containers" else "cube_yaw_degrees"
        placements[kind] = []
        for index, (x, y) in enumerate(anchors):
            bounds = {"x": [x - half_window, x + half_window],
                      "y": [y - half_window, y + half_window]}
            placements[kind].append(point(f"{kind}_{index}", bounds, video[angle_field]))
        layout.update(topology=topology, anchors=anchors, yaw_degrees=angle,
                      window_half_size=half_window)
    return placements, layout
