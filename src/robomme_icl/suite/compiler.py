"""纯标准库的配额、位置分层与确定性候选编译器。"""

from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path

from .spec import COMPILER_VERSION, DIFFICULTIES, TASKS, EpisodeSpec, canonical_json, content_hash


DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"
COLORS = {"red": [1.0, 0.0, 0.0, 1.0], "green": [0.0, 1.0, 0.0, 1.0], "blue": [0.0, 0.0, 1.0, 1.0]}
PARAMETERS = {
    "BinFill": {"pick_count", "spawn_count", "target_color_count", "scene_color_count", "dynamic"},
    "RouteStick": {"walk_steps", "allow_backtracking"},
    "VideoUnmaskSwap": {"container_count", "pick_count", "swap_count"},
    "VideoRepick": {"spawn_count", "repeat_count", "swap_count"},
}


class _Stream:
    """SHA-256 计数器随机流，避免全局 RNG 和进程调度影响候选。"""

    def __init__(self, *parts):
        self.key = canonical_json(parts).encode("utf-8")
        self.counter = 0

    def integer(self) -> int:
        data = hashlib.sha256(self.key + self.counter.to_bytes(8, "big")).digest()
        self.counter += 1
        return int.from_bytes(data[:8], "big")

    def uniform(self) -> float:
        return (self.integer() >> 11) / 2**53

    def randbelow(self, n: int) -> int:
        if n <= 0:
            raise ValueError("随机整数的上界必须为正")
        cutoff = 2**64 - (2**64 % n)
        while True:
            number = self.integer()
            if number < cutoff:
                return number % n

    def shuffle(self, values: list) -> None:
        for end in range(len(values) - 1, 0, -1):
            selected = self.randbelow(end + 1)
            values[end], values[selected] = values[selected], values[end]


def _positive_int(value, name, *, zero=False):
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError(f"{name} 必须为{'非负' if zero else '正'}整数")


def _interval(value, name):
    if not isinstance(value, list) or len(value) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError(f"{name} 必须为两个有限数值组成的区间")
    if value[0] > value[1]:
        raise ValueError(f"{name} 区间上下界反向")


