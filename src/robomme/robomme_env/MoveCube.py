from typing import Any, Dict, Union

import numpy as np
import sapien
import torch

from mani_skill.agents.robots import SO100, Fetch, Panda
from mani_skill.envs.sapien_env import BaseEnv
from mani_skill.envs.tasks.tabletop.pick_cube_cfgs import PICK_CUBE_CONFIGS
from mani_skill.sensors.camera import CameraConfig
from mani_skill.utils import sapien_utils
from mani_skill.utils.building import actors
from mani_skill.utils.registration import register_env
from mani_skill.utils.scene_builder.table import TableSceneBuilder
from mani_skill.utils.structs.pose import Pose
from mani_skill.utils import common, sapien_utils
from mani_skill.utils.structs import Actor
#Robomme
import matplotlib.pyplot as plt

from mani_skill.utils.geometry.rotation_conversions import (
    euler_angles_to_matrix,
    matrix_to_quaternion,
)
import copy
from .utils import *
from .utils.difficulty import normalize_robomme_difficulty
from .utils.subgoal_evaluate_func import static_check
from .utils.episode_spec import SpecRecorder
from .utils.sampling_config import SamplingConfigError, assert_native_decision, split_sampling_config
from .utils.SceneGenerationError import SceneGenerationError
from .utils.episode_spec import EpisodeSpecError
from .utils import subgoal_language
from .utils.object_generation import spawn_fixed_cube, build_board_with_hole
from .utils import reset_panda
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


# ── decision／native 两块的原值（newtaskRelease-v3 步 3，映射见方案第二节 2.13）────────
NATIVE_SAMPLING = {
    "parameters": {
        "peg_size": {
            "length_expression": "0.1 + (0.05 - 0.05) * rand()",
            "radius_expression": "0.01 + (0.005 - 0.005) * rand()",
            "note": "两次 rand 结果被乘 0 消掉，但必须保留以免平移随机流（红线 R8）",
        },
        "way_selection": {"sampler": "torch.randint(len(self.ways))"},
        "obj_selection": {"sampler": "torch.randint(0, 2)", "mapping": [-1, 1]},
        "dir_sample": {"sampler": "torch.randint(0, 2)", "consumed": False,
                        "note": "抽了但未使用，保留为 sampling_trace"},
        "direction_rule": "evaluate 按两套布局的实际 y 差给 ±1，不再随机抽",
        "reset_rule": "step 切换到已生成的执行位姿",
        "recovery": "本环境没有 inject_fail_grasp，只接收入口恢复模式，实际恢复动作为 null",
    },
    "positions": {
        "goal_demo": {"region_center": [0.0, 0.0], "region_half_size": 0.15,
                       "radius_factor": 2, "min_gap_factor": 1},
        "goal_execution": {"region_center": [0.0, 0.0], "region_half_size": 0.1,
                            "radius_factor": 2, "min_gap_factor": 1},
        "cube_rejection": {"max_trials": 128, "min_distance_factor": 5},
        "peg_color": {"head": "#EC7357", "tail": "#EC7357"},
    },
}


def native_blocks(cls):
    """本环境的 ``(decision, native)`` 原值块；外部导出与内部解析共用同一份。"""
    return _native_decision(cls), copy.deepcopy(NATIVE_SAMPLING)


def _native_decision(cls):
    """按方案第二节 2.13 切出 decision 块（原值阶段等于原值）。

    V4（计划 2.17）：xhard 新值一律挂在名为 ``xhard`` 的子键下（守卫只放行这些键偏离），
    默认值取自 ``cls.configs["xhard"]``；原三档可见部分与 V3 逐字相同。

    V5（计划 2.9，L30/L33）：V4 的 ``corner_bias`` 已删除；演示段与执行段各自暴露一份
    ``center_exclusion``（桌面中心共同禁区，两段各自声明、各自消费）。
    """
    xhard = cls.configs["xhard"]
    return {
        # 演示阶段的方块与杆位置采样规则（原值：杆基位 y=±0.2、xy 各抖动 ±0.05；
        # 方块候选中心 xy 各 ±0.1，再在 half_size 0.05 的小区里生成）。
        "demo_layout": {
            "peg_position_policy": {"base_y_abs": 0.2, "base_y_threshold": 0.5, "jitter_span": 0.1},
            "cube_position_policy": {"center_span": 0.2, "center_offset": -0.1, "region_half_size": 0.05},
            # V5 xhard：桌面中心共同禁区（L30；杆按轴线段、goal 与方块按中心判）
            "xhard": {"center_exclusion": copy.deepcopy(xhard["center_exclusion"])},
        },
        # 执行阶段另抽一套，原规则与演示相同但必须分开，不能误合并。
        "execution_layout": {
            "peg_position_policy": {"base_y_abs": 0.2, "base_y_threshold": 0.5, "jitter_span": 0.1},
            "cube_position_policy": {"center_span": 0.2, "center_offset": -0.1, "region_half_size": 0.05},
            # V5 xhard：执行段的中心禁区，与演示段各自声明、各自消费（两套不可合并）
            "xhard": {"center_exclusion": copy.deepcopy(xhard["center_exclusion"])},
        },
        # 杆在桌面内的转角范围：原值 ±π/4（表达式为 u*span - offset）。
        # V4 xhard：±π（A1，仍只绕世界 z；joint7 冲突按等价朝向归约，见 B11）。
        "peg_yaw_range": {"span_rad": np.pi / 2, "offset_rad": np.pi / 4,
                          "xhard": dict(xhard["peg_yaw_range"])},
    }


def _resolve_sampling_config(cls, override):
    """拆出本实例专属的 decision／native 副本；不抽随机数，必须在 Generator 之前调用。"""
    decision_default, native_default = native_blocks(cls)
    decision, native = split_sampling_config(override, native_default, decision_default)
    assert_native_decision(decision, decision_default, cls.__name__)
    native["decision"] = decision
    return native


