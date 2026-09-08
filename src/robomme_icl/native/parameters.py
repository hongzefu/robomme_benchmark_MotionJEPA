"""只覆盖次数和位置；所有形状、材质和任务函数仍来自原版。"""

import copy
import math

import numpy as np
import sapien

from ..specs import EpisodeSpec
from .imports import build_bin, build_board_with_hole, build_button, spawn_random_cube


def initialize_parameters(env, spec):
    env.episode_spec = spec if isinstance(spec, EpisodeSpec) else EpisodeSpec.from_dict(spec)
    env.native_task_id = env.episode_spec.task_kind
    env.parameters = env.episode_spec.parameters
    env.configs = copy.deepcopy(env.configs)
    return env.parameters


def runtime_options(spec, render_gpu):
    if type(render_gpu) is not int or render_gpu < 0:
        raise ValueError("render_gpu 必须为非负物理GPU编号")
    return dict(seed=spec.seed, difficulty=spec.difficulty, num_envs=1,
                obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                render_mode="rgb_array", sim_backend="physx_cpu",
                render_backend=f"cuda:{render_gpu}", reward_mode="dense")


class NativePlacements:
    """按原版构建顺序消费固定布局；不决定颜色、目标或交换角色。"""

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
        return positions[index]

    @property
    def route_center(self):
        return self.layout["center"]

    @property
    def route_spacing(self):
        return self.layout["spacing"]

    @property
    def route_angle(self):
        return math.radians(self.layout["yaw_degrees"])

    def build_button(self, env, **kwargs):
        point = self.next("button")
        kwargs.update(center_xy=(point["x"], point["y"]), randomize=False)
        return build_button(env, **kwargs)

    def build_board(self, env, **kwargs):
        point = self.next("board")
        angle = math.radians(point["yaw_degrees"]) / 2
        kwargs.update(position=[point["x"], point["y"], 0.],
                      rotation_quat=[math.cos(angle), 0., 0., math.sin(angle)])
        return build_board_with_hole(env, **kwargs)

    def spawn_cube(self, env, **kwargs):
        point = self.next("cubes")
        half_size = float(kwargs.get("half_size", .01))
        # 固定中心仍调用原版方块构建器；候选几何检查统一放在验证层。
        kwargs.update(region_center=[point["x"], point["y"]], region_half_size=[half_size + 1e-9] * 2,
                      avoid=[], include_existing=False, include_goal=False, min_gap=0., max_trials=1)
        cube = spawn_random_cube(env, **kwargs)
        angle = math.radians(point["yaw_degrees"]) / 2
        cube.set_pose(sapien.Pose([point["x"], point["y"], half_size],
                                 [math.cos(angle), 0., 0., math.sin(angle)]))
        return cube

    def spawn_bin(self, env, **kwargs):
        point = self.next("containers")
        return build_bin(env, callsign=kwargs.get("name_prefix", "bin"),
                         position=[point["x"], point["y"], .002],
                         z_rotation_deg=point["yaw_degrees"])
