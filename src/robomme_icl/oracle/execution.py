"""固定路径和计算预算的 oracle；每个物理动作都通过新版环境判定。"""

import copy

import numpy as np
import sapien
from mani_skill.examples.motionplanning.panda.motionplanner import PandaArmMotionPlanningSolver
from mani_skill.examples.motionplanning.panda.motionplanner_stick import PandaStickMotionPlanningSolver
from mani_skill.examples.motionplanning.base_motionplanner.utils import get_actor_obb, compute_grasp_info_by_obb

from ..errors import TaskExecutionError
from ..envs.base import array


class _EpisodeComplete(Exception):
    """内部流程信号：记录第一次成功后立即结束，避免终止后继续步进。"""


def frame_record(observation, action, info):
    """保存独立快照；不将 reset 的演示列表再次嵌入单帧。"""
    return {"observation": copy.deepcopy(observation),
            "joint_action": None if action is None else np.array(action, dtype=np.float64, copy=True),
            "info": copy.deepcopy({k: v for k, v in info.items() if k != "demonstration"})}


class _ActionSink:
    """为规划器提供会记录并立即检查任务失败的 step。"""

    def __init__(self, oracle):
        self.oracle = oracle
        self.unwrapped = oracle.base

    def step(self, action):
        return self.oracle.step(action)


class _StrictScrew:
    """禁止失败后继续执行，禁止自动转入墙钟 RRT。"""

    def move_to_pose_with_screw(self, pose, dry_run=False, refine_steps=5):
        result = super().move_to_pose_with_screw(pose, dry_run=True)
        if not isinstance(result, dict) or result.get("status") != "Success":
            raise TaskExecutionError("固定 screw 规划失败")
        if not np.isfinite(result["position"]).all():
            raise TaskExecutionError("规划关节值不是有限数")
        return result if dry_run else self.follow_path(result, refine_steps=refine_steps)

    def move_to_pose_with_RRTStar(self, *args, **kwargs):
        raise TaskExecutionError("严格模式禁止墙钟 RRT")

    def move_to_pose_with_RRTConnect(self, *args, **kwargs):
        raise TaskExecutionError("严格模式禁止墙钟 RRT")


class _ArmPlanner(_StrictScrew, PandaArmMotionPlanningSolver):
    """固定 screw 的双指规划器。"""


class _StickPlanner(_StrictScrew, PandaStickMotionPlanningSolver):
    """固定 screw 的 stick 规划器。"""