# ── V5 xhard 桌面中心禁区（计划 2.9）：纯数值判据，不抽随机数，只在 xhard 分支被调用 ──────────
def _peg_axis_extent(length):
    """杆轴线段在杆根坐标系里沿杆朝向 u 的区间 ``(t_min, t_max)``（米）。

    由 ``utils/object_generation.py::build_peg`` 的几何推出：head link 以杆根为中心，tail link
    经固定关节挂在 ``−length·u``；两段的碰撞盒半长 ``0.45·length``、可视盒半长 ``0.5·length``。
    取碰撞与可视外形的并集（即可视外形），``length=0.1`` 时为 ``(−0.15, +0.05)``，与 P2 实测一致。
    xhard 每次建杆后由 ``MoveCube._xhard_verify_peg_extent`` 用实际形状复核，二者不符即报错。
    """
    head_half = 0.5 * float(length)          # 可视盒半长（碰撞盒 0.45·length 被它包住）
    tail_center = -float(length)             # tail 固定关节的 pose_in_parent
    return (tail_center - head_half, head_half)


def _peg_root_xy(base_y, x_jitter, y_jitter):
    """与 ``_load_scene`` 建杆时的 float32 平移逐位同算法，得到杆根 xy（float64）。"""
    translation = np.array([0.0, base_y, 0.0], dtype=np.float32)
    translation[1] = base_y
    translation[:2] += np.array([x_jitter, y_jitter], dtype=np.float32)
    return translation[:2].astype(np.float64)


def _peg_zone_distance(base_y, x_jitter, y_jitter, yaw, zone, extent):
    """杆实际轴线段 ``root + t·u``（``t∈extent``）离禁区圆心的最近距离。"""
    root = _peg_root_xy(base_y, x_jitter, y_jitter)
    u = np.array([np.cos(float(yaw)), np.sin(float(yaw))], dtype=np.float64)
    rel = root - zone["center"]
    t = float(np.clip(-(rel @ u), extent[0], extent[1]))
    return float(np.linalg.norm(rel + t * u))


def _zone_violated(zone, xy):
    """物体中心 ``xy`` 离禁区圆心的距离 ``< radius`` 即违反（与 spawn 函数的 center_exclusion 同一判据）。"""
    return float(np.linalg.norm(np.asarray(xy, dtype=np.float64) - zone["center"])) < zone["radius"]


def _assert_peg_outside_zone(base_y, x_jitter, y_jitter, yaw, zone, extent, spec_prefix):
    """N17：回放冻结规格时杆位姿不经拒绝循环，按同一规则复核，违反抛 ``EpisodeSpecError``。"""
    dist = _peg_zone_distance(base_y, x_jitter, y_jitter, yaw, zone, extent)
    if dist < zone["radius"]:
        raise EpisodeSpecError(
            f"MoveCube xhard：{spec_prefix}.peg_offsets/peg_yaw 的杆轴线段离禁区圆心 {dist:.6f} "
            f"< {zone['radius']}（冻结或注入值违反桌面中心禁区）")


