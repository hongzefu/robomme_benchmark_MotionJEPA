import copy
from typing import Any, Dict, Union

import numpy as np
import sapien
import torch

import mani_skill.envs.utils.randomization as randomization
from mani_skill.agents.robots import SO100, Fetch, Panda
from mani_skill.envs.sapien_env import BaseEnv
from mani_skill.envs.tasks.tabletop.pick_cube_cfgs import PICK_CUBE_CONFIGS
from .utils.episode_spec import SpecRecorder
from .utils.sampling_config import assert_native_decision, split_sampling_config
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


# ── decision／native 两块的原值（newtaskRelease-v3 步 3，映射见方案第二节 2.6）────────
NATIVE_SAMPLING = {
    "parameters": {
        "color_pool": [
            {"rgba": [1, 0, 0, 1], "name": "red"},
            {"rgba": [0, 1, 0, 1], "name": "green"},
            {"rgba": [0, 0, 1, 1], "name": "blue"},
        ],
        "color_order": {"sampler": "torch.randperm(3)"},
        "constructor_rng": {
            "sampler": "torch.randint",
            "low": 1,
            "high_exclusive": 6,
            "note": "构造器这次抽样不决定抓取数量，但决定后续随机流位置，必须保留（红线 R8）",
        },
        "hidden_rule": "前 3 个容器各藏一块，其余为空",
        "pick_rule": "按按钮后先抓 bin_0，pick>1 再抓 bin_1",
        "recovery": "构造器的 self.generator 用于恢复；场景另有同 seed 局部 generator，两条流分开",
        "step_bin_scan": 15,
    },
    "positions": {
        "button": {
            "center_xy": [-0.2, 0],
            "scale": 1.5,
            "randomize": True,
            "randomize_range": [0.1, 0.1],
        },
        "bins": {"min_gap_factor": 2, "max_trials": 256, "yaw_expression": "u * 90 度"},
        "hidden_cube": {"half_size_divisor": 1.2, "yaw": 0.0, "dynamic": True},
        "reveal_window": {"start_step": 0, "end_step": 64},
    },
}


def native_blocks(cls):
    """本环境的 ``(decision, native)`` 原值块；外部导出与内部解析共用同一份。"""
    return _native_decision(cls), copy.deepcopy(NATIVE_SAMPLING)


def _native_decision(cls):
    """按方案第二节 2.6 切出 decision 块（原值阶段等于原值）。"""
    return {
        "pick_count": {difficulty: cfg["pick"] for difficulty, cfg in cls.configs.items()},
        "bin_layout_policy": {
            "count": {difficulty: cfg["bin"] for difficulty, cfg in cls.configs.items()},
            "region_center": [0, 0],
            "region_half_size": 0.2,
        },
        "distractor": None,
    }


def _resolve_sampling_config(cls, override):
    """拆出本实例专属的 decision／native 副本；不抽随机数，必须在 Generator 之前调用。"""
    decision_default, native_default = native_blocks(cls)
    decision, native = split_sampling_config(override, native_default, decision_default)
    assert_native_decision(decision, decision_default, cls.__name__)
    native["decision"] = decision
    return native


