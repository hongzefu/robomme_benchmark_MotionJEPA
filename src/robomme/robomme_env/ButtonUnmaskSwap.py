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
from .utils.difficulty import normalize_robomme_difficulty
from .utils.episode_spec import SpecRecorder
from .utils.sampling_config import assert_native_decision, split_sampling_config
from ..logging_utils import logger

PICK_CUBE_DOC_STRING = """**Task Description:**
A simple task where the objective is to grasp a red cube with the {robot_id} robot and move it to a target goal position. This is also the *baseline* task to test whether a robot with manipulation
capabilities can be simulated and trained properly. Hence there is extra code for some robots to set them up properly in this environment as well as the table scene builder.

**Randomizations:**
- the cube's xy position is randomized on top of a table in the region [0.1, 0.1] x [-0.1, -0.1]. It is placed flat on the table
- the cube's z-axis rotation is randomized to a random angle
- the target goal position (marked by a green sphere) of the cube has its xy position randomized in the region [0.1, 0.1] x [-0.1, -0.1] and z randomized in [0, 0.3]

**Success Conditions:**
- the cube position is within `goal_thresh` (default 0.025m) euclidean distance of the goal position
- the robot is static (q velocity < 0.2)
"""


# ── decision／native 两块的原值（newtaskRelease-v3 步 3，映射见方案第二节 2.8）────────
NATIVE_SAMPLING = {
    "parameters": {
        "bin_count": "FROM_CLASS_CONFIGS",
        "color_pool": [
            {"rgba": [1, 0, 0, 1], "name": "red"},
            {"rgba": [0, 1, 0, 1], "name": "green"},
            {"rgba": [0, 0, 1, 1], "name": "blue"},
        ],
        "color_order": {"sampler": "torch.randperm(3)"},
        "hidden_rule": "前三容器藏三色，第四个为空",
        "pick_rule": "右按钮→左按钮后，抓 selected_bins[0]，count=2 时再抓 [1]",
        "partner_rule": "交换开始时按实际 XY 取最近邻，不另抽签",
        "swap_window": {"start_step": 64, "duration_steps": 50},
        "swap_path": {"lane_offset": 0.07, "smooth": True, "keep_upright": True},
        "button_order": ["right", "left"],
        "recovery": "构造器的 self.generator 用于恢复；场景另建同 seed 局部流，两条流分开",
    },
    "positions": {
        "buttons": [
            {"name": "button_left", "center_xy": [-0.2, -0.1], "scale": 1.5,
             "randomize": True, "randomize_range": [0.05, 0.05]},
            {"name": "button_right", "center_xy": [-0.2, 0.1], "scale": 1.5,
             "randomize": True, "randomize_range": [0.05, 0.05]},
        ],
        "anchors": {
            "four_point": [[0, -0.1], [0, 0.1], [0.1, 0.1], [0.1, -0.1]],
            "triangle": [[-0.05, -0.15], [-0.05, 0.15], [0.05, 0]],
            "line": [[-0.05, -0.15], [-0.05, 0.15], [-0.05, 0]],
            "offset_scale": 0.1,
            "offset_note": "四点按两组各抽一次 y 偏移；三点各自抽一次 x 偏移；"
                            "未被选中的那一套分支仍然照常消费随机数（红线 R8）",
            "choice_sampler": "torch.randint(0, 2)",
        },
        "bins": {"region_half_size": 0.07, "min_gap_factor": 1, "max_trials": 256},
        "hidden_cube": {"half_size_divisor": 1.2, "yaw": 0.0},
    },
}


def native_blocks(cls):
    """本环境的 ``(decision, native)`` 原值块；外部导出与内部解析共用同一份。"""
    native = copy.deepcopy(NATIVE_SAMPLING)
    # 容器数按字段表属 native（本次未要求改按钮／容器布局），从类属性取原值。
    native["parameters"]["bin_count"] = {
        difficulty: cfg["bin"] for difficulty, cfg in cls.configs.items()
    }
    return _native_decision(cls), native


