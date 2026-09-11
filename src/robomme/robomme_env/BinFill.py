import copy
from typing import Any, Dict, Union

import numpy as np
import sapien
import torch

import mani_skill.envs.utils.randomization as randomization
from mani_skill.agents.robots import SO100, Fetch, Panda
from mani_skill.envs.sapien_env import BaseEnv
from mani_skill.envs.tasks.tabletop.pick_cube_cfgs import PICK_CUBE_CONFIGS
from mani_skill.sensors.camera import CameraConfig
from mani_skill.utils import sapien_utils
from mani_skill.utils.building import actors
from mani_skill.utils.registration import register_env
from mani_skill.utils.scene_builder.table import TableSceneBuilder
from mani_skill.utils.structs.pose import Pose
from mani_skill.utils.structs import Actor, Link
#Robomme
import matplotlib.pyplot as plt
import random
from mani_skill.utils.geometry.rotation_conversions import (
    euler_angles_to_matrix,
    matrix_to_quaternion,
)
from .utils import *
from .utils.subgoal_evaluate_func import static_check
from .utils.object_generation import spawn_fixed_cube, build_board_with_hole
from .utils import reset_panda
from .utils import subgoal_language
from .utils.difficulty import normalize_robomme_difficulty

from ..logging_utils import logger


# ── 原版采样输入的原值快照（newtask-v2 10.0）────────────────────────────────────
# 本字典就是不传 sampling_config 时的运行默认值，同时也是
# `scripts/generate_dataset_newseed.py --extract-config` 的 AST 提取目标，
# 因此「提取到的原值」与「实际跑的默认值」永远是同一处，不存在双真值。
# 难度字典不在这里重复，仍以类属性 config_easy / config_medium / config_hard 为准。
# 表达式与来源说明字段只作核查用，运行时不消费。
NATIVE_SAMPLING = {
    "parameters": {
        "dynamic": {
            "sampler": "torch.randint",
            "low": 0,
            "high_exclusive": 2,
            "shape": [1],
            "cast": "bool",
        },
    },
    "positions": {
        "button": {
            "center_xy": [-0.2, 0],
            "randomize": True,
            "randomize_range": [0.1, 0.4],
            "sampling_expression": "(torch.rand(2, generator=generator) - 0.5) * randomize_range",
            "scale": 1.5,
            "randomize_range_origin": "原值取自 build_button 形参默认值；原调用点未传，现由本快照显式传入",
        },
        "board": {
            "base_position": [0.15, 0, 0],
            "x_offset": {"scale": 0.2, "subtract": 0.2},
            "y_offset": {"scale": 0.4, "subtract": 0.2},
            "yaw_deg": {"scale": 40, "subtract": 20},
            "x_expression": "0.15 + (u * 0.2 - 0.2)",
            "y_expression": "u * 0.4 - 0.2",
            "yaw_expression": "u * 40.0 - 20.0",
            "board_side": 0.1,
            "hole_side": 0.08,
            "thickness": 0.05,
            "consumer": "build_board_with_hole 只是位置接收方，内部无随机",
        },
        "cubes": {
            "region_center": [-0.1, 0],
            "region_half_size": [0.2, 0.25],
            "random_yaw": True,
            "yaw_range_rad": [0, 6.283185307179586],
            "yaw_expression": "yaw_sample * 2 * np.pi",
            "min_gap": "self.cube_half_size",
            "min_gap_value": 0.02,
            "include_existing": False,
            "include_goal": False,
            "rng_per_trial": ["x", "y", "yaw"],
        },
    },
}


