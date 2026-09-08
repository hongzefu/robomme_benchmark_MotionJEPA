"""直接基于 ManiSkill 构建场景，不执行原版任务的初始化或判定。"""

import copy
import itertools
import random
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import sapien
import torch
from mani_skill.envs.sapien_env import BaseEnv
from mani_skill.sensors.camera import CameraConfig
from mani_skill.utils import sapien_utils
from mani_skill.utils.scene_builder.table import TableSceneBuilder

from ..errors import SceneRejected, TaskExecutionError
from ..geometry.collision import actor_boxes, box_clearance, box_components, pose_at_step
from ..legacy_bridge import build_fixed_button, build_fixed_cube, initial_qpos
from ..tasks import TaskEvaluator, language_goal


def array(value):
    """对可复用物理缓冲区取得独立 NumPy 快照。"""
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.array(value, copy=True)


class ICLBaseEnv(BaseEnv):
    """单环境 CPU 物理、固定 GPU 渲染和按子步执行的安全检查。"""

    SUPPORTED_ROBOTS = ["panda_wristcam", "panda_stick"]
    TASK_KIND = None

    def __init__(self, *, episode_spec, **kwargs):
        from ..suite import EpisodeSpec

        self.episode_spec = episode_spec if isinstance(episode_spec, EpisodeSpec) else EpisodeSpec.from_dict(episode_spec)
        self.definition = self.episode_spec.to_dict()
        if self.TASK_KIND != self.definition["task_kind"]:
            raise ValueError("注册任务与场景清单的 task_kind 不一致")
        self.task_kind = self.definition["task_kind"]
        self.robot_kind = self.definition["robot_kind"]
        self.seed = self.definition["seed"]
        self.cube_half_size = .02
        self.use_demonstrationwrapper = False
        self.robot_init_qpos_noise = 0
        self.actor_definitions = {a["id"]: a for a in self.definition["actors"]}
        self.icl_actors = {}
        self.icl_buttons = {}
        self._parked = set()
        self._kinematic = set()
        self._forbidden_contacts = []
        self._phase = "initialization"
        self._evaluator = TaskEvaluator(self.episode_spec)
        self._task_result = {}
        self._evaluated_at = None
        self._substep = 0
        self._animation_enabled = False
        self._animation_step_origin = 0
        self._evaluation_origin = 0
        self._native_ready = False
        fixed = dict(num_envs=1, robot_uids=self.robot_kind, obs_mode="rgb", control_mode="pd_joint_pos",
                     render_mode="rgb_array", sim_backend="physx_cpu", render_backend="cuda:0",
                     enhanced_determinism=True, reward_mode="none",
                     sim_config={"sim_freq": self.definition["schedule"]["sim_freq"],
                                 "control_freq": self.definition["schedule"]["control_freq"], "scene_config": {
                         "enable_enhanced_determinism": True, "cpu_workers": 0}})
        for key, value in kwargs.items():
            if key in fixed and value != fixed[key]:
                raise ValueError(f"认证运行不允许覆盖固定参数 {key}")
            fixed[key] = value
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        super().__init__(**fixed)
        srdf = Path(self.agent.urdf_path).with_suffix(".srdf")
        self._allowed_robot_pairs = {frozenset((x.attrib["link1"], x.attrib["link2"]))
                                     for x in ET.parse(srdf).getroot().iter("disable_collisions")}
        self._native_ready = True

    @property
    def _default_sensor_configs(self):
        pose = sapien_utils.look_at(eye=[.3, 0, .4], target=[0, 0, -.2])
        return [CameraConfig("base_camera", pose, 256, 256, np.pi / 2, .01, 100)]

    def _load_agent(self, options):
        super()._load_agent(options, sapien.Pose(p=[-.615, 0, 0]))

    def _load_scene(self, options):
        self.table_scene = TableSceneBuilder(self, robot_init_qpos_noise=0)
        self.table_scene.build()
        for definition in self.definition["actors"]:
            kind = definition["kind"]
            if kind == "cube":
                obj = build_fixed_cube(self, definition)
            elif kind == "button":
                obj = build_fixed_button(self, definition)
                self.icl_buttons[definition["id"]] = obj
            else:
                builder = self.scene.create_actor_builder()
                material = sapien.render.RenderMaterial(base_color=definition.get("color", [.6, .6, .6, 1]))
                for part in box_components(definition, self.definition["geometry"]):
                    pose = sapien.Pose(part["position"], part.get("quaternion", [1, 0, 0, 0]))
                    if kind != "target":
                        builder.add_box_collision(pose=pose, half_size=part["half_size"])
                    builder.add_box_visual(pose=pose, half_size=part["half_size"], material=material)
                builder.set_initial_pose(sapien.Pose(definition["position"], definition["quaternion"]))
                obj = builder.build_dynamic(name=definition["id"]) if kind == "container" else builder.build_kinematic(name=definition["id"])
            self.icl_actors[definition["id"]] = obj

    def _initialize_episode(self, env_idx, options):
        random.seed(self.seed)
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)
        self._phase = "initialization"
        self._parked.clear()
        self._kinematic.clear()
        self._forbidden_contacts.clear()
        self._animation_enabled = False
        self._substep = 0
        self._evaluated_at = None
        self._evaluator.reset()
        self._task_result = {}
        self.table_scene.initialize(env_idx)
        self.agent.reset(initial_qpos(self.robot_kind)[None, :])
        self.agent.robot.set_pose(sapien.Pose([-.615, 0, 0]))
        for name, actor in self.icl_actors.items():
            definition = self.actor_definitions[name]
            if name in self.icl_buttons:
                actor.set_qpos(np.zeros((1, 1), dtype=np.float32))
                actor.set_qvel(np.zeros((1, 1), dtype=np.float32))
                continue
            actor.set_pose(sapien.Pose(definition["position"], definition["quaternion"]))
            if definition["kind"] in ("cube", "container"):
                body = actor._bodies[0]
                body.set_kinematic(False)
                body.set_linear_velocity([0, 0, 0])
                body.set_angular_velocity([0, 0, 0])

    def reset(self, seed=None, options=None):
        """每次从同一记录重新构建物理场景，清除 PhysX 接触求解历史。"""
        if self._native_ready and seed is not None and seed not in (self.seed, [self.seed]):
            raise ValueError("当前环境固定到一个 seed；其他 seed 请重新 make_env")
        options = dict(options or {})
        options["reconfigure"] = True
        if self._native_ready:
            self.icl_actors = {}
            self.icl_buttons = {}
        return super().reset(seed=self.seed, options=options)

    def _get_obs_extra(self, info):
        return {}

    def compute_dense_reward(self, obs, action, info):
        return torch.zeros(1)

    def park(self, name):
        """隐藏对象停在互不重叠的位置，保持其碰撞形状可检查。"""
        actor = self.icl_actors[name]
        idx = list(self.actor_definitions).index(name)
        body = actor._bodies[0]
        body.set_kinematic(True)
        body.set_linear_velocity([0, 0, 0])
        body.set_angular_velocity([0, 0, 0])
        actor.set_pose(sapien.Pose([10 + idx * .25, 10, 10]))
        self._parked.add(name)
        self._kinematic.add(name)

    def restore(self, name, pose=None):
        """在检查过的位置恢复对象；不得依赖之前隐藏时的速度。"""
        actor = self.icl_actors[name]
        definition = pose or self.actor_definitions[name]
        actor.set_pose(sapien.Pose(definition["position"], definition["quaternion"]))
        body = actor._bodies[0]
        body.set_kinematic(False)
        body.set_linear_velocity([0, 0, 0])
        body.set_angular_velocity([0, 0, 0])
        self._parked.discard(name)
        self._kinematic.discard(name)

    def snapshot(self):
        """只从物理观测提取判定输入，不让 oracle 直接修改计数。"""
        poses, linear, angular, grasped = {}, {}, {}, []
        for name, actor in self.icl_actors.items():
            p, q = array(actor.pose.p).reshape(-1, 3)[0], array(actor.pose.q).reshape(-1, 4)[0]
            poses[name] = {"position": p.tolist(), "quaternion": q.tolist()}
            if name in self.icl_buttons:
                linear[name] = angular[name] = [0., 0., 0.]
            else:
                linear[name] = array(actor.linear_velocity).reshape(-1, 3)[0].tolist()
                angular[name] = array(actor.angular_velocity).reshape(-1, 3)[0].tolist()
            if self.actor_definitions[name]["kind"] in ("cube", "container") and self.robot_kind != "panda_stick" and name not in self._parked:
                if bool(self.agent.is_grasping(actor).item()):
                    grasped.append(name)
        return {"step": int(self.elapsed_steps.item()), "poses": poses,
                "linear_velocities": linear, "angular_velocities": angular,
                "grasped_ids": grasped,
                "button_pressed": any(float(array(b.get_qpos()).reshape(-1)[0]) < -.005 for b in self.icl_buttons.values()),
                "tcp_position": array(self.agent.tcp.pose.p).reshape(-1, 3)[0].tolist(),
                "forbidden_collision": bool(self._forbidden_contacts), "phase": self._phase}

    def evaluate(self):
        if not self._native_ready or self._phase == "initialization":
            return {"success": torch.tensor([False]), "fail": torch.tensor([False])}
        key = (self._phase, int(self.elapsed_steps.item()))
        if key != self._evaluated_at:
            self._task_result = self._evaluator.update(self.snapshot())
            self._evaluated_at = key
        return {"success": torch.tensor([bool(self._task_result.get("success", False) and not self._forbidden_contacts)]),
                "fail": torch.tensor([bool(self._task_result.get("fail", False) or self._forbidden_contacts)])}

    def set_phase(self, phase):
        """演示和执行使用分开的判定生命周期，演示不能累计执行次数。"""
        if self._forbidden_contacts or self._task_result.get("fail"):
            raise TaskExecutionError("前一阶段已失败，禁止切换阶段清除失败记录")
        self._phase = phase
        self._evaluator.reset()
        self._task_result = {}
        self._evaluated_at = None
        if phase == "evaluation":
            self._evaluation_origin = int(self.elapsed_steps.item())
            if self.task_kind == "BinFill":
                for name, reveal_step in self.definition["task_parameters"].get("reveal_steps_by_id", {}).items():
                    if reveal_step > 0:
                        self.park(name)

    def begin_animation(self):
        self._animation_enabled = True
        self._animation_step_origin = int(self.elapsed_steps.item())
        self._substep = 0

    def _before_control_step(self):
        self._substep = 0
        if self._phase == "evaluation" and self.task_kind == "BinFill":
            now = int(self.elapsed_steps.item()) - self._evaluation_origin
            inserted = self._task_result.get("inserted_ids", [])
            for name, reveal_step in self.definition["task_parameters"].get("reveal_steps_by_id", {}).items():
                if name in self._parked and name not in inserted and now >= reveal_step:
                    self.restore(name)

    def _before_simulation_step(self):
        self._substep += 1
        if not self._animation_enabled:
            return
        time = int(self.elapsed_steps.item()) - self._animation_step_origin + self._substep / self._sim_steps_per_control
        poses = pose_at_step(self.episode_spec, time)
        for name, actor in self.icl_actors.items():
            if self.actor_definitions[name]["kind"] not in ("cube", "container") or name in self._parked:
                continue
            body = actor._bodies[0]
            body.set_kinematic(True)
            self._kinematic.add(name)
            pose = poses[name]
            body.set_kinematic_target(sapien.Pose(pose["position"], pose["quaternion"]))

    def finish_animation(self):
        self._animation_enabled = False
        end = max((item["end_step"] for item in self.definition["swaps"]), default=0)
        endpoints = pose_at_step(self.episode_spec, end)
        # 切回动态刚体的顺序也属于确定性协议，不能遍历进程随机排序的 set。
        # 端点使用清单中的精确值，不回采刚体求解器的末帧近似位姿。
        for name in sorted(self._kinematic - self._parked):
            self.restore(name, endpoints[name])

    def _allowed_contact(self, a, b):
        if a == b:
            return True
        definitions = self.actor_definitions
        for first, second in ((a, b), (b, a)):
            if first in ("table-workspace", "ground", "table") and second in definitions:
                return True
            if first in definitions and definitions[first]["kind"] == "button" and second in definitions and definitions[second]["kind"] == "button":
                return True
            if first in definitions and definitions[first]["kind"] == "board" and second in definitions and definitions[second]["kind"] == "cube":
                return self.task_kind == "BinFill"
            if "finger" in first and second in definitions:
                parameters = self.definition["task_parameters"]
                allowed = parameters.get("target_container_ids", []) if self.task_kind == "VideoUnmaskSwap" else parameters.get("target_ids", [])
                if self.task_kind == "BinFill":
                    allowed = [x["id"] for x in definitions.values() if x["kind"] == "cube" and x.get("color_name") in parameters.get("target_counts", {})]
                return second in allowed or definitions[second]["kind"] == "button"
        # 只允许明确的机械结构接触；不能把所有未列出的机器人碰撞放行。
        if frozenset((a, b)) in self._allowed_robot_pairs:
            return True
        support = {"table-workspace", "ground", "table"}
        if a in support and b in support:
            return True
        return (a == "panda_link0" and b in support) or (b == "panda_link0" and a in support)

    def _after_simulation_step(self):
        if not self._native_ready or self._phase == "initialization":
            return
        try:
            contacts = self.scene.get_contacts()
        except Exception as exc:
            raise RuntimeError("无法读取 CPU 物理接触，拒绝继续认证") from exc
        body_names = {}
        for name, actor in self.icl_actors.items():
            if name in self.icl_buttons:
                for link in actor.get_links():
                    for body in link._bodies:
                        body_names[body.entity.name] = name
            else:
                for body in actor._bodies:
                    body_names[body.entity.name] = name
        for contact in contacts:
            names = [body_names.get(body.entity.name, body.entity.name.removeprefix("scene-0_")) for body in contact.bodies]
            if self._allowed_contact(*names):
                continue
            if any(float(p.separation) < -1e-5 or np.linalg.norm(p.impulse) > 1e-8 for p in contact.points):
                self._forbidden_contacts.append({"bodies": names, "step": int(self.elapsed_steps.item()), "substep": self._substep})
        # Kinematic 对可能没有接触回报；逐子步另查真实位置的 compound OBB。
        if self._animation_enabled:
            poses = self.snapshot()["poses"]
            active = [x for x in self.definition["actors"] if x["id"] not in self._parked and x["kind"] != "target"]
            for a, b in itertools.combinations(active, 2):
                gap = min(box_clearance(x, y) for x in actor_boxes(a, self.definition["geometry"], poses[a["id"]]) for y in actor_boxes(b, self.definition["geometry"], poses[b["id"]]))
                if gap < -1e-5:
                    self._forbidden_contacts.append({"bodies": [a["id"], b["id"]], "geometry_gap": gap})

    def normalized_observation(self, raw):
        sensors = raw["sensor_data"]
        snap = self.snapshot()
        return {"base_rgb": array(sensors["base_camera"]["rgb"])[0],
                "wrist_rgb": array(sensors["hand_camera"]["rgb"])[0],
                "qpos": array(self.agent.robot.get_qpos())[0],
                "qvel": array(self.agent.robot.get_qvel())[0],
                "actor_poses": {k: np.array(v["position"] + v["quaternion"], dtype=np.float32) for k, v in snap["poses"].items()}}

    def normalized_info(self):
        native = self.evaluate()
        return {"success": bool(native["success"].item()), "fail": bool(native["fail"].item()),
                "is_demonstration": self._phase == "demonstration", "phase": self._phase,
                "task_goal": language_goal(self.episode_spec),
                "step": int(self.elapsed_steps.item()), "task_events": copy.deepcopy(self._task_result),
                "forbidden_contacts": copy.deepcopy(self._forbidden_contacts)}