def _native_decision(cls):
    """按方案第二节 2.8 切出 decision 块（原值阶段等于原值）。"""
    return {
        "swap_count_range": {
            difficulty: [cfg["swap_min"], cfg["swap_max"]] for difficulty, cfg in cls.configs.items()
        },
        "pick_count_range": {
            difficulty: [cfg["pick_min"], cfg["pick_max"]] for difficulty, cfg in cls.configs.items()
        },
        # 交换速度倍率：原值 1（每段 50 步）；第二节的 1.5 倍本轮不启用。
        "swap_speed_multiplier": 1,
        "distractor": None,
    }


def _resolve_sampling_config(cls, override):
    """拆出本实例专属的 decision／native 副本；不抽随机数，必须在 Generator 之前调用。"""
    decision_default, native_default = native_blocks(cls)
    decision, native = split_sampling_config(override, native_default, decision_default)
    assert_native_decision(decision, decision_default, cls.__name__)
    native["decision"] = decision
    return native


@register_env("ButtonUnmaskSwap")
class ButtonUnmaskSwap(BaseEnv):


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
    config_easy = {
        "bin":3,
        "swap_min":1,
        "swap_max":2,
        "pick_min":1,
        "pick_max":2
    }
    config_medium= {
        "bin":4,
        "swap_min":1,
        "swap_max":2,
        "pick_min":1,
        "pick_max":1
    }
    config_hard = {
        "bin":4,
        "swap_min":2,
        "swap_max":3,
        "pick_min":2,
        "pick_max":2
    }


    # Combine into a dictionary
    configs = {
        'hard': config_hard,
        'easy': config_easy,
        'medium': config_medium
    }
    

    def __init__(self, *args, robot_uids="panda_wristcam", robot_init_qpos_noise=0,seed=0,Robomme_video_episode=None,Robomme_video_path=None,
                     sampling_config=None,
                     native_episode_spec=None,
                     **kwargs):
        # 必须落在任何随机数调用与 super().__init__() 之前
        self._sampling = _resolve_sampling_config(type(self), sampling_config)
        self._spec = SpecRecorder(native_episode_spec, "ButtonUnmaskSwap", {"seed": seed},
                                  difficulty=kwargs.get("difficulty"))
        # 初始化序号从 -1 起，_initialize_episode 每次进来先加一；
        # _load_scene 里的取值点用不带序号的路径，所以这里只作兜底。
        self._native_init_index = -1
        self.use_demonstrationwrapper=False
        self.demonstration_record_traj=False
        self.robot_init_qpos_noise = robot_init_qpos_noise
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
        self.robomme_failure_recovery = bool(
            kwargs.pop("robomme_failure_recovery", False)
        )
        self.robomme_failure_recovery_mode = kwargs.pop(
            "robomme_failure_recovery_mode", None
        )
        if isinstance(self.robomme_failure_recovery_mode, str):
            self.robomme_failure_recovery_mode = (
                self.robomme_failure_recovery_mode.lower()
            )
        normalized_robomme_difficulty = normalize_robomme_difficulty(
            kwargs.pop("difficulty", None)
        )
        if normalized_robomme_difficulty is not None:
            self.difficulty = normalized_robomme_difficulty
        else:
            seed_mod = seed % 3
            if seed_mod == 0:
                self.difficulty = "easy"
            elif seed_mod == 1:
                self.difficulty = "medium"
            else:  # seed_mod == 2
                self.difficulty = "hard"
        #self.difficulty = "hard"
        # Use seed to randomly determine number of repetitions (1-5)
        generator = torch.Generator()
        generator.manual_seed(seed)
        swap_range = self._sampling["decision"]["swap_count_range"][self.difficulty]
        self.swap_times = self._spec.value(
            "objects.n_swaps",
            torch.randint(swap_range[0], swap_range[1]+1, (1,), generator=generator).item(),
        )
        logger.debug(f"Task will swap {self.swap_times} times")


        pick_range = self._sampling["decision"]["pick_count_range"][self.difficulty]
        self.pick_times = self._spec.value(
            "objects.n_picks",
            torch.randint(pick_range[0], pick_range[1]+1, (1,), generator=generator).item(),
        )
        logger.debug(f"Task will pick {self.pick_times} times")

        super().__init__(*args, robot_uids=robot_uids, **kwargs)
    
    def _refresh_swap_schedule(self):
        if self.swap_times==1:
                    self.swap_schedule = [
                            (self.swap_pair1_idx1, self.swap_pair1_idx2, 64, 64 + 50),
                        ]# Final swap order
        elif self.swap_times==2:
            self.swap_schedule = [
                    (self.swap_pair1_idx1, self.swap_pair1_idx2, 64, 64 + 50),
                    (self.swap_pair2_idx1, self.swap_pair2_idx2, 64 + 50, 64 + 50 * 2),
                ]# Final swap order
        elif self.swap_times==3:
            self.swap_schedule = [
                    (self.swap_pair1_idx1, self.swap_pair1_idx2, 64, 64 + 50),
                    (self.swap_pair2_idx1, self.swap_pair2_idx2, 64 + 50, 64 + 50 * 2),
                    (self.swap_pair3_idx1, self.swap_pair3_idx2, 64 + 50 * 2, 64 + 50 * 3),
            ]

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
        return CameraConfig("render_camera", pose, 512, 512, 1, 0.01, 100)

    def _load_agent(self, options: dict):
        super()._load_agent(options, sapien.Pose(p=[-0.615, 0, 0]))

    def _load_scene(self, options: dict):
        generator = torch.Generator()
        generator.manual_seed(self.seed)
    
        self.table_scene = TableSceneBuilder(
            self, robot_init_qpos_noise=self.robot_init_qpos_noise
        )
        self.table_scene.build()

        avoid=[]

        avoid=[]
        buttons_cfg = self._sampling["positions"]["buttons"]
        anchors_cfg = self._sampling["positions"]["anchors"]
        bins_cfg = self._sampling["positions"]["bins"]
        button_obb_1 = build_button(
            self,
            center_xy=tuple(buttons_cfg[0]["center_xy"]),
            scale=buttons_cfg[0]["scale"],
            generator=generator,
            name=buttons_cfg[0]["name"],
            randomize=buttons_cfg[0]["randomize"],
            randomize_range=tuple(buttons_cfg[0]["randomize_range"])
        )
        # Store first button before building second one
        self.button_left = self.button
        self.button_joint_1 = self.button_joint

        avoid = [button_obb_1]

        button_obb_2 = build_button(
            self,
            center_xy=tuple(buttons_cfg[1]["center_xy"]),
            scale=buttons_cfg[1]["scale"],
            generator=generator,
            name=buttons_cfg[1]["name"],
            randomize=buttons_cfg[1]["randomize"],
            randomize_range=tuple(buttons_cfg[1]["randomize_range"])
        )
        # Store first button before building second one
        self.button_right = self.button
        self.button_joint_2 = self.button_joint

         # Generate 3 bins
        self.spawned_bins = []
        # Generate y offsets for region4 using torch generator
        offset_scale = anchors_cfg["offset_scale"]
        four_point = anchors_cfg["four_point"]
        y_offset_1 = (torch.rand(1, generator=generator).item()) * offset_scale  # for first two points
        y_offset_2 = (torch.rand(1, generator=generator).item()) * offset_scale  # for last two points

        region4=[[four_point[0][0], four_point[0][1] + y_offset_1],
                 [four_point[1][0], four_point[1][1] + y_offset_1],
                 [four_point[2][0], four_point[2][1] + y_offset_2],
                 [four_point[3][0], four_point[3][1] + y_offset_2]]


        # Generate independent random x offsets for each point using torch generator
        triangle = anchors_cfg["triangle"]
        line = anchors_cfg["line"]
        x_offset_tri_1 = (torch.rand(1, generator=generator).item()) * offset_scale
        x_offset_tri_2 = (torch.rand(1, generator=generator).item()) * offset_scale
        x_offset_tri_3 = (torch.rand(1, generator=generator).item()) * offset_scale

        x_offset_line_1 = (torch.rand(1, generator=generator).item()) * offset_scale
        x_offset_line_2 = (torch.rand(1, generator=generator).item()) * offset_scale
        x_offset_line_3 = (torch.rand(1, generator=generator).item()) * offset_scale

        region3_tri=[[triangle[0][0] + x_offset_tri_1, triangle[0][1]],
                     [triangle[1][0] + x_offset_tri_2, triangle[1][1]],
                     [triangle[2][0] + x_offset_tri_3, triangle[2][1]]]
        region3_line=[[line[0][0] + x_offset_line_1, line[0][1]],
                      [line[1][0] + x_offset_line_2, line[1][1]],
                      [line[2][0] + x_offset_line_3, line[2][1]]]

        # Use generator to randomly select region3_tri or region3_line
        region3_choice = self._spec.value(
            "layout.type_choice", torch.randint(0, 2, (1,), generator=generator).item()
        )
        region3 = region3_tri if region3_choice == 0 else region3_line

        if self._sampling["parameters"]["bin_count"][self.difficulty]==4:
            region=region4
        else:
             region=region3
        #angle, region = rotate_points_random(region,(0,180),generator)

        # # Safety check: ensure x coordinates are not less than 0
        # for i in range(len(region)):
        #     if region[i][0] < -0:
        #         region[i][0] = 0

        for i in range(self._sampling["parameters"]["bin_count"][self.difficulty]):
            try:
                bin_actor = spawn_random_bin(
                    self,
                    avoid=avoid,  # Use current avoidance list, containing all spawned objects
                    region_center=region[i],
                    region_half_size=bins_cfg["region_half_size"],
                    min_gap=self.cube_half_size*bins_cfg["min_gap_factor"],  # bins need larger gap, increased to 6x to avoid collision
                    name_prefix=f"bin_{i}",
                    max_trials=bins_cfg["max_trials"],
                    generator=generator,
                    recorder=self._spec,
                    spec_path=f"layout.bins.{i}"
                )
            except RuntimeError as e:
                break

            self.spawned_bins.append(bin_actor)
            # Assign bin to self.bin_0, self.bin_1 etc. attributes
            setattr(self, f"bin_{i}", bin_actor)
            # Add newly generated bin to avoidance list
            avoid.append(bin_actor)


        # Generate 3 dynamic cubes under each bin (using fixed position, colors red, green, blue)
        spawned_dynamic_cubes = []
        self.cube_bin_pairs = []
        self.bin_to_cube = {}
        self.bin_to_color = {}
        self.spawned_dynamic_cubes = spawned_dynamic_cubes
        cube_colors = [(1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1)]  # Red, Green, Blue
        color_names = ["red", "green", "blue"]

        # Use seed to randomly shuffle color order

        self._spec.identity.setdefault("difficulty", getattr(self, "difficulty", None))
        shuffle_indices = self._spec.value(
            "objects.color_order", torch.randperm(len(cube_colors), generator=generator).tolist()
        )
        cube_colors = [cube_colors[i] for i in shuffle_indices]
        color_names = [color_names[i] for i in shuffle_indices]

        # Store color_names for RecordWrapper access
        self.color_names = color_names

        # Randomly select 3 bins from all bins to spawn cube
        num_bins_to_select = min(3, len(self.spawned_bins))
        selected_bin_indices = self._spec.value(
            "objects.selected",
            torch.randperm(3, generator=generator)[:num_bins_to_select].tolist(),
        )
        selected_bins = [self.spawned_bins[idx] for idx in selected_bin_indices]
        self.selected_bin_indices = selected_bin_indices
        self.selected_bins = selected_bins  # Save selected bins, corresponding to color_names order

        for i, (bin_idx, bin_actor) in enumerate(zip(selected_bin_indices, selected_bins)):
            # Get bin position
            bin_pos = bin_actor.pose.p
            if isinstance(bin_pos, torch.Tensor):
                bin_pos = bin_pos[0].detach().cpu().numpy()

            cube_position = [bin_pos[0], bin_pos[1]]
            # Generate cube using fixed position, colors red, green, blue
            cube_actor = spawn_fixed_cube(
                self,
                position=cube_position,
                half_size=self.cube_half_size/self._sampling["positions"]["hidden_cube"]["half_size_divisor"],
                color=cube_colors[i],  # Use red, green, blue in order
                name_prefix=f"target_cube_{color_names[i]}",
                yaw=self._sampling["positions"]["hidden_cube"]["yaw"],  # No rotation
                dynamic=True
            )

            spawned_dynamic_cubes.append(cube_actor)
            # Assign cube to self.target_cube_red, self.target_cube_green, self.target_cube_blue etc. attributes
            setattr(self, f"target_cube_{color_names[i]}", cube_actor)
            # Also store using numeric index for easy access
            setattr(self, f"target_cube_{i}", cube_actor)
            setattr(self, f"target_cube_for_bin_{bin_idx}", cube_actor)
            self.cube_bin_pairs.append((cube_actor, bin_actor))
            self.bin_to_cube[bin_idx] = cube_actor
            self.bin_to_color[bin_idx] = color_names[i]

            # Add newly generated cube to avoidance list
            avoid.append(cube_actor)

        self.cube_bins = selected_bins
        self.cube_bin_indices = selected_bin_indices
        self.target_bin = None
        self.target_bin_index = None
        self.target_cube = None
        self.target_cube_color = None
        self.other_cube_bins = []
        self.other_cube_bin_indices = []
        self.other_cubes = []

        if self.cube_bin_pairs:
            target_choice = self._spec.value("objects.target_choice", int(
                torch.randint(
                    len(self.cube_bin_pairs),
                    (1,),
                    generator=generator,
                ).item()
            ))
            target_cube_actor, target_bin_actor = self.cube_bin_pairs[target_choice]
            self.target_cube = target_cube_actor
            self.target_bin = target_bin_actor
            self.target_bin_index = selected_bin_indices[target_choice]
            self.target_cube_color = color_names[target_choice]
            self.target_cube_name = (
                getattr(target_cube_actor, "name", None)
                or f"target_cube_{self.target_cube_color}"
            )
            self.target_label = self.target_cube_color or self.target_cube_name or "target"

            for idx_i, (cube_actor, bin_actor) in enumerate(self.cube_bin_pairs):
                if idx_i == target_choice:
                    continue
                self.other_cube_bins.append(bin_actor)
                self.other_cube_bin_indices.append(selected_bin_indices[idx_i])
                self.other_cubes.append(cube_actor)
        else:
            self.target_cube = None
            self.target_bin = None
            self.target_bin_index = None
            self.target_cube_color = None
            self.target_cube_name = None
            self.target_label = "target"

       # Randomly select 2 unique bins as target_bin_1 and target_bin_2
        # target_indices is index to selected_bin_indices (0, 1, 2)
        # 规格存整数列表，下游仍按张量用（.item()/.tolist()/torch.cat），所以包回张量
        target_indices = torch.tensor(self._spec.value(
            "objects.swap_initiator_indices",
            torch.randperm(len(selected_bin_indices), generator=generator)[:2].tolist(),
        ))
        # Use selected_bins to get correct bin (corresponding to color_names order)
        self.target_bin_1=self.selected_bins[target_indices[0]]
        self.target_bin_2=self.selected_bins[target_indices[1]]
        # Record cube colors corresponding to these two bins, index directly using color_names
        self.target_bin_1_cube_color = color_names[target_indices[0].item()]
        self.target_bin_2_cube_color = color_names[target_indices[1].item()]
        # swap_indices must include target_indices, then select 1 from remaining indices
        remaining_indices = [i for i in range(len(self.spawned_bins)) if i not in target_indices.tolist()]
        if remaining_indices:
            third_idx = self._spec.value(
                "objects.swap_initiator_third",
                remaining_indices[torch.randint(0, len(remaining_indices), (1,), generator=generator).item()],
            )
            swap_indices = torch.cat([target_indices, torch.tensor([third_idx])])
        else:
            swap_indices = target_indices
        self.swap_pair1_idx1=self.spawned_bins[swap_indices[0]]
        self.swap_pair2_idx1=self.spawned_bins[swap_indices[1]]
        self.swap_pair3_idx1=self.spawned_bins[swap_indices[2]]
        self.swap_pair1_idx2=None
        self.swap_pair2_idx2=None
        self.swap_pair3_idx2=None


        self._refresh_swap_schedule()

        self.button_list= [self.button_left, self.button_right]
        self.generator=generator

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        with torch.device(self.device):
            b = len(env_idx)
            self.table_scene.initialize(env_idx)
            qpos=reset_panda.get_reset_panda_param("qpos")
            self.agent.reset(qpos)
        tasks = [
            {
                "func": lambda: is_any_button_pressed_removelist(self, button_list=self.button_list),
                "name": "press the first button",
                "subgoal_segment":"press the first button at <>",
                "choice_label": "press the first button",
                "demonstration": False,
                "failure_func":None,
                "solve": lambda env, planner: solve_button(env, planner, obj=self.button_right),
                "segment":self.cap_links["button_right"]
            },
                  {
                "func": lambda: is_any_button_pressed_removelist(self, button_list=self.button_list),
                "name": "press the second button",
                "subgoal_segment":"press the second button at <>",
                "choice_label": "press the second button",
                "demonstration": False,
                "failure_func":None,
                "solve": lambda env, planner: solve_button(env, planner, obj=self.button_left),
                "segment":self.cap_links["button_left"]
            },

            {
                "func": (lambda: is_bin_pickup(self, obj=self.selected_bins[0])),
                "name": f"pick up the container that hides the {self.color_names[0]} cube",
                "subgoal_segment":f"pick up the container at <> that hides the {self.color_names[0]} cube",
                "choice_label": "pick up the container",
                "demonstration": False,
                "failure_func": lambda: is_any_bin_pickup(self,[bin for bin in self.spawned_bins if bin != self.selected_bins[0]]),
                "solve": lambda env, planner: [solve_pickup_bin(env, planner, obj=self.selected_bins[0])],
                "segment":self.selected_bins[0]
            }
        ]
        if self.pick_times==2:
            tasks.append({
                    "func": (lambda: is_bin_putdown(self, obj=self.selected_bins[0])),
                    "name": "put down the container",
                    "subgoal_segment":"put down the container",
                    "choice_label": "put down the container",
                    "demonstration": False,
                    "failure_func": lambda:is_any_bin_pickup(self,[bin for bin in self.spawned_bins if bin != self.selected_bins[0]]),
                    "solve": lambda env, planner: solve_putdown_whenhold(env, planner),
                })
            tasks.append(
                {
                    "func": (lambda: is_bin_pickup(self, obj=self.selected_bins[1])),
                        "name": f"pick up the container that hides the {self.color_names[1]} cube",
                        "subgoal_segment":f"pick up the container at <> that hides the {self.color_names[1]} cube",
                    "choice_label": "pick up the container",
                    "demonstration": False,
                    "failure_func": lambda: is_any_bin_pickup(self,[bin for bin in self.spawned_bins if bin != self.selected_bins[1]]),
                    "solve": lambda env, planner: solve_pickup_bin(env, planner, obj=self.selected_bins[1]),
                    "segment":self.selected_bins[1],
                })

        




        # Store task list for RecordWrapper use
        self.task_list = tasks

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
        self.failureflag = torch.tensor([False])
        target_color = getattr(self, "target_cube_color", None)
        if target_color is None and getattr(self, "color_names", None):
            target_color = self.color_names[0]
        if target_color is None:
            target_color = getattr(self, "target_label", None)
        if target_color is None:
            target_color = "target"
        self.target_label = target_color


        # Use encapsulated sequence task check function
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
        all_tasks_completed, current_task_name, task_failed ,self.current_task_specialflag= sequential_task_check(self, self.task_list,allow_subgoal_change_this_timestep=allow_subgoal_change_this_timestep)

        # If task failed, mark as failed immediately
        if task_failed:
            self.failureflag = torch.tensor([True])
            logger.debug(f"Task failed: {current_task_name}")
        else:
            self.failureflag = torch.tensor([False])

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

    def _get_other_bins_for_pair(self, idx_a: int, idx_b: int):
        """Return bins that are not part of the provided pair indices."""
        if not hasattr(self, "spawned_bins"):
            return []

        total_bins = len(self.spawned_bins)
        if idx_a >= total_bins or idx_b >= total_bins:
            return []

        # Prefer precomputed lists when available
        if hasattr(self, "otherbins") and idx_a < len(self.otherbins):
            other_candidates = [
                bin_actor
                for bin_actor in self.otherbins[idx_a]
                if bin_actor is not self.spawned_bins[idx_b]
            ]
            return other_candidates

        return [
            bin_actor
            for i, bin_actor in enumerate(self.spawned_bins)
            if i not in (idx_a, idx_b)
        ]

    def _get_actor_position(self, actor):
        """Return actor position as a numpy array."""
        if actor is None:
            return np.zeros(3, dtype=np.float32)

        pos = actor.pose.p if hasattr(actor, "pose") else actor.get_pose().p
        if isinstance(pos, torch.Tensor):
            pos = pos.detach().cpu().numpy()

        pos = np.asarray(pos, dtype=np.float32).reshape(-1)
        if pos.size < 3:
            padded = np.zeros(3, dtype=np.float32)
            padded[: pos.size] = pos
            return padded
        return pos

    def _compute_dynamic_swap_candidates(self, positions):
        """Compute nearest-neighbour swap candidates using provided positions."""
        candidate_map = {}
        num_positions = len(positions)
        if num_positions <= 1:
            return candidate_map

        for idx, pos in enumerate(positions):
            distances = []
            for other_idx, other_pos in enumerate(positions):
                if other_idx == idx:
                    continue
                dist = np.linalg.norm(pos[:2] - other_pos[:2])
                distances.append((other_idx, dist))

            distances.sort(key=lambda item: item[1])
            candidate_map[idx] = [j for j, _ in distances[:2]]

        return candidate_map

    def _select_swap_pair_from_positions(self, positions, generator):
        """Select one swap pair given current planned positions."""
        num_bins = len(positions)
        if num_bins < 2:
            return None

        candidate_map = self._compute_dynamic_swap_candidates(positions)
        valid_indices = [idx for idx, cands in candidate_map.items() if cands]
        if not valid_indices:
            return None

        if generator is None:
            generator = torch.Generator()
            generator.manual_seed(int(self.seed))
            self._swap_rng = generator

        first_idx = valid_indices[
            int(torch.randint(0, len(valid_indices), (1,), generator=generator).item())
        ]
        candidates = candidate_map[first_idx]
        second_idx = candidates[
            int(torch.randint(0, len(candidates), (1,), generator=generator).item())
        ]

        distance = float(
            np.linalg.norm(positions[first_idx][:2] - positions[second_idx][:2])
        )

        return {"idx1": first_idx, "idx2": second_idx, "distance": distance}