@register_env("ButtonUnmask")
class ButtonUnmask(BaseEnv):

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
    config_hard = {
    'bin':15,
    "pick":2,
    }

    config_easy = {
    'bin':3,
    "pick":1,
    }

    config_medium = {
    'bin':5,
    "pick":1,
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
        self._spec = SpecRecorder(native_episode_spec, "ButtonUnmask", {"seed": seed})
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
            self.robomme_failure_recovery_mode = (
                self.robomme_failure_recovery_mode.lower()
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

        # Use seed to randomly determine number of repetitions (1-5) arbitrarily
        generator = torch.Generator()
        generator.manual_seed(seed)
        ctor_cfg = self._sampling["parameters"]["constructor_rng"]
        # 这次抽样不决定抓取数量，但决定随机流位置；记进 sampling_trace 以证明它照常发生
        self.num_repeats = self._spec.value(
            "actions.sampling_trace.constructor_draw",
            torch.randint(ctor_cfg["low"], ctor_cfg["high_exclusive"], (1,), generator=generator).item(),
        )
        logger.debug(f"Task will repeat {self.num_repeats} times (pickup-drop cycles)")
        self.generator = generator  

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

        button_cfg = self._sampling["positions"]["button"]
        button_obb_1 = build_button(
            self,
            center_xy=tuple(button_cfg["center_xy"]),
            scale=button_cfg["scale"],
            generator=generator,
            name="button",
            randomize=button_cfg["randomize"],
            randomize_range=tuple(button_cfg["randomize_range"]),
            recorder=self._spec,
            spec_path="layout.button_xy",
        )
        # Store first button before building second one
        self.button_left = self.button
        self.button_joint_1 = self.button_joint

        avoid = [button_obb_1]


             # Generate 3 bins
        self.spawned_bins = []
        decision_cfg = self._sampling["decision"]
        bin_layout = decision_cfg["bin_layout_policy"]
        bins_cfg = self._sampling["positions"]["bins"]
        hidden_cfg = self._sampling["positions"]["hidden_cube"]
        for i in range(bin_layout["count"][self.difficulty]):
            try:
                bin_actor = spawn_random_bin(
                    self,
                    avoid=avoid,  # Use current avoidance list, containing all spawned objects
                    region_center=list(bin_layout["region_center"]),
                    region_half_size=bin_layout["region_half_size"],
                    min_gap=self.cube_half_size*bins_cfg["min_gap_factor"],  # bins need larger gap, increased to 6x to avoid collision
                    name_prefix=f"bin_{i}",
                    max_trials=bins_cfg["max_trials"],
                    generator=generator,
                    recorder=self._spec,
                    spec_path=f"layout.bins.{i}",
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

        # Generate cubes only for first 3 bins
        for i, bin_actor in enumerate(self.spawned_bins[:3]):
            # Get bin position
            bin_pos = bin_actor.pose.p
            if isinstance(bin_pos, torch.Tensor):
                bin_pos = bin_pos[0].detach().cpu().numpy()

            cube_position = [bin_pos[0], bin_pos[1]]
            # Generate cube using fixed position, colors red, green, blue
            cube_actor = spawn_fixed_cube(
                self,
                position=cube_position,
                half_size=self.cube_half_size/hidden_cfg["half_size_divisor"],
                color=cube_colors[i],  # Use red, green, blue in order
                name_prefix=f"target_cube_{color_names[i]}",
                yaw=hidden_cfg["yaw"],  # No rotation
                dynamic=True
            )

            spawned_dynamic_cubes.append(cube_actor)
            # Assign cube to self.target_cube_red, self.target_cube_green, self.target_cube_blue etc. attributes
            setattr(self, f"target_cube_{color_names[i]}", cube_actor)
            # Also store using numeric index for easy access
            setattr(self, f"target_cube_{i}", cube_actor)
            # Add newly generated cube to avoidance list
            avoid.append(cube_actor)



        tasks = [
            {
                "func": lambda: is_button_pressed(self, obj=self.button_left),
                "name": "press the button",
                "subgoal_segment":"press the button at <>",
                "choice_label": "press the button",
                "demonstration": False,
                "failure_func":None,
                "solve": lambda env, planner: solve_button(env, planner, obj=self.button_left),
                "segment":self.cap_link,
            },]
        tasks.append(
                    {
                        "func": (lambda: is_bin_pickup(self, obj=self.bin_0)),
                        "name": f"pick up the container that hides the {self.color_names[0]} cube",
                        "subgoal_segment":f"pick up the container at <> that hides the {self.color_names[0]} cube",
                        "choice_label": "pick up the container",
                        "demonstration": False,
                        "failure_func": lambda: [
                                is_any_bin_pickup(self,[bin for bin in self.spawned_bins if bin != self.bin_0]), ],
                        "solve": lambda env, planner: [solve_pickup_bin(env, planner, obj=self.bin_0)],
                         "segment":self.bin_0,
                    })
        if decision_cfg["pick_count"][self.difficulty]>1:
            tasks.append({
                    "func": (lambda: is_bin_putdown(self, obj=self.bin_0)),
                    "name": "put down the container",
                    "subgoal_segment":"put down the container",
                    "choice_label": "put down the container",
                    "demonstration": False,
                    "failure_func": lambda:is_any_bin_pickup(self,[bin for bin in self.spawned_bins if bin != self.bin_0]),
                    "solve": lambda env, planner: solve_putdown_whenhold(env, planner),
                })
            tasks.append(
                {
                    "func": (lambda: is_bin_pickup(self, obj=self.bin_1)),
                        "name": f"pick up the container that hides the {self.color_names[1]} cube",
                        "subgoal_segment":f"pick up the container at <> that hides the {self.color_names[1]} cube",
                    "choice_label": "pick up the container",
                    "demonstration": False,
                    "failure_func": lambda: is_any_bin_pickup(self,[bin for bin in self.spawned_bins if bin != self.bin_1]),
                    "solve": lambda env, planner: solve_pickup_bin(env, planner, obj=self.bin_1),
                    "segment":self.bin_1,
                })
        self.task_list = tasks
        # Set recovery related attributes
        # Record pickup related task indices and items for recovery
        self.recovery_pickup_indices, self.recovery_pickup_tasks = task4recovery(self.task_list)
        if self.robomme_failure_recovery:
            # Only inject an intentional failed grasp when recovery mode is enabled
            # 恢复动作的选择是一次真实抽样：原位置照常抽，回注模式下用冻结的索引
            self.fail_grasp_task_index = self._spec.value(
                f"initializations.{self._native_init_index}.recovery_action_index",
                inject_fail_grasp(
                self.task_list,
                generator=self.generator,
                mode=self.robomme_failure_recovery_mode,
            ),
            )
        else:
            self.fail_grasp_task_index = None

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        # 每次初始化各自记一份规格，不复用上一次的结果
        self._native_init_index = getattr(self, "_native_init_index", -1) + 1
        with torch.device(self.device):
            b = len(env_idx)
            self.table_scene.initialize(env_idx)
            qpos=reset_panda.get_reset_panda_param("qpos")
            self.agent.reset(qpos)


    def _get_obs_extra(self, info: Dict):
        return dict()



    def evaluate(self,solve_complete_eval=False):
        self.successflag=torch.tensor([False])
        self.failureflag = torch.tensor([False])

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

        #print(f"Current Task: {current_task_name}")
        
        # If task failed, mark as failed immediately
        if task_failed:
            self.failureflag = torch.tensor([True])
            logger.debug(f"Task failed: {current_task_name}")

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


#Robomme
    def step(self, action: Union[None, np.ndarray, torch.Tensor, Dict]):


     
        timestep = self.elapsed_steps
        
                #Lift and drop bins (bin_0 to bin_4 if they exist)
        for i in range(self._sampling["parameters"]["step_bin_scan"]):
            bin_attr = f"bin_{i}"
            if hasattr(self, bin_attr):
                lift_and_drop_objects_back_to_original(
                    self,
                    obj=getattr(self, bin_attr),
                    start_step=self._sampling["positions"]["reveal_window"]["start_step"],
                    end_step=self._sampling["positions"]["reveal_window"]["end_step"],
                    cur_step=timestep,
                ) 

        obs, reward, terminated, truncated, info = super().step(action)
        return obs, reward, terminated, truncated, info