def validate_configs(task_config: dict, position_config: dict) -> None:
    """配置缺键或参数不可行时立即失败，不能回退旧随机初始化。"""
    if not isinstance(task_config, dict) or not isinstance(position_config, dict):
        raise ValueError("两份配置必须都是 JSON 对象")
    required_task = {"schema_version", "compiler_seed", "episode_seed_start", "task_order", "episodes_by_difficulty", "tasks"}
    required_position = {"schema_version", "compiler_seed", "max_candidates", "sampling", "safety_clearance", "table_bounds", "schedule", "geometry", "BinFill", "RouteStick", "video_layouts", "VideoRepick"}
    for config, keys in ((task_config, required_task), (position_config, required_position)):
        if set(config) != keys:
            raise ValueError(f"配置字段不匹配：缺少 {sorted(keys - config.keys())}，多余 {sorted(config.keys() - keys)}")
        if config["schema_version"] != 1:
            raise ValueError("仅支持配置 schema_version=1")
        _positive_int(config["compiler_seed"], "compiler_seed", zero=True)
    if task_config["task_order"] != list(TASKS) or set(task_config["tasks"]) != set(TASKS):
        raise ValueError("task_order 必须按固定顺序完整列出四任务")
    _positive_int(task_config["episode_seed_start"], "episode_seed_start", zero=True)
    if set(task_config["episodes_by_difficulty"]) != set(DIFFICULTIES):
        raise ValueError("episodes_by_difficulty 必须完整指定三档")
    for difficulty, count in task_config["episodes_by_difficulty"].items():
        _positive_int(count, difficulty, zero=True)
    if not sum(task_config["episodes_by_difficulty"].values()):
        raise ValueError("总 episode 配额不得为零")
    for task, difficulties in task_config["tasks"].items():
        if set(difficulties) != set(DIFFICULTIES):
            raise ValueError(f"{task} 必须完整指定三档参数")
        for difficulty, parameters in difficulties.items():
            if set(parameters) != PARAMETERS[task]:
                raise ValueError(f"{task}.{difficulty} 参数缺失或多余")
            for key, values in parameters.items():
                if not isinstance(values, list) or not values or len({canonical_json(v) for v in values}) != len(values):
                    raise ValueError(f"{task}.{difficulty}.{key} 必须为不重复的非空列表")
                if key in ("dynamic", "allow_backtracking"):
                    if any(type(v) is not bool for v in values):
                        raise ValueError(f"{key} 只允许布尔值")
                else:
                    for value in values:
                        _positive_int(value, key, zero=key == "swap_count")
            if task == "BinFill" and (max(parameters["target_color_count"]) > 3 or max(parameters["scene_color_count"]) > 3):
                raise ValueError("BinFill 最多支持三个目标颜色与场景颜色")
            if task == "VideoUnmaskSwap" and (not set(parameters["container_count"]) <= {3, 4} or max(parameters["pick_count"]) > 2):
                raise ValueError("VideoUnmaskSwap 支持三／四容器和一／两次抓取")
            if task == "VideoRepick":
                if set(parameters["spawn_count"]) != ({15} if difficulty == "hard" else {3}):
                    raise ValueError("VideoRepick easy/medium 固定三个方块，hard 固定十五个")
                if difficulty == "hard" and parameters["swap_count"] != [0]:
                    raise ValueError("VideoRepick hard 必须 swap_count=[0]")
            if not _legal_combinations(task, parameters):
                raise ValueError(f"{task}.{difficulty} 没有合法次数组合")
    pos = position_config
    _positive_int(pos["max_candidates"], "max_candidates")
    if pos["max_candidates"] > 1024:
        raise ValueError("每槽 max_candidates 不得超过 1024")
    if pos["sampling"] != "stratified":
        raise ValueError("首版只支持 stratified 分层采样")
    if type(pos["safety_clearance"]) not in (int, float) or not math.isfinite(pos["safety_clearance"]) or pos["safety_clearance"] < 0.005:
        raise ValueError("safety_clearance 不得小于 0.005 m")
    for axis in ("x", "y"):
        _interval(pos["table_bounds"][axis], f"table_bounds.{axis}")
    for group in (pos["BinFill"]["button"], pos["BinFill"]["board"], pos["BinFill"]["cubes"], pos["VideoRepick"]["button"], pos["VideoRepick"]["hard_cubes"]):
        for axis in ("x", "y"):
            _interval(group[axis], axis)
        if "yaw_degrees" in group:
            _interval(group["yaw_degrees"], "yaw_degrees")
    _interval(pos["RouteStick"]["yaw_degrees"], "RouteStick.yaw_degrees")
    if len(pos["RouteStick"]["center"]) != 2 or pos["RouteStick"]["spacing"] <= 0:
        raise ValueError("RouteStick center 或 spacing 非法")
    video = pos["video_layouts"]
    _interval(video["yaw_degrees"], "video_layouts.yaw_degrees")
    _interval(video["container_yaw_degrees"], "video_layouts.container_yaw_degrees")
    _interval(video["cube_yaw_degrees"], "video_layouts.cube_yaw_degrees")
    if video["three_object_topologies"] != ["triangle", "line"] or video["window_half_size"] <= 0:
        raise ValueError("三物体拓扑必须为 triangle、line；窗口必须为正")
    for name, count in (("triangle", 3), ("line", 3), ("rectangle", 4)):
        if len(video[name]) != count or any(len(point) != 2 for point in video[name]):
            raise ValueError(f"{name} 锚点数量或维度错误")
    for key in ("control_freq", "sim_freq", "swap_steps", "settle_steps", "max_episode_steps", "dynamic_reveal_interval_steps"):
        _positive_int(pos["schedule"][key], key)
    for key in ("swap_start_step", "swap_gap_steps"):
        _positive_int(pos["schedule"][key], key, zero=True)
    if pos["schedule"]["sim_freq"] % pos["schedule"]["control_freq"]:
        raise ValueError("sim_freq 必须是 control_freq 的整数倍")
    geo = pos["geometry"]
    fixed_geometry = {"container_half_size": [0.03, 0.03, 0.036], "container_center_z": 0.036,
                      "central_box_top_z": 0.072, "button_half_size": [0.0375, 0.0375, 0.0075],
                      "button_root_z": 0.0075, "button_cap_radius": 0.0225, "button_cap_half_length": 0.009}
    for key, value in fixed_geometry.items():
        if geo.get(key) != value:
            raise ValueError(f"首版固定 geometry.{key}={value}，不能与实际 builder 几何不一致")
    if geo["swap_lane_offset"] != 0.07 or pos["schedule"]["swap_steps"] != 50:
        raise ValueError("首版交换轨道固定为 0.07 m、50 个控制步")
    for key in ("cube_half_size", "central_box_thickness", "central_box_top_z", "hidden_cube_half_size", "board_side", "hole_side", "board_thickness", "swap_lane_offset", "route_target_radius"):
        if type(geo[key]) not in (int, float) or not math.isfinite(geo[key]) or geo[key] <= 0:
            raise ValueError(f"geometry.{key} 必须为有限正数")
    if geo["hole_side"] >= geo["board_side"]:
        raise ValueError("board 的孔必须小于外边长")
    if geo["central_box_top_z"] - geo["central_box_thickness"] - 2 * geo["hidden_cube_half_size"] < pos["safety_clearance"]:
        raise ValueError("藏块与中央 box 的顶部净距不足")


def load_configs(task_path=None, position_path=None) -> tuple[dict, dict]:
    task_path = DEFAULT_CONFIG_DIR / "task_distribution.json" if task_path is None else Path(task_path)
    position_path = DEFAULT_CONFIG_DIR / "position_distribution.json" if position_path is None else Path(position_path)
    with task_path.open(encoding="utf-8") as stream:
        task_config = json.load(stream)
    with position_path.open(encoding="utf-8") as stream:
        position_config = json.load(stream)
    validate_configs(task_config, position_config)
    return task_config, position_config