def _resolve_sampling_config(cls, override):
    """准备本实例专属的采样配置副本。

    只做取值、字段校验与深拷贝：全程不调用任何随机数，且必须在 torch.Generator()
    创建之前完成 —— 在这里多抽或少抽一次会平移其后全部取值。
    gymnasium 会把 kwargs 字典的引用存进 env.unwrapped.spec.kwargs，
    因此独立副本只能由这里的 deepcopy 保证。
    """
    if override is None:
        resolved = copy.deepcopy(NATIVE_SAMPLING)
    else:
        if not isinstance(override, dict) or set(override) != {"parameters", "positions"}:
            raise ValueError("sampling_config 必须是只含 parameters 与 positions 的字典")
        resolved = copy.deepcopy(override)
    resolved["parameters"].setdefault("configs", copy.deepcopy(cls.configs))
    return resolved


def _actor_xyz(actor):
    """只读取 actor 当前世界位置，供注入证据用；不改状态、不抽随机数。"""
    pos = actor.pose.p if hasattr(actor, "pose") else actor.get_pose().p
    if isinstance(pos, torch.Tensor):
        pos = pos.detach().cpu().numpy()
    return [float(v) for v in np.asarray(pos).reshape(-1)[:3]]


def _actor_quat(actor):
    """只读取 actor 当前世界朝向（wxyz）。"""
    quat = actor.pose.q if hasattr(actor, "pose") else actor.get_pose().q
    if isinstance(quat, torch.Tensor):
        quat = quat.detach().cpu().numpy()
    return [float(v) for v in np.asarray(quat).reshape(-1)[:4]]


def _resolve_episode_spec(spec, task):
    """准备本实例专属的固定规格副本（新值注入）。

    与 :func:`_resolve_sampling_config` 同样的道理：gymnasium 会把 kwargs 字典的引用存进
    ``env.unwrapped.spec.kwargs``，两次初始化又要各自从规格重建工作态，所以这里必须
    deepcopy 出一份独立副本，任务内只改这份工作态，绝不碰调用方传进来的原对象。

    传 ``None``（即没传 ``--episode-specs``）时返回 ``None``，之后每个消费点都走原随机
    路径，链路与改动前逐字相同——``DEFAULT_PARITY`` 靠的就是这一条。
    """
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise ValueError("episode_spec 必须是字典")
    if spec.get("task") != task:
        raise ValueError(f"episode_spec 是 {spec.get('task')} 的规格，不能用于 {task}")
    return copy.deepcopy(spec)