class Oracle:
    """任务的目标来源于不可变说明单；计数仅由环境真实观测推进。"""

    def __init__(self, env):
        self.env = env
        self.base = env.unwrapped
        self.definition = self.base.definition
        self.parameters = self.definition["task_parameters"]
        self.frames = []
        self._sink = _ActionSink(self)
        planner_cls = _StickPlanner if self.base.robot_kind == "panda_stick" else _ArmPlanner
        pose = self.base.agent.robot.pose
        self.planner = planner_cls(self._sink, vis=False, print_env_info=False,
                                   base_pose=sapien.Pose(array(pose.p)[0], array(pose.q)[0]))

    def step(self, action):
        out = self.env.step(action)
        observation, _, terminated, truncated, info = out
        self.frames.append(frame_record(observation, action, info))
        if info["fail"]:
            raise TaskExecutionError(f"真实任务失败: {info['task_events']}; contacts={info['forbidden_contacts'][:3]}")
        if truncated:
            raise TaskExecutionError("任务超出最大控制步")
        if info["success"]:
            raise _EpisodeComplete()
        return out

    def hold(self, count):
        q = array(self.base.agent.robot.get_qpos())[0, :7]
        action = q if self.base.robot_kind == "panda_stick" else np.r_[q, self.planner.gripper_state]
        for _ in range(int(count)):
            self.step(action)

    def move(self, position, quaternion=None):
        if quaternion is None:
            quaternion = array(self.base.agent.tcp.pose.q)[0]
        return self.planner.move_to_pose_with_screw(sapien.Pose(position, quaternion))

    def pickup(self, name):
        """从实际物体 OBB 构建抓取姿态，固定接近、闭合和提升路径。"""
        if name in self.base._parked:
            reveal = self.parameters.get("reveal_steps_by_id", {}).get(name)
            if reveal is None:
                raise TaskExecutionError(f"目标 {name} 仍在不可操作的隐藏阶段")
            remaining = reveal - (int(self.base.elapsed_steps.item()) - self.base._evaluation_origin)
            self.hold(max(1, remaining + 1))
        obj = self.base.icl_actors[name]
        self.planner.open_gripper(t=8)
        obb = get_actor_obb(obj)
        closing = array(self.base.agent.tcp.pose.to_transformation_matrix())[0, :3, 1]
        grasp = compute_grasp_info_by_obb(obb, approaching=np.array([0., 0., -1.]), target_closing=closing, depth=.025)
        pose = self.base.agent.build_grasp_pose(np.array([0., 0., -1.]), grasp["closing"], array(obj.pose.p)[0])
        position = np.array(pose.p, copy=True)
        is_container = self.base.actor_definitions[name]["kind"] == "container"
        approach = position.copy(); approach[2] = .22
        self.move(approach, pose.q)
        if is_container:
            position[2] += .01
        self.move(position, pose.q)
        self.planner.close_gripper(t=10)
        lifted = array(obj.pose.p)[0]; lifted[2] = .22 if is_container else .18
        self.move(lifted, pose.q)
        self.hold(4)
        if name not in self.base.snapshot()["grasped_ids"]:
            raise TaskExecutionError(f"未真正抓住 {name}")

    def putdown(self, name, xy=None):
        """保持当前夹爪与物体相对位姿，落回指定桌面位置。"""
        obj = self.base.icl_actors[name]
        actual = array(obj.pose.p)[0]
        tcp = array(self.base.agent.tcp.pose.p)[0]
        target = self.base.actor_definitions[name]["position"]
        # 在孔口／桌面上方释放，避免夹爪随方块进入狭窄孔内撞到边框。
        # 最终落稳和入孔仍由物理状态判断，不以这段规划的终点代替。
        desired = np.array([*(xy if xy is not None else actual[:2]), target[2] + .060], dtype=float)
        tcp_goal = tcp + desired - actual
        approach = tcp_goal.copy(); approach[2] = max(.22, tcp_goal[2]+.12)
        self.move(approach)
        self.move(tcp_goal)
        self.planner.open_gripper(t=10)
        self.move(approach)
        self.hold(12)

    def press_button(self):
        """根据固定按钮的真实 cap 高度按下，再由关节位移判定完成。"""
        name = next(iter(self.base.icl_buttons))
        p = np.array(self.base.actor_definitions[name]["position"], dtype=float)
        self.planner.close_gripper(t=6)
        p[2] = .18
        self.move(p)
        p[2] = .026
        self.move(p)
        self.hold(8)

    def _reset_robot(self):
        from ..legacy_bridge import initial_qpos
        self.base.agent.reset(initial_qpos(self.base.robot_kind)[None, :])
        self.planner.gripper_state = 1

    def _swap_demonstration(self, hide_contents):
        swaps = self.definition["swaps"]
        start = swaps[0]["start_step"] if swaps else self.definition["schedule"]["swap_start_step"]
        if hide_contents:
            for name, definition in self.base.actor_definitions.items():
                if definition["kind"] == "container":
                    self.base.park(name)
        self.base.begin_animation()
        self.hold(start)
        if hide_contents:
            for name, definition in self.base.actor_definitions.items():
                if definition["kind"] == "cube":
                    self.base.park(name)
                elif definition["kind"] == "container":
                    self.base.restore(name)
        end = swaps[-1]["end_step"] if swaps else start
        self.hold(end-start)
        self.base.finish_animation()
        if hide_contents:
            from ..geometry import pose_at_step
            final = pose_at_step(self.base.episode_spec, end)
            for name, definition in self.base.actor_definitions.items():
                if definition["kind"] == "cube":
                    self.base.restore(name, final[name])
        self.hold(self.definition["schedule"].get("settle_steps", 10))

    def _route_start(self):
        first = self.parameters["path_indices"][0]
        p = np.array(self.base.actor_definitions[f"target_{first}"]["position"], dtype=float)
        p[2] = .25
        self.move(p)
        p[2] = .07
        self.move(p)
        self.hold(4)

    def _route(self):
        """每个 waypoint 只做一次固定初值 CLIK；失败不能跳过。"""
        path = self.parameters["path_indices"]
        planner = self.planner.planner
        qpos = planner.pad_qpos(array(self.base.agent.robot.get_qpos())[0])
        rotation = array(self.base.agent.tcp.pose.q)[0]
        for edge, (a, b) in enumerate(zip(path, path[1:])):
            start = np.array(self.base.actor_definitions[f"target_{a}"]["position"][:2])
            end = np.array(self.base.actor_definitions[f"target_{b}"]["position"][:2])
            delta = end-start
            normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
            control = (start+end)/2 + normal * .1 * self.parameters["directions"][edge]
            for t in np.linspace(0, 1, 45):
                xy = (1-t)**2*start + 2*(1-t)*t*control + t*t*end
                world = np.r_[xy, .07, rotation]
                goal = planner.transform_goal_to_wrt_base(world)
                result, success, _ = planner.pinocchio_model.compute_IK_CLIK(
                    planner.move_group_link_id, goal, qpos, mask=[], eps=1e-5,
                    max_iter=1000, dt=.1, damp=1e-12)
                if not success or not np.isfinite(result).all() or not planner.wrap_joint_limit(result):
                    raise TaskExecutionError(f"RouteStick 第 {edge} 段固定 CLIK 失败")
                planner.planning_world.set_qpos_all(result[planner.move_group_joint_indices])
                if planner.planning_world.collide_full():
                    raise TaskExecutionError("RouteStick 关节路径发生规划自碰撞")
                planner.pinocchio_model.compute_forward_kinematics(result)
                recovered = planner.pinocchio_model.get_link_pose(planner.move_group_link_id)
                if planner.distance_6D(goal[:3], goal[3:], recovered[:3], recovered[3:]) >= 1e-3:
                    raise TaskExecutionError("RouteStick CLIK 的 FK 误差超出固定阈值")
                qpos = result
                self.step(np.asarray(qpos[:7]))
            self.hold(5)

    def demonstrate(self):
        """演示在 reset 内完成；返回的每一帧都来自真实仿真。"""
        # 先检查完整初始场景，不能先停车再掩盖初始机器人碰撞。
        self.hold(1)
        kind = self.base.task_kind
        if kind == "VideoUnmaskSwap":
            self._swap_demonstration(hide_contents=True)
        elif kind == "VideoRepick":
            target = self.parameters["target_ids"][0]
            self.pickup(target)
            self.putdown(target, self.base.actor_definitions[target]["position"][:2])
            self._reset_robot()
            for name, definition in self.base.actor_definitions.items():
                if definition["kind"] == "cube":
                    self.base.restore(name)
            self._swap_demonstration(hide_contents=False)
        elif kind == "RouteStick":
            self._route_start()
            self._route()
            self._reset_robot()
            self._route_start()
        else:
            self.hold(3)
        if self.base._forbidden_contacts:
            raise TaskExecutionError("演示产生非预期碰撞")
        return self.frames

    def execute(self):
        kind = self.base.task_kind
        if kind == "BinFill":
            board = self.base.actor_definitions["board"]
            for target in self.parameters["target_ids"]:
                self.pickup(target)
                self.putdown(target, board["position"][:2])
                if target not in self.base._task_result["inserted_ids"]:
                    raise TaskExecutionError(f"{target} 未经真实入孔判定")
            self.press_button()
        elif kind == "VideoUnmaskSwap":
            targets = self.parameters["target_container_ids"]
            for i, target in enumerate(targets):
                self.pickup(target)
                if i+1 < len(targets):
                    self.putdown(target)
        elif kind == "VideoRepick":
            target = self.parameters["target_ids"][0]
            for _ in range(self.parameters["repeat_count"]):
                self.pickup(target)
                self.putdown(target)
            self.press_button()
        elif kind == "RouteStick":
            self._route()
        self.hold(3)
        info = self.base.normalized_info()
        if not info["success"] or info["fail"]:
            raise TaskExecutionError(f"任务未完成: {info['task_events']}")
        return self.frames


def run_episode(env):
    """完成演示与执行，返回记录器约定的完整帧序列。"""
    observation, info = env.reset()
    frames = list(info["demonstration"])
    frames.append(frame_record(observation, None, info))
    oracle = Oracle(env)
    try:
        oracle.execute()
    except _EpisodeComplete:
        pass
    frames.extend(oracle.frames)
    return frames