@register_env("MoveCube")
class MoveCube(BaseEnv):

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
    _clearance = 0.01

    # V4（A4/A6）：本环境原本没有难度分档，现有全局常量即 hard；三档同值，
    # difficulty 只在 xhard 生效。消费点读的是 decision（可被 sampling_config 覆盖），
    # 这里是 decision 的默认值来源。
    config_native = {
        "peg_yaw_range": {"span_rad": np.pi / 2, "offset_rad": np.pi / 4},
        "corner_bias": 0.0,
    }
    config_xhard = {
        # ±180°：u*2π - π（A1）
        "peg_yaw_range": {"span_rad": 2 * np.pi, "offset_rad": np.pi},
        # V5（计划 2.9，L30/L33）：V4 的 corner_bias 已删除（不再用偏置），改为桌面中心共同禁区、
        # 直接拒绝：以 (0,0) 为圆心、半径 0.05 m 的圆；杆按实际轴线段离圆心的最近点判，
        # goal 圆盘、方块候选中心与方块最终中心按物体中心判；落进圆即原地重抽。
        # max_trials 只约束新增的杆重抽循环（goal/方块沿用各自原有循环的预算），超出抛 SceneGenerationError。
        "center_exclusion": {"shape": "circle", "center": [0.0, 0.0], "radius_m": 0.05,
                             "judge": "object_center", "max_trials": 128},
    }
    configs = {
        "easy": config_native,
        "medium": config_native,
        "hard": config_native,
        "xhard": config_xhard,
    }

    def __init__(self, *args, robot_uids="panda_wristcam", robot_init_qpos_noise=0,seed=0,Robomme_video_episode=None,Robomme_video_path=None,
                     sampling_config=None,
                     native_episode_spec=None,
                     **kwargs):
        # 必须落在任何随机数调用与 super().__init__() 之前
        self._sampling = _resolve_sampling_config(type(self), sampling_config)
        self._spec = SpecRecorder(native_episode_spec, "MoveCube", {"seed": seed},
                                  difficulty=kwargs.get("difficulty"))
        # 初始化序号从 -1 起，_initialize_episode 每次进来先加一；
        # _load_scene 里的取值点用不带序号的路径，所以这里只作兜底。
        self._native_init_index = -1
        self.reset_in_proecess=False
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
        self._hb_generator = torch.Generator()
        self._hb_generator.manual_seed(int(self.seed))

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
            else:
                self.difficulty = "hard"
        if self.difficulty == "xhard":
            # V4 B11：抓杆时按等价朝向归约（只改夹爪姿态，并同步补偿抓杆后的推杆路点）；
            # 求解器按这个开关分叉，原三档不设此属性、走原路径
            self._xhard_peg_yaw_reduction = True

        self.restore_flag=False
        self.use_demonstrationwrapper=False
        self.demonstration_record_traj=False
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
        self.table_scene = TableSceneBuilder(
            self, robot_init_qpos_noise=0
        )
        self.table_scene.build()

        length_tensor = torch.rand(1, generator=self._hb_generator)
        radius_tensor = torch.rand(1, generator=self._hb_generator)
        self.length = (0.1 + (0.05 - 0.05) * length_tensor).item()
        self.radius = (0.01 + (0.005 - 0.005) * radius_tensor).item()

        # Create a single peg
        #peg_spawn_translation = np.array([self.length / 2, 0.0, self.radius], dtype=np.float32)
        demo_layout = self._sampling["decision"]["demo_layout"]
        exec_layout = self._sampling["decision"]["execution_layout"]
        peg_yaw_range = self._sampling["decision"]["peg_yaw_range"]
        native_pos = self._sampling["positions"]
        # V4 xhard（计划 2.17）：±180° 转角只在 xhard 生效；原三档转角仍读 decision 顶层的 span/offset。
        # V5 xhard（计划 2.9）：corner_bias 已删除，改为桌面中心共同禁区（直接拒绝）；原三档
        # demo_zone/exec_zone 为 None，不执行任何禁区判定、不多抽随机数，随机调用序列逐字不变
        xhard = self.difficulty == "xhard"
        if xhard:
            demo_zone = self._xhard_center_exclusion(demo_layout, "demo_layout")
            exec_zone = self._xhard_center_exclusion(exec_layout, "execution_layout")
            yaw_policy = peg_yaw_range["xhard"]
            dk_demo, dk_exec, dk_yaw = ("demo_layout.xhard.center_exclusion",
                                        "execution_layout.xhard.center_exclusion", "peg_yaw_range.xhard")
            # 杆轴线段在杆根坐标系里沿朝向 u 的区间，由 build_peg 的几何推出（不写死常数）
            peg_extent = _peg_axis_extent(self.length)
            zone_trials = {"demo": {}, "execution": {}}
        else:
            demo_zone = exec_zone = None
            yaw_policy = peg_yaw_range
            dk_demo = dk_exec = dk_yaw = None
        demo_peg = demo_layout["peg_position_policy"]
        base_y = -demo_peg["base_y_abs"] if torch.rand(1, generator=self._hb_generator).item() < demo_peg["base_y_threshold"] else demo_peg["base_y_abs"]

        peg_spawn_translation = np.array([0.0, base_y, 0.0], dtype=np.float32)

        # Generate [-0.05, 0.05] random offset (using torch generator)
        if xhard:
            # V5：抖动与 yaw 按原顺序抽完后判杆轴线段是否进禁区，进了就三者原地重抽
            x_jitter, y_jitter, initial_yaw, zone_trials["demo"]["peg_trials"] = self._xhard_sample_peg_outside_zone(
                base_y, demo_peg, yaw_policy, demo_zone, peg_extent, "演示段")
        else:
            x_jitter = (torch.rand(1, generator=self._hb_generator).item() - 0.5) * demo_peg["jitter_span"]
            y_jitter = (torch.rand(1, generator=self._hb_generator).item() - 0.5) * demo_peg["jitter_span"]

        # Apply offset
        base_y, x_jitter, y_jitter = self._spec.value(
            "layout.demo.peg_offsets", [base_y, x_jitter, y_jitter], decision_key=dk_demo
        )
        peg_spawn_translation[1] = base_y
        peg_spawn_translation[:2] += np.array([x_jitter, y_jitter], dtype=np.float32)
        self.peg1_basex=peg_spawn_translation[0]
        self.peg1_basey=peg_spawn_translation[1]

        if not xhard:
            initial_yaw = torch.rand(1, generator=self._hb_generator).item() * (yaw_policy["span_rad"]) - (yaw_policy["offset_rad"])
        initial_yaw = self._spec.value("layout.demo.peg_yaw", initial_yaw, decision_key=dk_yaw)
        if xhard:
            # N17：回放时上面两处 value 返回冻结值、不经拒绝循环，必须按同一规则复核
            _assert_peg_outside_zone(base_y, x_jitter, y_jitter, initial_yaw, demo_zone, peg_extent, "layout.demo")
        yaw_angles = torch.tensor([[0.0, 0.0, initial_yaw]], dtype=torch.float32)
        yaw_matrix = euler_angles_to_matrix(yaw_angles, convention="XYZ")
        yaw_quat = matrix_to_quaternion(yaw_matrix)[0].detach().cpu().numpy().tolist()

        peg_initial_pose = sapien.Pose(
            p=peg_spawn_translation.tolist(),
            q=yaw_quat,
        )

        self.peg, self.peg_head, self.peg_tail = build_peg(
            self,
            length=self.length,
            radius=self.radius,
            initial_pose=peg_initial_pose,
            name='peg',
            head_color= "#EC7357",
            tail_color= "#EC7357",
        )

        if xhard:
            # 禁区判据用的杆轴线段必须与刚建好的杆的实际碰撞/可视几何一致，否则判据形同虚设
            self._xhard_verify_peg_extent(peg_extent)

        # Create lists for backward compatibility
        self.pegs = [self.peg]
        self.peg_heads = [self.peg_head]
        self.peg_tails = [self.peg_tail]



        # Store initial poses for all pegs
        self.peg_init_poses = [peg.pose for peg in self.pegs]
        self.peg_init_pose = self.pegs[0].pose  # Keep backward compatibility

        #generate another set of pose for another reset
        exec_peg = exec_layout["peg_position_policy"]
        base_y = -exec_peg["base_y_abs"] if torch.rand(1, generator=self._hb_generator).item() < exec_peg["base_y_threshold"] else exec_peg["base_y_abs"]

        peg_spawn_translation = np.array([0.0, base_y, 0.0], dtype=np.float32)
        if xhard:
            x_jitter, y_jitter, initial_yaw, zone_trials["execution"]["peg_trials"] = self._xhard_sample_peg_outside_zone(
                base_y, exec_peg, yaw_policy, exec_zone, peg_extent, "执行段")
        else:
            x_jitter = (torch.rand(1, generator=self._hb_generator).item() - 0.5) * exec_peg["jitter_span"]
            y_jitter = (torch.rand(1, generator=self._hb_generator).item() - 0.5) * exec_peg["jitter_span"]
        base_y, x_jitter, y_jitter = self._spec.value(
            "layout.execution.peg_offsets", [base_y, x_jitter, y_jitter], decision_key=dk_exec
        )
        peg_spawn_translation[1] = base_y
        peg_spawn_translation[:2] += np.array([x_jitter, y_jitter], dtype=np.float32)

        if not xhard:
            initial_yaw = torch.rand(1, generator=self._hb_generator).item() * (yaw_policy["span_rad"]) - (yaw_policy["offset_rad"])
        initial_yaw = self._spec.value("layout.execution.peg_yaw", initial_yaw, decision_key=dk_yaw)
        if xhard:
            _assert_peg_outside_zone(base_y, x_jitter, y_jitter, initial_yaw, exec_zone, peg_extent, "layout.execution")
        yaw_angles = torch.tensor([[0.0, 0.0, initial_yaw]], dtype=torch.float32)
        yaw_matrix = euler_angles_to_matrix(yaw_angles, convention="XYZ")
        yaw_quat = matrix_to_quaternion(yaw_matrix)[0].detach().cpu().numpy().tolist()

        self.peg2_basex=peg_spawn_translation[0]
        self.peg2_basey=peg_spawn_translation[1]
        peg_initial_pose = sapien.Pose(
            p=peg_spawn_translation.tolist(),
            q=yaw_quat,
        )
        self.peg_init_poses_2=[peg_initial_pose]
        
        self.finish_return_flag=False

                # Define task list, each task contains a dictionary with function, name, demonstration flag, and optional failure_func
        obj_sample = self._spec.value(
            "objects.obj_sample",
            int(torch.randint(0, 2, (1,), generator=self._hb_generator).item()),
        )
        self.obj_flag = -1 if obj_sample == 0 else 1
        # 这次抽样原本就没被消费；记进 sampling_trace 以证明它照常发生（红线 R8）
        dir_sample = self._spec.value(
            "objects.sampling_trace.dir_sample",
            int(torch.randint(0, 2, (1,), generator=self._hb_generator).item()),
        )
        #self.direction = -1 if dir_sample.item() == 0 else 1


        # V5 xhard：goal 圆盘中心落进禁区即在 spawn_random_target 的拒绝循环里重抽；原三档不传新参数
        demo_goal_extra = {"center_exclusion": demo_zone["rule"]} if xhard else {}
        exec_goal_extra = {"center_exclusion": exec_zone["rule"]} if xhard else {}
        try:
            self.goal_site = spawn_random_target(
                        self,
                        avoid=None,  # Use current avoidance list, containing all spawned cubes
                        include_existing=False,  # Manually maintain list
                        include_goal=False,  # Manually maintain list
                        region_center=list(native_pos["goal_demo"]["region_center"]),
                        region_half_size=native_pos["goal_demo"]["region_half_size"],
                        radius=self.cube_half_size*native_pos["goal_demo"]["radius_factor"],  # Use radius instead of half_size
                        thickness=0.005,  # target thickness
                        min_gap=self.cube_half_size*1,  # Gap requirement same as cube
                        name_prefix=f"goal_site",
                        recorder=self._spec,
                        spec_path="layout.demo.goal_xy",
                        generator=self._hb_generator,
                        **demo_goal_extra,
                        )
        except RuntimeError as exc:
            if xhard and not isinstance(exc, SceneGenerationError):
                raise SceneGenerationError(f"MoveCube xhard：演示段 goal 生成失败：{exc}") from exc
            raise
        try:
            self.goal_site_2 = spawn_random_target(
                self,
                avoid=None,  # Use current avoidance list, containing all spawned cubes
                include_existing=False,  # Manually maintain list
                include_goal=False,  # Manually maintain list
                region_center=list(native_pos["goal_execution"]["region_center"]),
                region_half_size=native_pos["goal_execution"]["region_half_size"],
                radius=self.cube_half_size*native_pos["goal_execution"]["radius_factor"],  # Use radius instead of half_size
                thickness=0.005,  # target thickness
                min_gap=self.cube_half_size*1,  # Gap requirement same as cube
                name_prefix=f"goal_site_2",
                recorder=self._spec,
                spec_path="layout.execution.goal_xy",
                generator=self._hb_generator,
                **exec_goal_extra,
                )
        except RuntimeError as exc:
            if xhard and not isinstance(exc, SceneGenerationError):
                raise SceneGenerationError(f"MoveCube xhard：执行段 goal 生成失败：{exc}") from exc
            raise
        


        max_cube_spawn_trials = native_pos["cube_rejection"]["max_trials"]

        goal_pos = self.goal_site.pose.p
        goal_xy = np.asarray(goal_pos)
        goal_xy = np.asarray(goal_xy, dtype=np.float64).reshape(-1)[:2]

        def _sample_cube_center(required_distance: float):
            for _ in range(max_cube_spawn_trials):
                demo_cube = demo_layout["cube_position_policy"]
                sampled_x = torch.rand(1, generator=self._hb_generator).item() * demo_cube["center_span"] + demo_cube["center_offset"]
                #direction = -1.0 if -self.peg1_basey < 0 else 1.0
                #sampled_y = torch.rand(1, generator=self._hb_generator).item() * 0.2 * direction
                sampled_y = torch.rand(1, generator=self._hb_generator).item() * demo_cube["center_span"] + demo_cube["center_offset"]
                candidate_xy = np.array([sampled_x, sampled_y], dtype=np.float64)
                if np.linalg.norm(candidate_xy - goal_xy) > required_distance:
                    # V5 xhard：候选中心落进禁区同样拒绝（与 goal 距离判据共用同一次试验与 128 次预算）
                    if demo_zone is not None and _zone_violated(demo_zone, candidate_xy):
                        zone_trials["demo"]["cube_candidate_center_rejects"] += 1
                        continue
                    return candidate_xy
            return None

        if xhard:
            zone_trials["demo"]["cube_candidate_center_rejects"] = 0

        cube_center = _sample_cube_center(self.cube_half_size*native_pos["cube_rejection"]["min_distance_factor"])
        if xhard and cube_center is None:
            # D3（只在 xhard 修，H2）：原三档此处 None 会在下一行触发 TypeError，保持原样
            raise SceneGenerationError(
                f"MoveCube xhard：演示段方块中心 {max_cube_spawn_trials} 次拒绝采样全部失败")

        cube_x, cube_y = float(cube_center[0]), float(cube_center[1])

        # V5 xhard：方块最终中心按禁区复查；include_existing=False 让已放方块不以 actor（会退化的
        # trimesh OBB）作障碍——本局演示段方块之前没有别的方块，结果与默认值相同（计划 2.0①）。
        # 原三档调用参数逐字不变
        demo_cube_extra = {"include_existing": False, "center_exclusion": demo_zone["rule"]} if xhard else {}
        try:
            self.cube = spawn_random_cube(
                            self,
                            region_center=[cube_x, cube_y],
                            color=(1, 0, 0, 1),
                            name_prefix="fixed_cube",
                            recorder=self._spec,
                            spec_path="layout.demo.cube_pose",
                            region_half_size=demo_layout["cube_position_policy"]["region_half_size"],
                            generator=self._hb_generator,
                            half_size=self.cube_half_size,
                            **demo_cube_extra,
                        )
        except RuntimeError as exc:
            if xhard and not isinstance(exc, SceneGenerationError):
                raise SceneGenerationError(f"MoveCube xhard：演示段方块生成失败：{exc}") from exc
            raise
        
        self.cube_init_pose=self.cube.pose



        goal_pos = self.goal_site_2.pose.p
        goal_xy = np.asarray(goal_pos)
        goal_xy = np.asarray(goal_xy, dtype=np.float64).reshape(-1)[:2]
        def _sample_cube_center(required_distance: float):
            for _ in range(max_cube_spawn_trials):
                exec_cube = exec_layout["cube_position_policy"]
                sampled_x = torch.rand(1, generator=self._hb_generator).item() * exec_cube["center_span"] + exec_cube["center_offset"]
                #direction = -1.0 if -self.peg2_basey < 0 else 1.0
                #sampled_y = torch.rand(1, generator=self._hb_generator).item() * 0.2 * direction
                sampled_y = torch.rand(1, generator=self._hb_generator).item()  * exec_cube["center_span"] + exec_cube["center_offset"]
                candidate_xy = np.array([sampled_x, sampled_y], dtype=np.float64)
                if np.linalg.norm(candidate_xy - goal_xy) > required_distance:
                    if exec_zone is not None and _zone_violated(exec_zone, candidate_xy):
                        zone_trials["execution"]["cube_candidate_center_rejects"] += 1
                        continue
                    return candidate_xy
            return None

        if xhard:
            zone_trials["execution"]["cube_candidate_center_rejects"] = 0

        cube_center = _sample_cube_center(self.cube_half_size*native_pos["cube_rejection"]["min_distance_factor"])
        if xhard and cube_center is None:
            # D3（只在 xhard 修，H2）：执行段同样修
            raise SceneGenerationError(
                f"MoveCube xhard：执行段方块中心 {max_cube_spawn_trials} 次拒绝采样全部失败")

        cube_x, cube_y = float(cube_center[0]), float(cube_center[1])
        # V5 xhard（L34）：执行段方块与演示段方块从不同时在场（cube_2 只取位姿，随即被传送走），
        # 不再把演示段方块当障碍（include_existing=False）；最终中心按禁区复查
        exec_cube_extra = {"include_existing": False, "center_exclusion": exec_zone["rule"]} if xhard else {}
        try:
            self.cube_2 = spawn_random_cube(
                            self,
                            region_center=[cube_x, cube_y],
                            color=(1, 0, 0, 1),
                            name_prefix="fixed_cube_2",
                            recorder=self._spec,
                            spec_path="layout.execution.cube_pose",
                            region_half_size=exec_layout["cube_position_policy"]["region_half_size"],
                            generator=self._hb_generator,
                            half_size=self.cube_half_size,
                            **exec_cube_extra,
                        )
        except RuntimeError as exc:
            if xhard and not isinstance(exc, SceneGenerationError):
                raise SceneGenerationError(f"MoveCube xhard：执行段方块生成失败：{exc}") from exc
            raise
        
        self.cube_init_pose_2=self.cube_2.pose
        #only need the pose! teleport away in 

        goal2_p = np.array(self.goal_site_2.pose.p.detach().cpu().numpy(), dtype=np.float64, copy=True)
        self.goal_site_2_pose_p = goal2_p

        goal2_q = np.array(self.goal_site_2.pose.q.detach().cpu().numpy(), dtype=np.float64, copy=True)
        self.goal_site_2_pose_q = goal2_q

        goal1_p = np.array(self.goal_site.pose.p.detach().cpu().numpy(), dtype=np.float64, copy=True)
        self.goal_site_1_pose_p = goal1_p

        goal1_q = np.array(self.goal_site.pose.q.detach().cpu().numpy(), dtype=np.float64, copy=True)
        self.goal_site_1_pose_q = goal1_q

        if xhard:
            # 只读记录本局实际生效的禁区规则与各拒绝循环的尝试次数（N18；不抽随机数，排在全部取值点之后）
            for seg, zone in (("demo", demo_zone), ("execution", exec_zone)):
                self._spec.record(f"layout.{seg}.center_exclusion", dict(zone["decision"], peg_axis_extent_m=list(peg_extent)))
                self._spec.record(f"layout.{seg}.center_exclusion_trials", dict(zone_trials[seg]))

    def _xhard_center_exclusion(self, layout, key):
        """取并校验 xhard 的桌面中心禁区（计划 2.9）；形状或数值不合法时拒绝，不许静默放宽。

        返回 dict：``rule`` 为传给 ``spawn_random_cube/target(center_exclusion=...)`` 的
        ``(center_xy, radius)``；``center``（(2,) float64）、``radius``、``max_trials`` 供杆与方块候选的
        本地判据使用；``decision`` 为原样的配置副本（写进规格留痕）。
        """
        cfg = layout["xhard"]["center_exclusion"]
        where = f"MoveCube xhard：decision.{key}.xhard.center_exclusion"
        if not isinstance(cfg, dict):
            raise SamplingConfigError(f"{where} 必须是字典，收到 {cfg!r}")
        if cfg.get("shape") != "circle":
            raise SamplingConfigError(f"{where}.shape 只支持 circle，收到 {cfg.get('shape')!r}")
        if cfg.get("judge") != "object_center":
            raise SamplingConfigError(f"{where}.judge 只支持 object_center，收到 {cfg.get('judge')!r}")
        try:
            center = np.asarray(cfg["center"], dtype=np.float64).reshape(-1)
            radius = float(cfg["radius_m"])
            max_trials = cfg["max_trials"]
        except (KeyError, TypeError, ValueError) as exc:
            raise SamplingConfigError(f"{where} 缺字段或类型不对：{exc}") from exc
        if center.shape != (2,) or not np.all(np.isfinite(center)):
            raise SamplingConfigError(f"{where}.center 必须是两个有限数，收到 {cfg['center']!r}")
        if not (np.isfinite(radius) and radius >= 0.0):
            raise SamplingConfigError(f"{where}.radius_m 必须是 ≥0 的有限数，收到 {cfg['radius_m']!r}")
        if isinstance(max_trials, bool) or not isinstance(max_trials, (int, np.integer)) or int(max_trials) < 1:
            raise SamplingConfigError(f"{where}.max_trials 必须是 ≥1 的整数，收到 {max_trials!r}")
        return {
            "rule": ((float(center[0]), float(center[1])), radius),
            "center": center,
            "radius": radius,
            "max_trials": int(max_trials),
            "decision": copy.deepcopy(cfg),
        }

    def _xhard_sample_peg_outside_zone(self, base_y, peg_policy, yaw_policy, zone, extent, seg_label):
        """V5 xhard：按原顺序抽 (x_jitter, y_jitter, yaw)，杆轴线段离禁区圆心最近点 < 半径就三者原地重抽。

        随机调用顺序与原路径相同（x、y、yaw 各一次 ``torch.rand``），只是被拒时整组重来；
        ``base_y`` 不重抽。只返回被接受的那组，``recorder.value`` 由调用方在其后照常调用（N18）。
        返回 ``(x_jitter, y_jitter, yaw, 尝试次数)``；超过 ``max_trials`` 抛真 ``SceneGenerationError``。
        """
        span = peg_policy["jitter_span"]
        for trial in range(1, zone["max_trials"] + 1):
            x_jitter = (torch.rand(1, generator=self._hb_generator).item() - 0.5) * span
            y_jitter = (torch.rand(1, generator=self._hb_generator).item() - 0.5) * span
            yaw = torch.rand(1, generator=self._hb_generator).item() * (yaw_policy["span_rad"]) - (yaw_policy["offset_rad"])
            if _peg_zone_distance(base_y, x_jitter, y_jitter, yaw, zone, extent) >= zone["radius"]:
                return x_jitter, y_jitter, yaw, trial
        raise SceneGenerationError(
            f"MoveCube xhard：{seg_label}杆 {zone['max_trials']} 次重抽全部落进桌面中心禁区")

    def _xhard_verify_peg_extent(self, extent):
        """用刚建好的杆的实际碰撞盒与可视盒复核禁区判据所用的轴线段区间（取二者并集）。

        读 head/tail 两个 link 的 box 形状半长、形状局部位姿与 tail 固定关节的 ``pose_in_parent``／``pose_in_child``，
        得到沿杆朝向（link 局部 x 轴）的实际区间；与 ``_peg_axis_extent`` 不一致就抛 RuntimeError
        （属代码类错误：说明 build_peg 的几何变了而判据没跟上）。
        """
        lo, hi = np.inf, -np.inf
        for link in (self.peg_head, self.peg_tail):
            comp = link._objs[0]
            joint = comp.get_joint()
            # 固定关节只有沿 x 的平移（build_peg）：link 原点在父 link 系的 x = pose_in_parent.x − pose_in_child.x
            offset = 0.0 if comp.get_parent() is None else (
                float(joint.get_pose_in_parent().p[0]) - float(joint.get_pose_in_child().p[0]))
            shapes = [(float(sh.half_size[0]), float(sh.local_pose.p[0])) for sh in comp.get_collision_shapes()]
            for c in comp.get_entity().get_components():
                for rs in getattr(c, "render_shapes", []) or []:
                    if hasattr(rs, "half_size"):
                        shapes.append((float(rs.half_size[0]), float(rs.local_pose.p[0])))
            if not shapes:
                raise RuntimeError(f"MoveCube xhard：杆 link {link.name} 没有可读的 box 形状，无法复核禁区杆轴线段")
            for half, local_x in shapes:
                lo = min(lo, offset + local_x - half)
                hi = max(hi, offset + local_x + half)
        if abs(lo - extent[0]) > 1e-6 or abs(hi - extent[1]) > 1e-6:
            raise RuntimeError(
                f"MoveCube xhard：禁区判据用的杆轴线段 {tuple(extent)} 与实际几何 ({lo}, {hi}) 不一致")

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        # 每次初始化各自记一份规格，不复用上一次的结果
        self._native_init_index = getattr(self, "_native_init_index", -1) + 1
        with torch.device(self.device):
            self.table_scene.initialize(env_idx)

            if not hasattr(self, "pegs"):
                return

            # Initialize all 3 pegs

            qpos = np.array(
            [
                0.0,
                0,
                0,
                -np.pi * 4 / 8,
                0,
                np.pi * 2 / 4,
                np.pi / 4,
                0.04,
                0.04,
            ],
            dtype=np.float32,
            )
            self.ways=["peg_push","gripper_push","grasp_putdown"]
            way_idx = self._spec.value(
                f"initializations.{getattr(self, '_native_init_index', 0)}.way_idx",
                torch.randint(len(self.ways), (1,), generator=self._hb_generator).item(),
            )
            self.way = self.ways[way_idx]
            #self.way="gripper_push"

            self.agent.reset(qpos)            
            if self.difficulty == "xhard":
                # B11：每次初始化清掉上一次抓杆的归约标记（由 grasp_and_lift_peg_side 重新设置）
                self._peg_grasp_flipped = False
                self._peg_grasp_flip_log = []
            self.cube_2.set_pose(sapien.Pose(p=[10,10,1]))#only need the pose!
            self.goal_site_2.set_pose(sapien.Pose(p=[10, -10, 1]))

            

    def evaluate(self,solve_complete_eval=False):
        timestep = self.elapsed_steps
        # flag=is_A_pickup_notB(self,self.peg_head,self.peg_tail)
        # flag2=is_A_pickup_notB(self,self.peg_tail,self.peg_head)
        # flag=is_A_insert_notB(self,self.peg_head,self.peg_tail,self.box)

        self.successflag=torch.tensor([False])
        self.failureflag = torch.tensor([False])
        

        self.obj_flag=-1
        if self.obj_flag==-1:
            self.grasp_target=self.peg_tail
            self.grasp_target_false=self.peg_head

        else:
            self.grasp_target=self.peg_head
            self.grasp_target_false=self.peg_tail

        self.direction1 = 1 if self.cube_init_pose.p[0][1]-self.goal_site_1_pose_p[0][1] > 0 else -1# relative position
        self.direction2 = 1 if self.cube_init_pose_2.p[0][1]-self.goal_site_2_pose_p[0][1]  > 0 else -1
        # direction -1 push from left 
        # direction 1 push from right +y side / table right side from camera view -> treated as push from right


        if self.way=="peg_push":
            tasks = [
                {
                "func": lambda: is_any_obj_pickup_flag_currentpickup(self, objects=[self.grasp_target,self.grasp_target_false]),
                "name": f"Pick up the peg",
                "subgoal_segment":f"Pick up the peg at <>",
                "choice_label": "pick up the peg",
                "demonstration": True,
                "failure_func":   lambda:[
                                           is_obj_pickup(self, obj=self.cube), 
                                           is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2),],
                "solve": lambda env, planner:grasp_and_lift_peg_side(env, planner, env.grasp_target),
                "segment":self.grasp_target
                },
                {
                "func": lambda:  is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2,must_gripper_open=True),
                "name": f"Hook the cube to the target with the peg",
                "subgoal_segment":f"Hook the cube at <> to the target at <> with the peg",
                "choice_label": "hook the cube to the target with the peg",
                "demonstration": True,
                "failure_func": lambda:None,
                "solve": lambda env, planner:solve_push_to_target_with_peg(env,planner,self.cube,self.goal_site,self.direction1,self.obj_flag),
                "segment":[self.cube,self.goal_site],
                },
                                                {
                "func": lambda: static_check(self, timestep=int(self.elapsed_steps), static_steps=30),
                "name": "static",
                "subgoal_segment":f"static",
                "demonstration": True,
                "failure_func": None,
                "solve": lambda env, planner: [solve_hold_obj(env, planner, static_steps=30)],
            },
                  {
                    "func": lambda:reset_check(self),
                    "name": "NO RECORD",
                    "subgoal_segment":f"NO RECORD",
                    "demonstration": True,
                    "failure_func": None,
                    "specialflag":"reset pegs",
                    "solve": lambda env, planner: [solve_strong_reset(env,planner)],
                    },
                
                {
                "func": lambda: is_any_obj_pickup_flag_currentpickup(self, objects=[self.grasp_target,self.grasp_target_false]),
                "name": "Pick up the peg",
                "subgoal_segment":f"Pick up the peg at <>",
                "choice_label": "pick up the peg",
                "demonstration": False,
                "failure_func":   lambda:[
                                           is_obj_pickup(self, obj=self.cube), 
                                           is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2),],
                "solve": lambda env, planner:grasp_and_lift_peg_side(env, planner, env.grasp_target),
                "segment":self.grasp_target
                },
                {
                "func": lambda:  is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2,must_gripper_open=True),
                "name": f"Hook the cube to the target with the peg",
                "subgoal_segment":f"Hook the cube at <> to the target at <> with the peg",
                "choice_label": "hook the cube to the target with the peg",
                "demonstration": False,
                "failure_func": lambda:None,
                "solve": lambda env, planner:solve_push_to_target_with_peg(env,planner,self.cube,self.goal_site,self.direction2,self.obj_flag),
                "segment":[self.cube,self.goal_site],
                },
                ]
            
            #test using gripper/grasp =false

        if self.way=="gripper_push":
            tasks = [{
                                "func": lambda: is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2,must_gripper_open=True),
                                "name": "Close the gripper and push the cube to the target",
                                "subgoal_segment":f"Close the gripper and push the cube at <> to the target at <>",
                                "choice_label": "close gripper and push the cube to the target",
                                "demonstration": True,
                                "failure_func":  lambda: [is_obj_pickup(self, obj=self.cube),
                                                          is_obj_pickup(self, obj=self.grasp_target),
                                                          is_obj_pickup(self, obj=self.grasp_target_false)],
                                "solve": lambda env, planner:solve_push_to_target(env,planner,self.cube,self.goal_site),
                                "segment":[self.cube,self.goal_site],
                                },
                                                                {
                "func": lambda: static_check(self, timestep=int(self.elapsed_steps), static_steps=60),
                "name": "static",
                "subgoal_segment":f"static",
                "demonstration": True,
                "failure_func": None,
                "solve": lambda env, planner: [solve_hold_obj(env, planner, static_steps=60)],
            },
                                {
                                "func": lambda:reset_check(self),
                                "name": "NO RECORD",
                                "subgoal_segment":f"NO RECORD",
                                "demonstration": True,
                                "failure_func": None,
                                "specialflag":"reset pegs",
                                "solve": lambda env, planner: [solve_strong_reset(env,planner)],
                                },
                                {
                                "func": lambda: is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2,must_gripper_open=True),
                                "name": "Close the gripper and push the cube to the target",
                                "subgoal_segment":f"Close the gripper and push the cube at <> to the target at <>",
                                "choice_label": "close gripper and push the cube to the target",
                                "demonstration": False,
                                "failure_func":  lambda: [is_obj_pickup(self, obj=self.cube),
                                                          is_obj_pickup(self, obj=self.grasp_target),
                                                          is_obj_pickup(self, obj=self.grasp_target_false)],
                                "solve": lambda env, planner:solve_push_to_target(env,planner,self.cube,self.goal_site),
                                "segment":[self.cube,self.goal_site],
                                },
                                
                                
                                ]
            
        if self.way=="grasp_putdown":
            tasks = [
                {
                        "func": lambda: is_obj_pickup(self, obj=self.cube),
                        "name": "Pick up the cube",
                        "subgoal_segment":f"Pick up the cube at <>",
                        "choice_label": "pick up the cube",
                        "demonstration": True,
                        "failure_func": lambda: [is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2), 
                                                 is_obj_pickup(self, obj=self.grasp_target),
                                                 is_obj_pickup(self, obj=self.grasp_target_false)],
                        "solve": lambda env, planner:[solve_pickup(env, planner, obj=self.cube),],
                        "segment":[self.cube],
                        },
                        {
                    "func": (lambda: is_obj_dropped_onto(self,obj=self.cube,target=self.goal_site)),
                    "name": "place the cube onto the target",
                    "subgoal_segment":f"place the cube onto the target at <>",
                    "choice_label": "place the cube onto the target",
                    "demonstration": True,
                    "failure_func":  None, 
                    "solve": lambda env, planner: [solve_putonto_whenhold(env, planner,target=self.goal_site)],
                                        "segment":[self.goal_site],
                                        },

                                {
                "func": lambda: static_check(self, timestep=int(self.elapsed_steps), static_steps=60),
                "name": "static",
                "subgoal_segment":f"static",
                "demonstration": True,
                "failure_func": None,
                "solve": lambda env, planner: [solve_hold_obj(env, planner, static_steps=60)],
            },
                                                    {
                                "func": lambda:reset_check(self),
                                "name": "NO RECORD",
                                "subgoal_segment":f"NO RECORD",
                                "demonstration": True,
                                "failure_func": None,
                                "specialflag":"reset pegs",
                                "solve": lambda env, planner: [solve_strong_reset(env,planner)],
                                },
                {
                        "func": lambda: is_obj_pickup(self, obj=self.cube),
                        "name": "Pick up the cube",
                        "subgoal_segment":f"Pick up the cube at <>",
                        "choice_label": "pick up the cube",
                        "demonstration": False,
                        "failure_func": lambda: [is_obj_pushed_onto(self,self.cube,self.goal_site,distance_threshold=self.cube_half_size*2*1.2), 
                                                 is_obj_pickup(self, obj=self.grasp_target),
                                                 is_obj_pickup(self, obj=self.grasp_target_false)],
                        "solve": lambda env, planner:[solve_pickup(env, planner, obj=self.cube),],
                        "segment":[self.cube],
                        },
                        {
                    "func": (lambda: is_obj_dropped_onto(self,obj=self.cube,target=self.goal_site)),
                    "name": "place the cube onto the target",
                    "subgoal_segment":f"place the cube onto the target at <>",
                    "choice_label": "place the cube onto the target",
                    "demonstration": False,
                    "failure_func":  None, 
                    "solve": lambda env, planner: [solve_putonto_whenhold(env, planner,target=self.goal_site)],
                                        "segment":[self.goal_site],
                                        },

            ]


                            


        # Store task list for RecordWrapper use
        self.task_list = tasks

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

        #allow_subgoal_change_this_timestep=True
        all_tasks_completed, current_task_name, task_failed,_ = sequential_task_check(self, tasks,allow_subgoal_change_this_timestep=allow_subgoal_change_this_timestep)

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


#Robomme
    def step(self, action: Union[None, np.ndarray, torch.Tensor, Dict]):


        obs, reward, terminated, truncated, info = super().step(action)
        timestep = int(info["elapsed_steps"])

            
        if self.reset_in_proecess==True:
            for i, peg in enumerate(self.pegs):
                peg.set_pose(self.peg_init_poses_2[i])
                if peg.dof > 0:
                    zero = np.zeros(peg.dof)
                    peg.set_qpos(zero)
                    peg.set_qvel(zero)

            self.cube.set_pose(self.cube_init_pose_2)
            #self.goal_site_2.set_pose(sapien.Pose(p=self.goal_site_2_pose_p[0],q=self.goal_site_2_pose_q[0]))
            goal2_p = np.array(self.goal_site_2_pose_p, copy=True)
            goal2_q = np.array(self.goal_site_2_pose_q, copy=True)
            self.goal_site.set_pose(sapien.Pose(p=goal2_p[0],q=goal2_q[0]))
            #print("reset goal site to",goal2_p[0],goal2_q[0])



        return obs, reward, terminated, truncated, info
