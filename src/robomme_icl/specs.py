"""版本2场景只冻结分布输入，原版行为的实测快照由记录器保存。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import TypedDict

from .config import DIFFICULTIES, TASKS, TASK_FIELDS

NATIVE_REFERENCE = "76ae12bf1e71f79e1c3f608eede10ac7430b406f"
COMPILER_VERSION = "2.0.0"


@dataclass(frozen=True)
class BinFillParameters:
    pick_count: int
    spawn_count: int
    target_color_count: int
    scene_color_count: int
    dynamic: bool


@dataclass(frozen=True)
class RouteStickParameters:
    walk_steps: int
    allow_backtracking: bool


@dataclass(frozen=True)
class VideoUnmaskSwapParameters:
    container_count: int
    pick_count: int
    swap_count: int


@dataclass(frozen=True)
class VideoRepickParameters:
    spawn_count: int
    repeat_count: int
    swap_count: int


PARAMETER_TYPES = dict(
    zip(
        TASKS,
        (
            BinFillParameters,
            RouteStickParameters,
            VideoUnmaskSwapParameters,
            VideoRepickParameters,
        ),
    )
)


class PlacementSample(TypedDict):
    """在原版实际几何决定的合法中心区间内，固定两个分层分位数。"""

    x_fraction: float
    y_fraction: float
    yaw_degrees: float


class FrameRecord(TypedDict):
    observation: dict
    joint_action: object
    info: dict


def canonical_json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    """用规范JSON保存不可变嵌套数据；访问返回独立副本。"""

    _json: str

    def __post_init__(self):
        value = json.loads(self._json)
        expected = {
            "schema_version",
            "task_kind",
            "seed",
            "episode",
            "difficulty",
            "robot_kind",
            "env_id",
            "task_parameters",
            "placements",
            "layout",
            "provenance",
        }
        if set(value) != expected or value["schema_version"] != 2:
            raise ValueError("仅接受版本2场景；旧素材／时序清单必须重新编译认证")
        task = value["task_kind"]
        if task not in TASKS or value["difficulty"] not in DIFFICULTIES:
            raise ValueError("任务或难度非法")
        for key in ("seed", "episode"):
            if type(value[key]) is not int or value[key] < 0:
                raise ValueError(f"{key} 必须为非负整数")
        if value["seed"] >= 2**31:
            raise ValueError("seed 超出32位范围")
        robot = "panda_stick" if task == "RouteStick" else "panda_wristcam"
        if value["robot_kind"] != robot or value["env_id"] != f"RoboMME-ICL/{task}-v0":
            raise ValueError("机器人、任务与注册ID不匹配")
        parameters = value["task_parameters"]
        if set(parameters) != TASK_FIELDS[task]:
            raise ValueError("任务参数字段不匹配")
        for key, number in parameters.items():
            if key in ("dynamic", "allow_backtracking"):
                valid = type(number) is bool
            else:
                valid = type(number) is int and number >= (
                    0 if key == "swap_count" else 1
                )
            if not valid:
                raise ValueError(f"任务参数 {key} 非法")
        asdict(PARAMETER_TYPES[task](**parameters))
        if value["provenance"].get("native_reference") != NATIVE_REFERENCE:
            raise ValueError("原版来源不是固定对照版本")
        for placements in value["placements"].values():
            if not isinstance(placements, list):
                raise ValueError("位置组必须为列表")
            for point in placements:
                if set(point) != {"x_fraction", "y_fraction", "yaw_degrees"} or any(
                    type(x) not in (float, int) or not math.isfinite(x)
                    for x in point.values()
                ):
                    raise ValueError(
                        "位置须含有限分位数x_fraction/y_fraction和yaw_degrees"
                    )
                if (
                    not 0 <= point["x_fraction"] <= 1
                    or not 0 <= point["y_fraction"] <= 1
                ):
                    raise ValueError("位置分位数必须位于[0,1]")
        if value["layout"].get("coordinate_mode") != "native_support_fraction":
            raise ValueError("位置协议不同，请按当前原版几何重新编译认证")
        object.__setattr__(self, "_json", canonical_json(value))

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        declared = value.pop("spec_hash", None)
        result = cls(canonical_json(value))
        if declared is not None and declared != result.spec_hash:
            raise ValueError("EpisodeSpec 哈希不匹配")
        return result

    def to_dict(self):
        return {**json.loads(self._json), "spec_hash": self.spec_hash}

    @property
    def spec_hash(self):
        return hashlib.sha256(self._json.encode()).hexdigest()

    def _get(self, key):
        return json.loads(self._json)[key]

    @property
    def task_kind(self):
        return self._get("task_kind")

    @property
    def seed(self):
        return self._get("seed")

    @property
    def episode(self):
        return self._get("episode")

    @property
    def difficulty(self):
        return self._get("difficulty")

    @property
    def robot_kind(self):
        return self._get("robot_kind")

    @property
    def env_id(self):
        return self._get("env_id")

    @property
    def task_parameters(self):
        return self._get("task_parameters")

    @property
    def parameters(self):
        return PARAMETER_TYPES[self.task_kind](**self.task_parameters)