def _legal_combinations(task, choices):
    keys = sorted(choices)
    result = []
    for values in itertools.product(*(choices[key] for key in keys)):
        row = dict(zip(keys, values))
        if task == "BinFill":
            if not row["target_color_count"] <= row["pick_count"] <= row["spawn_count"]:
                continue
            if row["scene_color_count"] < row["target_color_count"] or row["spawn_count"] < row["pick_count"] + row["scene_color_count"] - row["target_color_count"]:
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
        dynamic_targets = {v: count // len(values) + (i < count % len(values)) for i, v in enumerate(values)}
    for _ in range(remainder):
        eligible = [row for row in pool if not dynamic_targets or marginal["dynamic"][row["dynamic"]] < dynamic_targets[row["dynamic"]]]
        if not eligible:
            raise ValueError("动态配额与合法次数组合无法同时满足")
        row = min(eligible, key=lambda item: sum((2 * marginal[key][item[key]] + 1) * len(choices[key]) for key in choices))
        rows.append(copy.deepcopy(row))
        pool.remove(row)
        for key in choices:
            marginal[key][row[key]] += 1
    stream.shuffle(rows)
    return rows


def plan_slots(task_config, position_config, tasks=None, episodes_per_task=None) -> list[dict]:
    """固定任务名额和每个连续参数的位置层；结果可以独立交给任意 worker。"""
    validate_configs(task_config, position_config)
    requested = list(TASKS) if tasks is None else list(tasks)
    if not requested or len(set(requested)) != len(requested) or not set(requested) <= set(TASKS):
        raise ValueError("tasks 必须为不重复的已知任务列表")
    quotas = dict(task_config["episodes_by_difficulty"])
    if episodes_per_task is not None:
        _positive_int(episodes_per_task, "episodes_per_task")
        quotas = {d: episodes_per_task // 3 + (i < episodes_per_task % 3) for i, d in enumerate(DIFFICULTIES)}
    per_task = sum(quotas.values())
    if task_config["episode_seed_start"] + len(TASKS) * per_task > 2**31:
        raise ValueError("新 seed 分配将超出有符号 32 位范围")
    slots = []
    for task_number, task in enumerate(TASKS):
        if task not in requested:
            continue
        episode = 0
        for difficulty in DIFFICULTIES:
            choices = task_config["tasks"][task][difficulty]
            stream = _Stream(task_config["compiler_seed"], task, difficulty, "quota")
            rows = _quota_rows(task, choices, quotas[difficulty], stream)
            topology_ranks = defaultdict(int)
            for rank, parameters in enumerate(rows):
                count = parameters.get("container_count", parameters.get("spawn_count", 0))
                topology = "field" if task == "BinFill" or count == 15 else "route" if task == "RouteStick" else "rectangle" if count == 4 else ("triangle", "line")[rank % 2]
                # 拓扑分配属于位置配置域，不参与任务次数 RNG。
                slot = {
                    "slot_id": f"{task}/{difficulty}/{rank:04d}", "task_kind": task,
                    "difficulty": difficulty, "episode": episode,
                    "seed": task_config["episode_seed_start"] + task_number * per_task + episode,
                    "parameters": parameters, "topology": topology,
                    "difficulty_rank": rank, "topology_rank": topology_ranks[topology],
                    "max_candidates": position_config["max_candidates"],
                    "task_config": copy.deepcopy(task_config), "position_config": copy.deepcopy(position_config),
                }
                topology_ranks[topology] += 1
                slots.append(slot)
                episode += 1
    groups = defaultdict(list)
    for slot in slots:
        group = (slot["task_kind"], slot["difficulty"], slot["topology"], slot["parameters"].get("spawn_count", slot["parameters"].get("container_count", 0)))
        groups[group].append(slot)
    for group, group_slots in groups.items():
        for index, slot in enumerate(group_slots):
            slot["position_group"] = list(group)
            slot["position_rank"] = index
            slot["position_count"] = len(group_slots)
        if group_slots[0]["topology"] == "field" and len(group_slots) >= 4:
            _allocate_field_layers(group_slots)
        elif group_slots[0]["topology"] in ("triangle", "line", "rectangle"):
            _allocate_video_yaw_layers(group_slots)
    return slots


def _allocate_video_yaw_layers(slots):
    """在计划阶段配对原有朝向层与位置层，完整物体必须能放进初始窗口。

    位置层范围与每轴配额完全保持。首先匹配整个朝向层都可行的配对；
    必要时匹配至少存在可行朝向的配对，随后候选阶段只在冻结层内拒绝。
    """
    from robomme_icl.geometry.collision import actor_boxes, box_components

    first, count = slots[0], len(slots)
    pos = first["position_config"]
    geometry, cfg = pos["geometry"], pos["video_layouts"]
    is_container = first["task_kind"] == "VideoUnmaskSwap"
    kind = "container" if is_container else "cube"
    half = geometry["container_half_size"] if is_container else [geometry["cube_half_size"]] * 3
    margin, window = half[0], cfg["window_half_size"]
    support = [-window + margin, window - margin]
    yaw_support = cfg["container_yaw_degrees" if is_container else "cube_yaw_degrees"]
    shape = _actor("probe", kind, [0.0, 0.0, 0.0], half)
    vertices = []
    for component in box_components(shape, geometry):
        for sx, sy in itertools.product((-1, 1), repeat=2):
            vertices.append((component["position"][0] + sx * component["half_size"][0], component["position"][1] + sy * component["half_size"][1]))
    projections = []
    for layer in range(count):
        low = yaw_support[0] + (yaw_support[1] - yaw_support[0]) * layer / count
        high = yaw_support[0] + (yaw_support[1] - yaw_support[0]) * (layer + 1) / count
        angles = {low, high}
        # 每个实际碰撞形状角点的旋转投影极值均位于端点或导数零点。
        for x, y in vertices:
            for phase in (math.degrees(math.atan2(-y, x)), math.degrees(math.atan2(x, y))):
                for turn in range(math.floor((low - phase) / 180) - 1, math.ceil((high - phase) / 180) + 2):
                    angle = phase + turn * 180
                    if low <= angle <= high:
                        angles.add(angle)
        # 容器对称外轮廓的分段交点也可能给出投影下界。
        angles.update(turn * 45 for turn in range(math.ceil(low / 45), math.floor(high / 45) + 1))
        values = []
        for angle in sorted(angles):
            shape["quaternion"] = _yaw(angle)
            boxes = actor_boxes(shape, geometry)
            extrema = []
            for axis in range(2):
                unit = tuple(float(i == axis) for i in range(3))
                extrema.append((min(box.center[axis] - box.radius_on(unit) for box in boxes), max(box.center[axis] + box.radius_on(unit) for box in boxes)))
            values.append(extrema)
        projections.append(values)
    actor_count = first["parameters"].get("container_count", first["parameters"].get("spawn_count"))
    for slot in slots:
        slot["video_yaw_layers"] = {}
    for actor_number in range(actor_count):
        fields = []
        for slot in slots:
            strata = {}
            for axis in ("x", "y"):
                _sample(slot, 0, f"anchor_{actor_number}.{axis}", support, strata)
            fields.append([strata[f"anchor_{actor_number}.{axis}"]["bounds"] for axis in ("x", "y")])

        def can_fit(episode, layer, require_all):
            fits = [all(max(fields[episode][axis][0], -window - extrema[axis][0]) < min(fields[episode][axis][1], window - extrema[axis][1]) for axis in range(2)) for extrema in projections[layer]]
            return all(fits) if require_all else any(fits)

        solution = None
        for require_all in (True, False):
            options = []
            for episode in range(count):
                values = [layer for layer in range(count) if can_fit(episode, layer, require_all)]
                _Stream(pos["compiler_seed"], first["position_group"], actor_number, episode, "yaw-layer-matching").shuffle(values)
                options.append(values)
            owner = {}

            def augment(episode, seen):
                for layer in options[episode]:
                    if layer in seen:
                        continue
                    seen.add(layer)
                    if layer not in owner or augment(owner[layer], seen):
                        owner[layer] = episode
                        return True
                return False

            if all(augment(episode, set()) for episode in sorted(range(count), key=lambda i: len(options[i]))):
                solution = {episode: layer for layer, episode in owner.items()}
                break
        if solution is None:
            raise ValueError(f"{first['position_group']} 的 anchor_{actor_number} 无法保持原轴层配额并满足完整物体初始外框")
        for episode, slot in enumerate(slots):
            slot["video_yaw_layers"][f"anchor_{actor_number}.yaw_degrees"] = solution[episode]


def _allocate_field_layers(slots):
    """先用确定性匹配分配细网格，避免将方块锁在按钮完全覆盖的层里。

    每个物体在本组的每条 x/y 轴层各出现一次。匹配只发生在计划阶段，
    候选认证失败后不再改变这些层。粗网格组依旧由层内构造处理。
    """
    count = len(slots)
    first = slots[0]
    pos = first["position_config"]
    size = pos["geometry"]["cube_half_size"]
    support = pos["BinFill"]["cubes"] if first["task_kind"] == "BinFill" else pos["VideoRepick"]["hard_cubes"]
    span = {axis: [support[axis][0] + size, support[axis][1] - size] for axis in ("x", "y")}
    blockers = []
    for slot in slots:
        fields = {}
        task = slot["task_kind"]
        for axis in ("x", "y"):
            _sample(slot, 0, f"button.{axis}", pos[task]["button"][axis], fields)
        half = pos["geometry"]["button_half_size"]
        rectangles = [(fields["button.x"]["bounds"], fields["button.y"]["bounds"], max(half[:2]))]
        if task == "BinFill":
            for axis in ("x", "y"):
                _sample(slot, 0, f"board.{axis}", pos[task]["board"][axis], fields)
            rectangles.append((fields["board.x"]["bounds"], fields["board.y"]["bounds"], pos["geometry"]["board_side"] / math.sqrt(2)))
        blockers.append(rectangles)
    used = [Counter() for _ in slots]
    object_count = first["parameters"]["spawn_count"]
    capacity = math.ceil(object_count / count**2)
    for slot in slots:
        slot["field_layers"] = {}

    def admissible(episode, x_layer, y_layer):
        if used[episode][(x_layer, y_layer)] >= capacity:
            return False
        coordinates = []
        for axis, layer in (("x", x_layer), ("y", y_layer)):
            low, high = span[axis]
            coordinates.append([low + (high - low) * layer / count, low + (high - low) * (layer + 1) / count])
        padding = size * math.sqrt(2) + pos["safety_clearance"]
        return any(all(x < bx[0] - radius - padding or x > bx[1] + radius + padding or y < by[0] - radius - padding or y > by[1] + radius + padding
                       for bx, by, radius in blockers[episode]) for x, y in itertools.product(*coordinates))

    for number in range(object_count):
        solution = None
        for attempt in range(64):
            x_layers = list(range(count))
            rng = _Stream(pos["compiler_seed"], first["position_group"], number, attempt, "field-matching")
            rng.shuffle(x_layers)
            options = []
            for episode in range(count):
                values = [layer for layer in range(count) if admissible(episode, x_layers[episode], layer)]
                rng.shuffle(values)
                options.append(values)
            owner = {}

            def augment(episode, seen):
                for layer in options[episode]:
                    if layer in seen:
                        continue
                    seen.add(layer)
                    if layer not in owner or augment(owner[layer], seen):
                        owner[layer] = episode
                        return True
                return False

            order = sorted(range(count), key=lambda episode: len(options[episode]))
            if all(augment(episode, set()) for episode in order):
                y_layers = {episode: layer for layer, episode in owner.items()}
                solution = x_layers, y_layers
                break
        if solution is None:
            raise ValueError(f"{first['position_group']} 无法在保持逐轴分层均衡时为 cube_{number} 分配安全网格")
        x_layers, y_layers = solution
        for episode, slot in enumerate(slots):
            slot["field_layers"][f"cube_{number}.x"] = x_layers[episode]
            slot["field_layers"][f"cube_{number}.y"] = y_layers[episode]
            used[episode][(x_layers[episode], y_layers[episode])] += 1


def _sample(slot, index, name, bounds, strata):
    count = slot["position_count"]
    order = list(range(count))
    seed = slot["position_config"]["compiler_seed"]
    actor_name, axis = name.rsplit(".", 1)
    if name in slot.get("video_yaw_layers", {}):
        layer = slot["video_yaw_layers"][name]
    elif name in slot.get("field_layers", {}):
        layer = slot["field_layers"][name]
    elif slot["topology"] == "field" and actor_name.startswith("cube_") and axis in ("x", "y"):
        # 场地内各物体协同分配轴层：同一物体跨 episode 仍各层一次，
        # 同一 episode 的前 count**2 个物体不占相同二维网格。
        number = int(actor_name.removeprefix("cube_"))
        offset = number if axis == "x" else 3 * (number % count) + number // count
        _Stream(seed, slot["position_group"], f"field.{axis}", "strata").shuffle(order)
        layer = (order[slot["position_rank"]] + offset) % count
    else:
        _Stream(seed, slot["position_group"], name, "strata").shuffle(order)
        layer = order[slot["position_rank"]]
    low, high = bounds
    layer_low = low + (high - low) * layer / count
    layer_high = low + (high - low) * (layer + 1) / count
    strata[name] = {"index": layer, "count": count, "bounds": [layer_low, layer_high], "support": list(bounds)}
    offset = _Stream(seed, slot["slot_id"], index, name, "within-stratum").uniform()
    return layer_low + (layer_high - layer_low) * offset


def _yaw(degrees):
    angle = math.radians(degrees) / 2
    return [math.cos(angle), 0.0, 0.0, math.sin(angle)]


def _rotate(point, degrees):
    angle = math.radians(degrees)
    return [point[0] * math.cos(angle) - point[1] * math.sin(angle), point[0] * math.sin(angle) + point[1] * math.cos(angle)]


def _actor(identifier, kind, position, half_size, yaw=0.0, color=None, role="distractor", **extra):
    return {"id": identifier, "kind": kind, "position": list(position), "quaternion": _yaw(yaw), "half_size": list(half_size), "color": list(color or [0.75, 0.75, 0.75, 1.0]), "role": role, **extra}


def _sample_initial_support(actor, slot, candidate_index, strata, geometry, *, trial=0, prefix=None, anchor=(0.0, 0.0)):
    """按真实旋转投影求原位置层与完整物体支持外框的中心区交集。

    对交集均匀采样，不能把已抽到的越界位置裁到边缘。若交集为空，
    保留带明确拒绝标记的候选，交给几何认证拒绝；不会偷偷换位置层。
    """
    from robomme_icl.geometry.collision import actor_boxes

    bounds = actor["initial_xy_bounds"]
    prefix = actor["id"] if prefix is None else prefix
    boxes = actor_boxes(actor, geometry)
    intervals = []
    for coordinate, axis in enumerate(("x", "y")):
        unit = tuple(float(i == coordinate) for i in range(3))
        minimum = min(box.center[coordinate] - box.radius_on(unit) for box in boxes) - actor["position"][coordinate]
        maximum = max(box.center[coordinate] + box.radius_on(unit) for box in boxes) - actor["position"][coordinate]
        low, high = strata[f"{prefix}.{axis}"]["bounds"]
        low = max(low + anchor[coordinate], bounds[axis][0] - minimum)
        high = min(high + anchor[coordinate], bounds[axis][1] - maximum)
        if low >= high:
            actor["initial_support_rejection"] = f"{actor['id']}.{axis} 原位置层与旋转后的完整支持框无正宽交集"
            return False
        intervals.append((low, high))
    actor.pop("initial_support_rejection", None)
    for coordinate, (low, high) in enumerate(intervals):
        rng = _Stream(slot["position_config"]["compiler_seed"], slot["slot_id"], candidate_index, actor["id"], trial, coordinate, "initial-support-intersection")
        actor["position"][coordinate] = low + (high - low) * rng.uniform()
    return True


def _pack_field(actors, slot, candidate_index, strata, geometry):
    """在既定位置层内逐物体构造候选，减少整场独立重抽的组合爆炸。

    每个方块最多尝试 32 个层内点；无法放置时保留净距最大的点并
    标记未解决，交给外层认证拒绝。不换层、不删除物体、不降低间距。
    几何模块同样只依赖标准库，这里不会导入仿真引擎。
    """
    from robomme_icl.geometry.collision import actor_boxes, box_clearance

    placed = [actor for actor in actors if actor["kind"] != "cube"]
    previous_boxes = [box for actor in placed for box in actor_boxes(actor, geometry)]
    attempts, unresolved = {}, []
    margin = geometry["safety_clearance"]
    for actor in (actor for actor in actors if actor["kind"] == "cube"):
        identifier = actor["id"]
        best, best_gap, accepted = None, -math.inf, False
        for trial in range(32):
            proposed = copy.deepcopy(actor)
            if trial:
                low, high = strata[f"{identifier}.yaw_degrees"]["bounds"]
                rng = _Stream(slot["position_config"]["compiler_seed"], slot["slot_id"], candidate_index, identifier, trial, "yaw_degrees", "packing")
                proposed["quaternion"] = _yaw(low + (high - low) * rng.uniform())
            if not _sample_initial_support(proposed, slot, candidate_index, strata, geometry, trial=trial):
                if best is None:
                    best = proposed
                continue
            boxes = actor_boxes(proposed, geometry)
            gap = min((box_clearance(a, b) for a in boxes for b in previous_boxes), default=math.inf)
            if gap > best_gap:
                best, best_gap = proposed, gap
            if gap >= margin:
                accepted = True
                break
        actor.update(best)
        attempts[identifier] = trial + 1
        if not accepted:
            unresolved.append(identifier)
        previous_boxes.extend(actor_boxes(actor, geometry))
    return {"method": "sequential_within_stratum", "attempts": attempts, "unresolved": unresolved}


def candidate_for_slot(slot: dict, candidate_index: int) -> EpisodeSpec:
    """同一名额的拒绝采样只改变候选，不改变次数、位置分层或 seed。"""
    if type(candidate_index) is not int or not 0 <= candidate_index < slot["max_candidates"]:
        raise ValueError("candidate_index 超出该名额的固定候选预算")
    task = slot["task_kind"]
    pos = slot["position_config"]
    geometry = copy.deepcopy(pos["geometry"])
    geometry["safety_clearance"] = pos["safety_clearance"]
    geometry["table_bounds"] = copy.deepcopy(pos["table_bounds"])
    parameters = copy.deepcopy(slot["parameters"])
    schedule = copy.deepcopy(pos["schedule"])
    stream = _Stream(slot["task_config"]["compiler_seed"], slot["slot_id"], "task-details")
    strata, actors = {}, []
    layout = {"topology": slot["topology"], "strata": strata, "table_bounds": copy.deepcopy(pos["table_bounds"])}

    def sample(name, bounds):
        return _sample(slot, candidate_index, name, bounds, strata)

    def sample_xy(name, bounds, inset=0.0):
        return [sample(f"{name}.{axis}", [bounds[axis][0] + inset, bounds[axis][1] - inset]) for axis in ("x", "y")]

    def add_button(bounds):
        xy = sample_xy("button", bounds)
        actors.append(_actor("button", "button", [*xy, geometry["button_root_z"]], geometry["button_half_size"], role="finish_button"))

    size = geometry["cube_half_size"]
    if task == "BinFill":
        add_button(pos[task]["button"])
        board = pos[task]["board"]
        xy = sample_xy("board", board)
        yaw = sample("board.yaw_degrees", board["yaw_degrees"])
        actors.append(_actor("board", "board", [*xy, geometry["board_thickness"] / 2], [geometry["board_side"] / 2] * 2 + [geometry["board_thickness"] / 2], yaw, role="receptacle"))
        names = list(COLORS)
        stream.shuffle(names)
        names = names[:parameters["scene_color_count"]]
        active = names[:parameters["target_color_count"]]
        target_counts = dict.fromkeys(COLORS, 0)
        for name in active:
            target_counts[name] += 1
        for _ in range(parameters["pick_count"] - len(active)):
            target_counts[active[stream.randbelow(len(active))]] += 1
        cube_colors = [name for name, number in target_counts.items() for _ in range(number)]
        # 每个声明的场景颜色至少出现一次；非目标颜色也计入 spawn_count。
        cube_colors.extend(name for name in names if name not in cube_colors)
        while len(cube_colors) < parameters["spawn_count"]:
            cube_colors.append(names[stream.randbelow(len(names))])
        stream.shuffle(cube_colors)
        remaining = dict(target_counts)
        targets = []
        bounds = pos[task]["cubes"]
        for number, name in enumerate(cube_colors):
            identifier = f"cube_{number}"
            is_target = remaining[name] > 0
            if is_target:
                remaining[name] -= 1
                targets.append(identifier)
            xy = sample_xy(identifier, bounds, size)
            yaw = sample(f"{identifier}.yaw_degrees", bounds["yaw_degrees"])
            actors.append(_actor(identifier, "cube", [*xy, size], [size] * 3, yaw, COLORS[name], "target" if is_target else "distractor", color_name=name, initial_xy_bounds={axis: list(bounds[axis]) for axis in ("x", "y")}))
        color_seen = Counter()
        reveal_steps = {}
        for actor in actors:
            if actor["kind"] == "cube":
                name = actor["color_name"]
                reveal_steps[actor["id"]] = color_seen[name] * schedule["dynamic_reveal_interval_steps"] if parameters["dynamic"] else 0
                color_seen[name] += 1
        parameters.update(target_counts=target_counts, target_ids=targets, reveal_steps_by_id=reveal_steps)
    elif task == "RouteStick":
        cfg = pos[task]
        yaw = sample("route.yaw_degrees", cfg["yaw_degrees"])
        layout["yaw_degrees"] = yaw
        for number in range(9):
            xy = _rotate([cfg["center"][0], cfg["center"][1] + (number - 4) * cfg["spacing"]], yaw)
            if number % 2 == 0:
                radius = geometry["route_target_radius"]
                actors.append(_actor(f"target_{number // 2}", "target", [*xy, 0.01], [radius, radius, 0.005], yaw, role="route_target"))
            else:
                half = geometry["route_obstacle_half_size"]
                actors.append(_actor(f"obstacle_{number // 2}", "obstacle", [*xy, half[2]], half, yaw, [stream.uniform(), stream.uniform(), stream.uniform(), 1.0], "obstacle"))
        path = [stream.randbelow(5)]
        for _ in range(parameters["walk_steps"]):
            possibilities = [i for i in (path[-1] - 1, path[-1] + 1) if 0 <= i < 5]
            if len(path) > 1 and not parameters["allow_backtracking"] and len(possibilities) > 1:
                possibilities = [i for i in possibilities if i != path[-2]]
            path.append(possibilities[stream.randbelow(len(possibilities))])
        parameters.update(path_indices=path, directions=[(-1, 1)[stream.randbelow(2)] for _ in range(parameters["walk_steps"])], target_ids=[f"target_{i}" for i in path])
    else:
        count = parameters.get("container_count", parameters.get("spawn_count"))
        if task == "VideoRepick":
            add_button(pos[task]["button"])
        if slot["topology"] == "field":
            bounds = pos["VideoRepick"]["hard_cubes"]
            positions = [sample_xy(f"cube_{i}", bounds, size) for i in range(count)]
            yaws = [sample(f"cube_{i}.yaw_degrees", bounds["yaw_degrees"]) for i in range(count)]
            initial_bounds = [{axis: list(bounds[axis]) for axis in ("x", "y")} for _ in range(count)]
        else:
            cfg = pos["video_layouts"]
            yaw = sample("layout.yaw_degrees", cfg["yaw_degrees"])
            layout["yaw_degrees"] = yaw
            anchors = [_rotate(point, yaw) for point in cfg[slot["topology"]]]
            layout["anchors"] = anchors
            initial_bounds = [{axis: [point[i] - cfg["window_half_size"], point[i] + cfg["window_half_size"]] for i, axis in enumerate(("x", "y"))} for point in anchors]
            margin = geometry["container_half_size"][0] if task == "VideoUnmaskSwap" else size
            width = cfg["window_half_size"] - margin
            if width <= 0:
                raise ValueError("锚点采样窗口不足以容纳物体")
            positions = [[point[axis] + sample(f"anchor_{i}.{'xy'[axis]}", [-width, width]) for axis in range(2)] for i, point in enumerate(anchors)]
            yaw_range = cfg["container_yaw_degrees" if task == "VideoUnmaskSwap" else "cube_yaw_degrees"]
            yaws = [sample(f"anchor_{i}.yaw_degrees", yaw_range) for i in range(count)]
        indices = list(range(count))
        # 角色相对锚点轮转，避免零号位置长期固定为目标或空容器。
        _Stream(slot["task_config"]["compiler_seed"], task, slot["difficulty"], "role-order").shuffle(indices)
        shift = slot["difficulty_rank"] % count
        indices = indices[shift:] + indices[:shift]
        if task == "VideoUnmaskSwap":
            targets = [f"container_{i}" for i in indices[:parameters["pick_count"]]]
            colors = list(COLORS)
            stream.shuffle(colors)
            for i, (xy, yaw) in enumerate(zip(positions, yaws)):
                actors.append(_actor(f"container_{i}", "container", [*xy, geometry["container_center_z"]], geometry["container_half_size"], yaw, role="target" if f"container_{i}" in targets else "distractor", initial_xy_bounds=initial_bounds[i]))
            occupied_indices = indices if count == 3 else indices[:-1]
            for cube_index, container_index in enumerate(occupied_indices):
                half = geometry["hidden_cube_half_size"]
                name = colors[cube_index % len(colors)]
                actors.append(_actor(f"cube_{cube_index}", "cube", [*positions[container_index], half], [half] * 3, yaws[container_index], COLORS[name], "hidden_target" if f"container_{container_index}" in targets else "hidden_distractor", color_name=name, parent_id=f"container_{container_index}"))
            parameters.update(target_container_ids=targets, target_ids=[actor["id"] for actor in actors if actor["role"] == "hidden_target"], empty_container_id=None if count == 3 else f"container_{indices[-1]}")
        else:
            target = indices[0]
            colors = list(COLORS)
            stream.shuffle(colors)
            for i, (xy, yaw) in enumerate(zip(positions, yaws)):
                # 三方块场景必须同色，才能保留依靠演示记忆目标身份的任务。
                name = colors[i % len(colors)] if slot["difficulty"] == "hard" else colors[0]
                actors.append(_actor(f"cube_{i}", "cube", [*xy, size], [size] * 3, yaw, COLORS[name], "target" if i == target else "distractor", color_name=name, initial_xy_bounds=initial_bounds[i]))
            parameters.update(target_ids=[f"cube_{target}"], pick_count=parameters["repeat_count"])

    if slot["topology"] == "field":
        layout["packing"] = _pack_field(actors, slot, candidate_index, strata, geometry)
    elif slot["topology"] not in ("route",):
        for actor in actors:
            if "initial_xy_bounds" in actor:
                index = int(actor["id"].rsplit("_", 1)[1])
                _sample_initial_support(actor, slot, candidate_index, strata, geometry, prefix=f"anchor_{index}", anchor=layout["anchors"][index])
        by_id = {actor["id"]: actor for actor in actors}
        for actor in actors:
            if "parent_id" in actor:
                actor["position"][:2] = by_id[actor["parent_id"]]["position"][:2]
    swaps = []
    swap_stream = _Stream(slot["task_config"]["compiler_seed"], slot["slot_id"], candidate_index, "swap-candidate")
    swappable = [actor for actor in actors if actor["kind"] == ("container" if task == "VideoUnmaskSwap" else "cube")]
    occupants = [actor["id"] for actor in swappable]
    for number in range(parameters.get("swap_count", 0)):
        if slot["topology"] == "rectangle":
            pairs = [(0, 1), (1, 2), (2, 3), (3, 0)]
        elif slot["topology"] == "line":
            pairs = [(0, 2), (2, 1)]
        else:
            pairs = list(itertools.combinations(range(len(occupants)), 2))
        # 交换逻辑槽位由任务随机流确定，不受位置 seed 或运行时 pose 影响。
        left, right = pairs[swap_stream.randbelow(len(pairs))]
        pair = occupants[left], occupants[right]
        start = schedule["swap_start_step"] + number * (schedule["swap_steps"] + schedule["swap_gap_steps"])
        swaps.append({"a": pair[0], "b": pair[1], "start_step": start, "end_step": start + schedule["swap_steps"], "lane_offset": geometry["swap_lane_offset"]})
        occupants[left], occupants[right] = occupants[right], occupants[left]
    return EpisodeSpec.from_dict({
        "schema_version": 1, "task_kind": task, "seed": slot["seed"], "episode": slot["episode"],
        "difficulty": slot["difficulty"], "robot_kind": "panda_stick" if task == "RouteStick" else "panda_wristcam",
        "env_id": f"RoboMME-ICL/{task}-v0", "task_parameters": parameters, "actors": actors,
        "swaps": swaps, "layout": layout, "geometry": geometry, "schedule": schedule,
        "provenance": {"compiler_version": COMPILER_VERSION, "task_config_hash": content_hash(slot["task_config"]), "position_config_hash": content_hash(pos), "slot_id": slot["slot_id"], "candidate_index": candidate_index},
    })


def distribution_summary(slots: list[dict]) -> dict:
    """同时列出已分配次数与零覆盖组合，避免把小样本称为全组合覆盖。"""
    summary = {}
    grouped = defaultdict(list)
    for slot in slots:
        grouped[(slot["task_kind"], slot["difficulty"])].append(slot)
    for (task, difficulty), group in grouped.items():
        choices = group[0]["task_config"]["tasks"][task][difficulty]
        counts = Counter(canonical_json(slot["parameters"]) for slot in group)
        summary[f"{task}/{difficulty}"] = {
            "episodes": len(group), "topologies": dict(Counter(slot["topology"] for slot in group)),
            "combinations": [{"parameters": row, "count": counts[canonical_json(row)]} for row in _legal_combinations(task, choices)],
        }
    return summary