@register_env("BinFill")
class BinFill(BaseEnv):

    _sample_video_link = "https://github.com/haosulab/ManiSkill/raw/main/figures/environment_demos/PickCube-v1_rt.mp4"
    SUPPORTED_ROBOTS = [
        "panda",
        "fetch",
        "xarm6_robotiq",
        "so100",
        "widowxai",
    ]
    agent: Union[Panda]
    goal_thresh = 0.025
    cube_spawn_half_size = 0.05
    cube_spawn_center = (0, 0)

    # config_hard = {
    # 'color': 3, 
    # 'spawn_cubes':4,
    #     "put_in_color":3,
    # }

    # config_easy = {
    #     'color': 1, 
    # 'spawn_cubes':8,
    #     "put_in_color":1,
    # }

    # config_medium = {
    #     'color': 3, 
    # 'spawn_cubes':4,
    #     "put_in_color":1,
    # }

    config_easy = {
    'color': 1, 
    'spawn_cubes':[4,6],
    "put_in_color":[1,1],
    "put_in_numbers":[1,3]
    }

    config_medium = {
    'color': 2, 
    'spawn_cubes':[8,10],
    "put_in_color":[1,2],
    "put_in_numbers":[2,4]
    }


    config_hard = {
    'color': 3, 
    'spawn_cubes':[10,12],
    "put_in_color":[2,3],
    "put_in_numbers":[3,5]
    }




    # Combine into a dictionary
    configs = {
        'hard': config_hard,
        'easy': config_easy,
        'medium': config_medium
    }

    def __init__(self, *args, robot_uids="panda_wristcam", robot_init_qpos_noise=0,seed=0,Robomme_video_episode=None,Robomme_video_path=None,
                     sampling_config=None,
                     episode_spec=None,
                     **kwargs):
        # 必须落在任何随机数调用与 super().__init__() 之前
        self._sampling = _resolve_sampling_config(type(self), sampling_config)
        self._episode_spec = _resolve_episode_spec(episode_spec, "BinFill")
        # 注入生效的只读证据，供对拍观察器核对「创建输入 vs 创建后位姿」
        self._injection_evidence = {}
        self.robot_init_qpos_noise = robot_init_qpos_noise
        self.use_demonstrationwrapper=False
        self.demonstration_record_traj=False
        normalized_robomme_difficulty = normalize_robomme_difficulty(
            kwargs.pop("difficulty", None)
        )
        self.robomme_failure_recovery = bool(
            kwargs.pop("robomme_failure_recovery", False)
        )
        self.robomme_failure_recovery_mode = kwargs.pop(
            "robomme_failure_recovery_mode", None
        )
        if isinstance(self.robomme_failure_recovery_mode, str):
            self.robomme_failure_recovery_mode = self.robomme_failure_recovery_mode.lower()

        if normalized_robomme_difficulty is not None:
            self.difficulty = normalized_robomme_difficulty
        else:
            # Determine difficulty based on seed % 3
            seed_mod = seed % 3
            if seed_mod == 0:
                self.difficulty = "easy"
            elif seed_mod == 1:
                self.difficulty = "medium"
            else:  # seed_mod == 2
                self.difficulty = "hard"
        #self.difficulty = "hard"

        if robot_uids in PICK_CUBE_CONFIGS:
            cfg = PICK_CUBE_CONFIGS[robot_uids]
        else:
            cfg = PICK_CUBE_CONFIGS["panda"]
        self.cube_half_size = cfg["cube_half_size"]
        self.goal_thresh = cfg["goal_thresh"]
        self.cube_spawn_half_size = cfg["cube_spawn_half_size"]
        self.cube_spawn_center = cfg["cube_spawn_center"]
        self.max_goal_height = cfg["max_goal_height"]
        self.sensor_cam_eye_pos = cfg["sensor_cam_eye_pos"]
        self.sensor_cam_target_pos = cfg["sensor_cam_target_pos"]
        self.human_cam_eye_pos = cfg["human_cam_eye_pos"]
        self.human_cam_target_pos = cfg["human_cam_target_pos"]

        self.seed = seed
        self.generator = torch.Generator()
        self.generator.manual_seed(seed)
        dynamic_cfg = self._sampling["parameters"]["dynamic"]
        if self._episode_spec is None:
            self.dynamic=bool(torch.randint(dynamic_cfg["low"], dynamic_cfg["high_exclusive"], tuple(dynamic_cfg["shape"]), generator=self.generator).item())
        else:
            # 规格定死 dynamic：不抽这一次 randint。开启态不要求随机流位置与原版对齐——
            # 凡规格覆盖的量都由规格决定，规格没覆盖的量（如 inject_fail_grasp）继续用
            # self.generator，取值会因流位置平移而与原版不同，这些量不在验收范围内。
            self.dynamic=bool(self._episode_spec["layout"]["dynamic"])

        # Track the color order and counts used to describe the language goal.
        self.binfill_language_sequence = []

        super().__init__(*args, robot_uids=robot_uids, **kwargs)

    @property
    def _default_sensor_configs(self):
        pose = sapien_utils.look_at(
            eye=self.sensor_cam_eye_pos, target=self.sensor_cam_target_pos
        )
        camera_eye=[0.3,0,0.4]
        camera_target =[0,0,-0.2]
        pose = sapien_utils.look_at(
            eye=camera_eye, target=camera_target
        )
        return [CameraConfig("base_camera", pose, 256, 256, np.pi / 2, 0.01, 100)]

    @property
    def _default_human_render_camera_configs(self):
        pose = sapien_utils.look_at(
            eye=self.human_cam_eye_pos, target=self.human_cam_target_pos
        )
        camera_eye=[1,0,0.4]
        camera_target =[0,0,0.4]
        pose = sapien_utils.look_at(
            eye=camera_eye, target=camera_target
        )

        return CameraConfig("render_camera", pose, 512, 512, 1, 0.01, 100)

    def _load_agent(self, options: dict):
        super()._load_agent(options, sapien.Pose(p=[-0.615, 0, 0]))

    def _load_scene(self, options: dict):
        self.table_scene = TableSceneBuilder(
            self, robot_init_qpos_noise=self.robot_init_qpos_noise
        )
        self.table_scene.build()

        # Create generator for all randomization
        generator = self.generator

        spec = self._episode_spec
        button_cfg = self._sampling["positions"]["button"]
        if spec is None:
            button_obb = build_button(
                self,
                center_xy=tuple(button_cfg["center_xy"]),
                scale=button_cfg["scale"],
                generator=generator,
                randomize=button_cfg["randomize"],
                randomize_range=tuple(button_cfg["randomize_range"]),
            )
        else:
            # 规格给的是**最终**中心；关掉 randomize 后 build_button 不抽随机数，
            # 其余（缩放、travel、连杆、OBB）全走原路径
            button_obb = build_button(
                self,
                center_xy=tuple(spec["layout"]["button_xy"]),
                scale=button_cfg["scale"],
                generator=generator,
                randomize=False,
                randomize_range=tuple(button_cfg["randomize_range"]),
            )
        avoid = [button_obb]

        # Create square board with square hole
        board_cfg = self._sampling["positions"]["board"]
        board_x = board_cfg["x_offset"]
        board_y = board_cfg["y_offset"]
        board_yaw = board_cfg["yaw_deg"]
        board_base = board_cfg["base_position"]
        if spec is None:
            x_var = torch.rand(1, generator=generator).item() * board_x["scale"] - board_x["subtract"]  # [-0.25, 0.25]
            y_var = torch.rand(1, generator=generator).item() * board_y["scale"] - board_y["subtract"]  # [-0.25, 0.25]
            z_rot_deg = (torch.rand(1, generator=generator).item() * board_yaw["scale"] - board_yaw["subtract"])  # [-20, 20] degrees
        else:
            # 规格存的是最终位置，这里反解回原公式里的偏移量，位置计算仍走下面同一行
            board_spec = spec["layout"]["board"]
            x_var = float(board_spec["xy"][0]) - float(board_base[0])
            y_var = float(board_spec["xy"][1]) - float(board_base[1])
            z_rot_deg = float(board_spec["yaw_deg"])
        z_rot_rad = torch.deg2rad(torch.tensor(z_rot_deg))
        # Create rotation quaternion for z-axis rotation
        rot_mat = euler_angles_to_matrix(torch.tensor([[0.0, 0.0, z_rot_rad]]), convention="XYZ")
        rot_quat = matrix_to_quaternion(rot_mat)[0]  # [w, x, y, z]
        self.board_with_hole = build_board_with_hole(
            self,
            board_side=board_cfg["board_side"],  # Side length of square board
            hole_side=board_cfg["hole_side"],   # Side length of square hole, slightly larger than cube for passing
            thickness=board_cfg["thickness"],   # Board thickness
            position=[float(board_base[0]) + x_var, float(board_base[1]) + y_var, float(board_base[2])],  # Board position
            rotation_quat=rot_quat.tolist(),  # z-axis rotation
            name="board_with_hole"
        )
        avoid += [self.board_with_hole]

        ###
        ###
        ###
        ###
        ###
        # First generate target_number (put_in):
        # If put_in_color == 1: Randomly select a color, assign target count in range [put_in_range[0], put_in_range[1]]
        # If put_in_color == 3:
            # First generate total target count total_target from put_in_range
            # Start from [0, 0, 0], randomly distribute to three colors (no requirement for min 1 per color)

        # Then generate spawn_number:
        # If num_colors == 1: Only the color with target will spawn cube, spawn count = max(total_spawn, target count)
        # If num_colors == 3: Spawn count for each color at least equals target, remaining spawn count distributed randomly
        # This ensures spawn >= target for each color.


        # Get configuration for current difficulty
        config = self._sampling["parameters"]["configs"][self.difficulty]
        num_colors = config['color']  # 1 or 3
        spawn_range = config['spawn_cubes']  # [min, max]
        put_in_color_range = config['put_in_color']
        spec_counts = None
        if spec is not None:
            # 规格直接定死每色的生成数与目标数，下面整段配额抽样一次随机数都不走
            order = ["red", "blue", "green"]
            spec_counts = (
                [int(spec["objects"]["spawn_count"].get(name, 0)) for name in order],
                [int(spec["objects"]["target_count"].get(name, 0)) for name in order],
            )
        color_pool = torch.randperm(3, generator=generator).tolist()[:num_colors]
        put_in_color = torch.randint(
            put_in_color_range[0], put_in_color_range[1] + 1, (1,), generator=generator
        ).item()
        put_in_color = max(1, min(3, put_in_color))
        put_in_color = min(put_in_color, max(1, num_colors))
        active_color_indices = color_pool[:put_in_color]
        put_in_range = config['put_in_numbers']  # [min, max]

        # First generate target_number (put_in)
        target_numbers = [0, 0, 0]
        if spec_counts is not None:
            spawn_numbers, target_numbers = list(spec_counts[0]), list(spec_counts[1])
        elif put_in_color == 1:
            # Only one color needs to be put in bin
            selected_idx = active_color_indices[0]
            target_numbers[selected_idx] = torch.randint(put_in_range[0], put_in_range[1] + 1, (1,), generator=generator).item()
        else:
            # All 3 colors need to be put in bin, generate total number first then distribute
            total_target = torch.randint(put_in_range[0], put_in_range[1] + 1, (1,), generator=generator).item()
            # Randomly distribute target number to three colors
            for _ in range(total_target):
                idx = torch.randint(0, len(active_color_indices), (1,), generator=generator).item()
                target_numbers[active_color_indices[idx]] += 1

        self.red_cubes_target_number = target_numbers[0]
        self.blue_cubes_target_number = target_numbers[1]
        self.green_cubes_target_number = target_numbers[2]

        # Then generate spawn_number, ensure spawn >= target
        if spec_counts is not None:
            total_spawn = sum(spawn_numbers)
        else:
            total_spawn = torch.randint(spawn_range[0], spawn_range[1] + 1, (1,), generator=generator).item()

        if spec_counts is not None:
            pass  # spawn_numbers 已由规格定死
        elif num_colors == 1:
            # Only one color has cube, choose the one with target (if none, use first color in color_pool)
            spawn_numbers = [0, 0, 0]
            active_idx = next((i for i in color_pool if target_numbers[i] > 0), color_pool[0])
            # Spawn number at least equals target number
            spawn_numbers[active_idx] = max(total_spawn, target_numbers[active_idx])
        else:
            # num_colors controls 1/2/3 colors: ensure each selected color has at least 1 spawn, and spawn >= target
            spawn_numbers = [0, 0, 0]
            for i in color_pool:
                spawn_numbers[i] = max(target_numbers[i], 1)
            used_spawn = sum(spawn_numbers[i] for i in color_pool)
            remaining = total_spawn - used_spawn
            # Randomly distribute remaining spawn count
            for _ in range(max(0, remaining)):
                idx = torch.randint(0, len(color_pool), (1,), generator=generator).item()
                spawn_numbers[color_pool[idx]] += 1

        self.red_cubes_spawn_number = spawn_numbers[0]
        self.blue_cubes_spawn_number = spawn_numbers[1]
        self.green_cubes_spawn_number = spawn_numbers[2]

        logger.debug(f"Target numbers - Red: {self.red_cubes_target_number}, Blue: {self.blue_cubes_target_number}, Green: {self.green_cubes_target_number}")
        logger.debug(f"Spawn numbers - Red: {self.red_cubes_spawn_number}, Blue: {self.blue_cubes_spawn_number}, Green: {self.green_cubes_spawn_number}")

        ###
        ###
        ###
        ###
        ###
        self.all_cubes = []
        self.red_cubes, self.blue_cubes, self.green_cubes = [], [], []

        color_info = [
            {"color": (1, 0, 0, 1), "name": "red", "list": self.red_cubes, "spawn_num": self.red_cubes_spawn_number},
            {"color": (0, 0, 1, 1), "name": "blue", "list": self.blue_cubes, "spawn_num": self.blue_cubes_spawn_number},
            {"color": (0, 1, 0, 1), "name": "green", "list": self.green_cubes, "spawn_num": self.green_cubes_spawn_number}
        ]

        # Generate task list for all cubes and shuffle order
        cube_tasks = []
        for info in color_info:
            for idx in range(info["spawn_num"]):
                cube_tasks.append({"color": info["color"], "name": info["name"], "list": info["list"], "idx": idx})

        if spec is None:
            # Shuffle generation order
            shuffle_order = torch.randperm(len(cube_tasks), generator=generator).tolist()
            cube_tasks = [cube_tasks[i] for i in shuffle_order]
        else:
            # 规格的 cubes 列表本身就是生成顺序，直接按它重排并挂上固定位姿；
            # 名字仍由 name_prefix=f"cube_{名}_{序号}" 拼出，与规格里的 object_id 一致
            by_identity = {(item["name"], item["idx"]): item for item in cube_tasks}
            ordered = []
            for entry in spec["layout"]["cubes"]:
                key = (entry["color"], int(entry["color_index"]))
                if key not in by_identity:
                    raise ValueError(f"规格里的 {entry['object_id']} 不在按 spawn_count 展开的任务列表里")
                task = dict(by_identity[key])
                task["fixed_xy"] = [float(entry["xy"][0]), float(entry["xy"][1])]
                task["fixed_yaw"] = float(entry["yaw_rad"])
                ordered.append(task)
            if len(ordered) != len(cube_tasks):
                raise ValueError(
                    f"规格给了 {len(ordered)} 块方块，spawn_count 展开是 {len(cube_tasks)} 块"
                )
            cube_tasks = ordered

        # Spawn cubes in shuffled order
        cubes_cfg = self._sampling["positions"]["cubes"]
        for task in cube_tasks:
            try:
                cube = spawn_random_cube(
                    self, color=task["color"], avoid=avoid,
                    include_existing=cubes_cfg["include_existing"], include_goal=cubes_cfg["include_goal"],
                    region_center=list(cubes_cfg["region_center"]), region_half_size=list(cubes_cfg["region_half_size"]),
                    half_size=self.cube_half_size, min_gap=self.cube_half_size,
                    random_yaw=cubes_cfg["random_yaw"], name_prefix=f"cube_{task['name']}_{task['idx']}",
                    generator=generator,
                    fixed_xy=task.get("fixed_xy"), fixed_yaw=task.get("fixed_yaw"),
                )
                self.all_cubes.append(cube)
                task["list"].append(cube)
                avoid.append(cube)
            except RuntimeError as e:
                logger.debug(f"Failed to spawn {task['name']} cube {task['idx']}: {e}")

        logger.debug(f"Generated {len(self.all_cubes)} cubes total (red: {len(self.red_cubes)}, blue: {len(self.blue_cubes)}, green: {len(self.green_cubes)})")

        if spec is not None:
            # 只读证据：记录「创建输入 vs 创建后 actor 实际位姿」，供 INJECTION_BINDING 核对。
            # 这里只读位姿，不改任何状态、不抽随机数。
            self._injection_evidence = {
                "spec_sha256": spec.get("spec_sha256"),
                "episode": spec.get("episode"),
                "button_xy": [float(v) for v in spec["layout"]["button_xy"]],
                "board": dict(spec["layout"]["board"]),
                "spawn_count": dict(spec["objects"]["spawn_count"]),
                "target_count": dict(spec["objects"]["target_count"]),
                "cubes": [
                    {
                        "object_id": entry["object_id"],
                        "requested_xy": [float(v) for v in entry["xy"]],
                        "requested_yaw_rad": float(entry["yaw_rad"]),
                        "actual_p": _actor_xyz(cube),
                        "actual_q": _actor_quat(cube),
                    }
                    for entry, cube in zip(spec["layout"]["cubes"], self.all_cubes)
                ],
            }




    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        with torch.device(self.device):
            b = len(env_idx)
            self.table_scene.initialize(env_idx)
            qpos=reset_panda.get_reset_panda_param("qpos")
            self.agent.reset(qpos)

            tasks=[]
            self.red_cubes_in_bin=0
            self.blue_cubes_in_bin=0
            self.green_cubes_in_bin=0
            self.binfill_language_sequence = []
            color_task_definitions = [
                ("blue", self.blue_cubes, self.blue_cubes_target_number),
                ("red", self.red_cubes, self.red_cubes_target_number),
                ("green", self.green_cubes, self.green_cubes_target_number),
            ]
            if self._episode_spec is None:
                color_order = torch.randperm(len(color_task_definitions), generator=self.generator).tolist()
            else:
                # 规格的 initialize_color_order 直接定死定义表 (blue, red, green) 的遍历顺序，
                # 替代源码这次 randperm。两次初始化都从同一份规格重建，不复用上一次的结果。
                names = [item[0] for item in color_task_definitions]
                color_order = [names.index(name) for name in self._episode_spec["objects"]["initialize_color_order"]]
            for color_idx in color_order:
                color_name, cube_collection, target_number = color_task_definitions[color_idx]
                if target_number <= 0:
                    continue
                self.binfill_language_sequence.append((color_name, target_number))
                for i in range(target_number):
                    cube = cube_collection[i]
                    tasks.append({
                        "func": lambda c=self.all_cubes: is_any_obj_pickup_flag_currentpickup(self,objects=c),
                        "name": subgoal_language.get_subgoal_with_index(i, "pick up the {idx} {color} cube", color=color_name),
                        "subgoal_segment": subgoal_language.get_subgoal_with_index(i, "pick up the {idx} {color} cube at <>", color=color_name),
                        "choice_label": "pick up the cube",
                        "demonstration": False,
                        "failure_func":  lambda:is_button_pressed(self, obj=self.button),
                        "solve": lambda env, planner, c=cube: solve_pickup(env, planner, obj=c),
                        "segment":[cube_collection[i]]
                    })
                    tasks.append({
                        "func": lambda c=self.all_cubes: is_any_obj_dropped_onto_delete(self, objects=c, target=self.board_with_hole),
                        "name": f"put it into the bin",
                        "subgoal_segment":"put it into the bin at <>",
                        "choice_label": "put it into the bin",
                        "demonstration": False,
                        "failure_func":  lambda:is_button_pressed(self, obj=self.button),
                        "solve": lambda env, planner, c=cube: [
                            solve_putonto_whenhold_binspecial(env, planner, target=self.board_with_hole),
                        ],
                        "segment":[self.board_with_hole]
                    })
            tasks.append({
                "func": lambda: is_button_pressed(self, obj=self.button),
                "name": "press the button",
                "subgoal_segment":"press the button at <>",
                "choice_label": "press the button",
                "demonstration": False,
                "failure_func":lambda  c=self.all_cubes:[not check_in_bin_number(self,in_bin_list= [self.red_cubes_in_bin, self.blue_cubes_in_bin, self.green_cubes_in_bin],
                                                            total_number_list=[self.red_cubes_target_number, self.blue_cubes_target_number, self.green_cubes_target_number])
                ,is_any_obj_dropped_onto_delete(self, objects=c, target=self.board_with_hole)],
                "solve": lambda env, planner: [solve_button(env, planner, obj=self.button)],
                  "segment":self.cap_link 
            })
            self.task_list=tasks
            # Record pickup related task indices and items for recovery
            self.recovery_pickup_indices, self.recovery_pickup_tasks = task4recovery(self.task_list)
            if self.robomme_failure_recovery:
                # Only inject an intentional failed grasp when recovery mode is enabled
                self.fail_grasp_task_index = inject_fail_grasp(
                    self.task_list,
                    generator=self.generator,
                    mode=self.robomme_failure_recovery_mode,
                )
            else:
                self.fail_grasp_task_index = None


    def _get_obs_extra(self, info: Dict):
        return dict()



    def evaluate(self,solve_complete_eval=False):
        self.successflag=torch.tensor([False])
        # Save current_task_failure state before calling sequential_task_check
        # This is because failure might be detected during step(), but sequential_task_check might reset it
        previous_failure = getattr(self, "current_task_failure", False)
        self.failureflag = torch.tensor([False])



        if(self.use_demonstrationwrapper==False):# change subgoal after planner ends during recording
            if solve_complete_eval==True:
                allow_subgoal_change_this_timestep=True
            else:
                allow_subgoal_change_this_timestep=False
        else:# during demonstration, video needs to call evaluate(solve_complete_eval), video ends and flag changes in demonstrationwrapper
            if solve_complete_eval==True or self.demonstration_record_traj==False:
                allow_subgoal_change_this_timestep=True
            else:
                allow_subgoal_change_this_timestep=False

            
        # Use encapsulated sequence task check function
        all_tasks_completed, current_task_name, task_failed ,self.current_task_specialflag= sequential_task_check(self, self.task_list,allow_subgoal_change_this_timestep=allow_subgoal_change_this_timestep)

        # If task failed, mark as failed immediately
        # Or if failure was detected previously (previous_failure), also mark as failed
        if task_failed or previous_failure:
            self.failureflag = torch.tensor([True])
            if task_failed:
                logger.debug(f"Task failed: {current_task_name}")
            elif previous_failure:
                # If marked failed due to previous_failure, ensure current_task_failure is also set
                self.current_task_failure = True

        # If static_check succeeds or all tasks completed, set success flag
        if all_tasks_completed and not task_failed:
            self.successflag = torch.tensor([True])
        
        return {
            "success": self.successflag,
            "fail": self.failureflag,
        }

    def compute_dense_reward(self, obs: Any, action: torch.Tensor, info: Dict):
        tcp_to_obj_dist = torch.linalg.norm(
            self.agent.tcp_pose.p - self.agent.tcp_pose.p, axis=1
        )
        reaching_reward = 1 - torch.tanh(5 * tcp_to_obj_dist)
        reward = reaching_reward*0
        return reward

    def compute_normalized_dense_reward(
        self, obs: Any, action: torch.Tensor, info: Dict
    ):
        return self.compute_dense_reward(obs=obs, action=action, info=info) / 5

#Robomme
    def step(self, action: Union[None, np.ndarray, torch.Tensor, Dict]):
        self.vis_obj_id_list=[]
        
        timestep = self.elapsed_steps
        if self.dynamic:
            # Dynamically lift cubes for each color (starting from 2nd cube)
            for cube_list in [self.red_cubes, self.blue_cubes, self.green_cubes]:
                for idx in range(1, len(cube_list)):
                    lift_and_drop_objects_back_to_original(
                        self,
                        obj=cube_list[idx],
                        start_step=0,
                        end_step=idx * 100,
                        cur_step=timestep,
                    )
                
        obs, reward, terminated, truncated, info = super().step(action)

        return obs, reward, terminated, truncated, info
