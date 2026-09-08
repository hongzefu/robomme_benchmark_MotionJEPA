"""与仿真依赖隔离的不可变单局环境记录。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any


TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")
DIFFICULTIES = ("easy", "medium", "hard")
COMPILER_VERSION = "1.0.0"


def canonical_json(value: Any) -> str:
    """使用固定键顺序且禁止 NaN，使哈希独立于字典插入顺序。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _vector(value: Any, size: int, label: str) -> None:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} 必须含 {size} 个数值")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError(f"{label} 必须为有限数值")


def validate_spec(data: dict) -> None:
    """验证清单结构和内部引用，物理可行性由独立认证器负责。"""
    required = {
        "schema_version", "task_kind", "seed", "episode", "difficulty", "robot_kind", "env_id",
        "task_parameters", "actors", "swaps", "layout", "geometry", "schedule", "provenance",
    }
    if set(data) != required:
        raise ValueError(f"EpisodeSpec 字段不匹配：缺少 {sorted(required - data.keys())}，多余 {sorted(data.keys() - required)}")
    task = data["task_kind"]
    if data["schema_version"] != 1 or task not in TASKS or data["difficulty"] not in DIFFICULTIES:
        raise ValueError("不支持的 EpisodeSpec 版本、任务或难度")
    if type(data["seed"]) is not int or not 0 <= data["seed"] < 2**31:
        raise ValueError("seed 必须为 [0, 2**31) 内整数")
    if type(data["episode"]) is not int or data["episode"] < 0:
        raise ValueError("episode 必须为非负整数")
    robot = "panda_stick" if task == "RouteStick" else "panda_wristcam"
    if data["robot_kind"] != robot or data["env_id"] != f"RoboMME-ICL/{task}-v0":
        raise ValueError("环境 ID、机器人和任务不匹配")
    for name in ("task_parameters", "layout", "geometry", "schedule", "provenance"):
        if not isinstance(data[name], dict):
            raise ValueError(f"{name} 必须为对象")
    if not isinstance(data["actors"], list) or not data["actors"]:
        raise ValueError("actors 不得为空")
    ids = set()
    for actor in data["actors"]:
        if not isinstance(actor, dict) or not isinstance(actor.get("id"), str) or not actor["id"]:
            raise ValueError("actor 必须有非空稳定 ID")
        if actor["id"] in ids:
            raise ValueError(f"actor ID 重复：{actor['id']}")
        ids.add(actor["id"])
        if actor.get("kind") not in {"cube", "container", "board", "button", "target", "obstacle"}:
            raise ValueError("未知 actor kind")
        for name, size in (("position", 3), ("quaternion", 4), ("half_size", 3), ("color", 4)):
            _vector(actor.get(name), size, f"{actor['id']}.{name}")
        if min(actor["half_size"]) <= 0:
            raise ValueError("actor half_size 必须为正")
        if abs(sum(x * x for x in actor["quaternion"]) - 1) > 1e-9:
            raise ValueError("actor quaternion 必须归一化")
        if not isinstance(actor.get("role"), str):
            raise ValueError("actor role 必须为字符串")
        if "initial_xy_bounds" in actor:
            bounds = actor["initial_xy_bounds"]
            if not isinstance(bounds, dict) or set(bounds) != {"x", "y"}:
                raise ValueError("initial_xy_bounds 必须明确指定 x、y 外框")
            for axis in ("x", "y"):
                _vector(bounds[axis], 2, f"{actor['id']}.initial_xy_bounds.{axis}")
                if bounds[axis][0] >= bounds[axis][1]:
                    raise ValueError("初始完整物体外框必须具有正宽度")
    for actor in data["actors"]:
        if "parent_id" in actor and actor["parent_id"] not in ids:
            raise ValueError("藏块 parent_id 不存在")
    params = data["task_parameters"]
    by_id = {actor["id"]: actor for actor in data["actors"]}
    for key in ("target_ids", "target_container_ids"):
        if any(identifier not in ids for identifier in params.get(key, [])):
            raise ValueError(f"{key} 引用了不存在的 actor")
    if not isinstance(data["swaps"], list):
        raise ValueError("swaps 必须为列表")
    previous_end = -1
    for swap in data["swaps"]:
        if swap.get("a") not in ids or swap.get("b") not in ids or swap["a"] == swap["b"]:
            raise ValueError("swap 两端必须是不同的已有 actor")
        start, end = swap.get("start_step"), swap.get("end_step")
        if type(start) is not int or type(end) is not int or not 0 <= start < end or start < previous_end:
            raise ValueError("swap 时间区间必须递增且不能重叠")
        previous_end = end
        if type(swap.get("lane_offset")) not in (float, int) or swap["lane_offset"] <= 0:
            raise ValueError("swap lane_offset 必须为正")
    if params.get("swap_count", 0) != len(data["swaps"]):
        raise ValueError("swap_count 与完整交换序列不一致")
    for name in ("pick_count", "spawn_count", "repeat_count", "walk_steps", "container_count", "target_color_count", "scene_color_count"):
        if name in params and (type(params[name]) is not int or params[name] <= 0):
            raise ValueError(f"{name} 必须为正整数")
    if type(params.get("swap_count", 0)) is not int or params.get("swap_count", 0) < 0:
        raise ValueError("swap_count 必须为非负整数")
    cube_ids = {actor["id"] for actor in data["actors"] if actor["kind"] == "cube"}
    if task in ("BinFill", "VideoRepick") and params.get("spawn_count") != len(cube_ids):
        raise ValueError("spawn_count 与已声明方块数量不一致")
    if task == "BinFill":
        counts = params.get("target_counts", {})
        if set(counts) != {"red", "green", "blue"} or any(type(n) is not int or n < 0 for n in counts.values()):
            raise ValueError("target_counts 必须完整指定三色的非负整数数量")
        if sum(counts.values()) != params.get("pick_count") or sum(n > 0 for n in counts.values()) != params.get("target_color_count"):
            raise ValueError("目标颜色数或放入总数与 target_counts 不一致")
        targets = params.get("target_ids", [])
        if len(set(targets)) != params.get("pick_count") or len(targets) != len(set(targets)) or not set(targets) <= cube_ids:
            raise ValueError("BinFill 目标必须是 pick_count 个唯一方块")
        actual = {name: sum(by_id[identifier].get("color_name") == name for identifier in targets) for name in counts}
        if counts != actual:
            raise ValueError("BinFill 目标 ID 的实际颜色与目标配额不一致")
        scene_colors = {by_id[identifier].get("color_name") for identifier in cube_ids}
        if not scene_colors <= counts.keys() or len(scene_colors) != params.get("scene_color_count"):
            raise ValueError("BinFill 场景颜色数量或颜色名称与配置不一致")
        if type(params.get("dynamic")) is not bool:
            raise ValueError("BinFill dynamic 必须为布尔值")
        reveal = params.get("reveal_steps_by_id", {})
        if set(reveal) != cube_ids or any(type(step) is not int or step < 0 for step in reveal.values()):
            raise ValueError("BinFill 必须为每个方块指定非负整数出现时刻")
        interval = data["schedule"].get("dynamic_reveal_interval_steps")
        if type(interval) is not int or interval <= 0:
            raise ValueError("动态出现时间间隔必须为正整数")
        seen = dict.fromkeys(counts, 0)
        for actor in data["actors"]:
            if actor["kind"] == "cube":
                color = actor.get("color_name")
                if color not in seen or reveal[actor["id"]] != (seen[color] * interval if params["dynamic"] else 0):
                    raise ValueError("出现时刻必须与每色首次零步、之后固定间隔的规则一致")
                seen[color] += 1
    if task == "VideoRepick":
        targets = params.get("target_ids", [])
        if len(targets) != 1 or targets[0] not in cube_ids or params.get("pick_count") != params.get("repeat_count"):
            raise ValueError("VideoRepick 需要一个已声明方块且抓放次数一致")
        colors = [by_id[identifier].get("color_name") for identifier in cube_ids]
        if data["difficulty"] == "hard":
            if len(cube_ids) != 15 or any(colors.count(name) != 5 for name in ("red", "green", "blue")):
                raise ValueError("VideoRepick hard 必须是三色各五个方块")
        elif len(cube_ids) != 3 or len(set(colors)) != 1 or colors[0] not in ("red", "green", "blue"):
            raise ValueError("VideoRepick easy/medium 必须是三个同色方块")
    if task == "VideoUnmaskSwap":
        container_ids = {actor["id"] for actor in data["actors"] if actor["kind"] == "container"}
        targets = params.get("target_container_ids", [])
        if len(container_ids) != params.get("container_count") or len(container_ids) not in (3, 4) or len(cube_ids) != 3:
            raise ValueError("容器数量或藏块数量不符合任务设置")
        if len(targets) != params.get("pick_count") or len(set(targets)) != len(targets) or not set(targets) <= container_ids:
            raise ValueError("目标容器数量或引用不合法")
        empty = params.get("empty_container_id")
        if len(container_ids) == 3 and empty is not None:
            raise ValueError("三容器场景不应有空容器")
        if len(container_ids) == 4 and (empty not in container_ids or empty in targets):
            raise ValueError("四容器场景必须有一个空容器且不得作为目标")
        parents = [by_id[identifier].get("parent_id") for identifier in cube_ids]
        if set(parents) != container_ids - {empty} or len(set(parents)) != len(parents):
            raise ValueError("除空容器外，每个容器必须恰好对应一个藏块")
        if {by_id[identifier].get("color_name") for identifier in cube_ids} != {"red", "green", "blue"}:
            raise ValueError("VideoUnmaskSwap 必须包含三个不同原色的藏块")
    if task == "RouteStick":
        path, directions = params.get("path_indices", []), params.get("directions", [])
        if len(path) != params.get("walk_steps", -1) + 1 or len(directions) != len(path) - 1:
            raise ValueError("RouteStick 路径长度与游走段数不一致")
        if any(type(i) is not int or not 0 <= i < 5 for i in path):
            raise ValueError("RouteStick 目标索引必须在 0..4")
        if any(abs(a - b) != 1 for a, b in zip(path, path[1:])) or any(d not in (-1, 1) for d in directions):
            raise ValueError("RouteStick 路径或绕行方向非法")
        if type(params.get("allow_backtracking")) is not bool:
            raise ValueError("RouteStick 必须明确是否允许立即折返")
        if not params["allow_backtracking"] and any(a == c and b not in (0, 4) for a, b, c in zip(path, path[1:], path[2:])):
            raise ValueError("当前难度不允许非边界立即折返")


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    """仅保存规范 JSON 文本；嵌套列表不泄漏可变引用。"""

    _json: str

    def __post_init__(self) -> None:
        value = json.loads(self._json)
        validate_spec(value)
        object.__setattr__(self, "_json", canonical_json(value))

    @classmethod
    def from_dict(cls, value: dict) -> "EpisodeSpec":
        """序列化时校验声明哈希，防止修改清单后静默继续。"""
        value = dict(value)
        declared_hash = value.pop("spec_hash", None)
        result = cls(canonical_json(value))
        if declared_hash is not None and declared_hash != result.spec_hash:
            raise ValueError("EpisodeSpec 哈希不匹配")
        return result

    def to_dict(self) -> dict:
        value = json.loads(self._json)
        value["spec_hash"] = self.spec_hash
        return value

    @property
    def spec_hash(self) -> str:
        return hashlib.sha256(self._json.encode("utf-8")).hexdigest()

    def _get(self, key: str) -> Any:
        return json.loads(self._json)[key]

    @property
    def task_kind(self) -> str:
        return self._get("task_kind")

    @property
    def seed(self) -> int:
        return self._get("seed")

    @property
    def episode(self) -> int:
        return self._get("episode")

    @property
    def difficulty(self) -> str:
        return self._get("difficulty")

    @property
    def robot_kind(self) -> str:
        return self._get("robot_kind")

    @property
    def env_id(self) -> str:
        return self._get("env_id")

    @property
    def task_parameters(self) -> dict:
        return self._get("task_parameters")