#Robomme
    def step(self, action: Union[None, np.ndarray, torch.Tensor, Dict]):



        timestep = self.elapsed_steps
        
        # Keep all spawned bins in their original placement during the pre-swap window
        for bin_actor in getattr(self, "spawned_bins", []):
            lift_and_drop_objects_back_to_original(
                self,
                obj=bin_actor,
                start_step=0,
                end_step=32*2,
                cur_step=timestep,
            )
        for i in range(len(self.swap_schedule)):
            start = self.swap_schedule[i][2]
            end = self.swap_schedule[i][3]
            if timestep in range (start,end):
                # Select corresponding swap pair based on index
                pair_idx1 = getattr(self, f'swap_pair{i+1}_idx1')
                pair_idx2 = getattr(self, f'swap_pair{i+1}_idx2')

                if pair_idx2 is None and pair_idx1 is not None:
                    reference_pos = self._get_actor_position(pair_idx1)
                    closest_actor = None
                    closest_dist = float("inf")
                    for candidate in self.spawned_bins:
                        if candidate is None or candidate is pair_idx1:
                            continue
                        candidate_pos = self._get_actor_position(candidate)
                        dist = np.linalg.norm(reference_pos[:2] - candidate_pos[:2])
                        if dist < closest_dist:
                            closest_dist = dist
                            closest_actor = candidate
                    if closest_actor is not None:
                        setattr(self, f'swap_pair{i+1}_idx2', closest_actor)
                        self._refresh_swap_schedule()
        
        for idx_a, idx_b, start_step, end_step in self.swap_schedule:
            
            if idx_a is None or idx_b is None:
                continue

            swap_flat_two_lane(
                self,
                cube_a=idx_a,
                cube_b=idx_b,
                start_step=start_step,
                end_step=end_step,
                cur_step=timestep,
                lane_offset=0.07,
                smooth=True,
                keep_upright=True,
                other_cube=[b for b in self.spawned_bins if b not in (idx_a, idx_b)],  # Keep all other bins in place to prevent collision during swap
            )


        for cube_actor, bin_actor in getattr(self, "cube_bin_pairs", []):
            if cube_actor is None or bin_actor is None:
                continue
            
            lift_and_drop_objectA_onto_objectB(
                self,
                obj_a=cube_actor,
                obj_b=bin_actor,
                start_step=64,
                end_step=self.swap_schedule[-1][3],
                cur_step=timestep,
            )

        obs, reward, terminated, truncated, info = super().step(action)
        return obs, reward, terminated, truncated, info
