"""只覆盖次数和位置；所有形状、材质和任务函数仍来自原版。"""

import copy
import math

import sapien
from mani_skill.utils.structs.pose import Pose

from ..specs import EpisodeSpec
from ..errors import SceneRejected
from ..validation.geometry import actual_boxes
from .imports import build_bin, build_board_with_hole, build_button, spawn_random_cube


def initialize_parameters(env, spec):
    env.episode_spec = (
        spec if isinstance(spec, EpisodeSpec) else EpisodeSpec.from_dict(spec)
    )
    env.native_task_id = env.episode_spec.task_kind
    env.parameters = env.episode_spec.parameters
    env.configs = copy.deepcopy(env.configs)
    return env.parameters


def runtime_options(spec, render_gpu):
    if type(render_gpu) is not int or render_gpu < 0:
        raise ValueError("render_gpu 必须为非负物理GPU编号")
    return dict(
        seed=spec.seed,
        difficulty=spec.difficulty,
        num_envs=1,
        obs_mode="rgb+depth+segmentation",
        control_mode="pd_joint_pos",
        render_mode="rgb_array",
        sim_backend="physx_cpu",
        render_backend=f"cuda:{render_gpu}",
        reward_mode="dense",
    )


class NativePlacements:
    """分层分位数在原版实际素材的合法中心区间内解析，不另定义几何。"""

    def __init__(self, spec):
        definition = spec.to_dict()
        self.positions = definition["placements"]
        self.layout = definition["layout"]
        self.indices = {}

    def next(self, kind):
        index = self.indices.get(kind, 0)
        positions = self.positions.get(kind, [])
        if index >= len(positions):
            raise ValueError(f"原版请求的 {kind} 数量超过冻结布局")
        self.indices[kind] = index + 1
        if kind in ("button", "board"):
            key = kind
        elif kind == "cubes" and self.layout["topology"] == "field":
            key = f"cube_{index}"
        else:
            key = f"{kind}_{index}"
        return positions[index], self.layout["supports"][key]

    @property
    def route_center(self):
        return self.layout["center"]

    @property
    def route_spacing(self):
        return self.layout["spacing"]

    @property
    def route_angle(self):
        return math.radians(self.layout["yaw_degrees"])

    @staticmethod
    def center(point, bounds):
        return [
            bounds[axis][0]
            + point[f"{axis}_fraction"] * (bounds[axis][1] - bounds[axis][0])
            for axis in ("x", "y")
        ]

    @staticmethod
    def fit_actor(actor, point, bounds):
        """使用实际碰撞形状的旋转投影求合法区间，再映射分位数。"""
        parts = actual_boxes(actor)
        pose = actor.pose.sp
        center = list(pose.p)
        for index, axis in enumerate(("x", "y")):
            direction = (1, 0, 0) if index == 0 else (0, 1, 0)
            low_offset = (
                min(box.center[index] - box.radius_on(direction) for box in parts)
                - center[index]
            )
            high_offset = (
                max(box.center[index] + box.radius_on(direction) for box in parts)
                - center[index]
            )
            low = bounds[axis][0] - low_offset
            high = bounds[axis][1] - high_offset
            if low > high:
                raise SceneRejected(f"{actor.name} 的原版素材无法放入配置{axis}窗口")
            center[index] = low + point[f"{axis}_fraction"] * (high - low)
        resolved = sapien.Pose(center, pose.q)
        actor.initial_pose = Pose.create(resolved)
        actor.set_pose(resolved)
        return actor

    def build_button(self, env, **kwargs):
        point, bounds = self.next("button")
        kwargs.update(center_xy=self.center(point, bounds), randomize=False)
        return build_button(env, **kwargs)

    def build_board(self, env, **kwargs):
        point, bounds = self.next("board")
        angle = math.radians(point["yaw_degrees"]) / 2
        kwargs.update(
            position=[*self.center(point, bounds), 0.0],
            rotation_quat=[math.cos(angle), 0.0, 0.0, math.sin(angle)],
        )
        return build_board_with_hole(env, **kwargs)

    def spawn_cube(self, env, **kwargs):
        point, bounds = self.next("cubes")
        half_size = float(kwargs.get("half_size", 0.01))
        provisional = [sum(bounds[axis]) / 2 for axis in ("x", "y")]
        # 构建时仍调用原版工具，随后用其实际形状解析最终位置；期间不推进物理。
        kwargs.update(
            region_center=provisional,
            region_half_size=[half_size + 1e-9] * 2,
            avoid=[],
            include_existing=False,
            include_goal=False,
            min_gap=0.0,
            max_trials=1,
        )
        cube = spawn_random_cube(env, **kwargs)
        angle = math.radians(point["yaw_degrees"]) / 2
        cube.set_pose(
            sapien.Pose(
                [*provisional, half_size], [math.cos(angle), 0.0, 0.0, math.sin(angle)]
            )
        )
        return self.fit_actor(cube, point, bounds)

    def spawn_bin(self, env, **kwargs):
        point, bounds = self.next("containers")
        provisional = [sum(bounds[axis]) / 2 for axis in ("x", "y")]
        actor = build_bin(
            env,
            callsign=kwargs.get("name_prefix", "bin"),
            position=[*provisional, 0.002],
            z_rotation_deg=point["yaw_degrees"],
        )
        return self.fit_actor(actor, point, bounds)
