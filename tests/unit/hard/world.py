"""CPU 世界替身：机械臂（夹持、TCP、关节）、按钮关节、时钟；驱动任务类**真实的** ``evaluate``／``step``。

真实谓词（``is_obj_pickup``、``is_obj_dropped_onto``、``is_button_pressed``、``static_check`` …）读的是
``actor.pose``、``agent.is_grasping(obj)``、``agent.tcp.pose``、``agent.robot.get_qvel()``、按钮 ``get_qpos()``
与 ``elapsed_steps``；本替身只提供这些状态，谓词与任务表本身全部走生产代码。

``BaseEnv.step`` 换成最小替身（时钟加一 → ``evaluate()`` → 按 success／fail 给 terminated），任务类覆写的
``step`` 前后处理照常执行。
"""
from __future__ import annotations

import contextlib
from types import SimpleNamespace

import numpy as np
import sapien
import torch

from mani_skill.envs.sapien_env import BaseEnv
from mani_skill.utils.structs.pose import Pose

from robomme_hard.robomme_env.utils import reset_panda

from . import offline_scene as O

TABLE_Z = 0.02  # 方块落桌时的中心高度量级（只用作「放下」时的 z，判定阈值取自生产谓词本身）
LIFT_Z = 0.12  # 抬起后的高度：高于 is_obj_pickup 的 0.05 与 is_bin_pickup 的 0.15 之下由调用方另给
TCP_UP_Z = 0.25


def _pose_at(xyz, q=(1.0, 0.0, 0.0, 0.0)) -> Pose:
    return Pose.create_from_pq(torch.tensor([list(map(float, xyz))], dtype=torch.float32),
                               torch.tensor([list(map(float, q))], dtype=torch.float32))


#: 机械臂基座位姿（ManiSkill TableSceneBuilder.initialize 把 Panda 放在 x=-0.615 处；InsertPeg 读它定朝向）
ROBOT_BASE_XYZ = (-0.615, 0.0, 0.0)


class FakeRobot:
    def __init__(self):
        self.pose = _pose_at(ROBOT_BASE_XYZ)
        self.qpos = torch.zeros((1, 9), dtype=torch.float32)
        self.qvel = torch.zeros((1, 9), dtype=torch.float32)

    def get_qpos(self):
        return self.qpos

    def get_qvel(self):
        return self.qvel

    def set_qpos(self, qpos):
        self.qpos = torch.as_tensor(qpos, dtype=torch.float32).reshape(1, -1)

    def set_qvel(self, qvel):
        self.qvel = torch.as_tensor(qvel, dtype=torch.float32).reshape(1, -1)


class FakeAgent:
    def __init__(self):
        self.robot = FakeRobot()
        self.tcp = SimpleNamespace(pose=_pose_at((0.0, 0.0, TCP_UP_Z)))
        self.held = None

    @property
    def tcp_pose(self):
        return self.tcp.pose

    def reset(self, qpos=None):
        if qpos is not None:
            self.robot.set_qpos(qpos)

    def is_grasping(self, obj, *a, **k):
        return torch.tensor([obj is self.held])


def _fake_base_step(self, action=None):
    """``BaseEnv.step`` 替身：时钟加一、调真实 ``evaluate``，按 success／fail 给 terminated。"""
    self._elapsed_steps = self._elapsed_steps + 1
    info = self.evaluate()
    info = dict(info)
    info["elapsed_steps"] = self._elapsed_steps
    terminated = bool(torch.as_tensor(info["success"]).any() or torch.as_tensor(info["fail"]).any())
    return None, 0.0, terminated, False, info


@contextlib.contextmanager
def cpu_world():
    """离线场景 + ``BaseEnv.step`` 替身（``elapsed_steps`` 是 BaseEnv 的只读属性，读 ``_elapsed_steps``）。"""
    with O.offline_scene():
        saved = BaseEnv.__dict__["step"]
        BaseEnv.step = _fake_base_step
        try:
            yield
        finally:
            BaseEnv.step = saved


class World:
    """一局 CPU 世界：建好任务（离线 ``_load_scene`` + ``_initialize_episode``），提供手写事件的原语。"""

    def __init__(self, env):
        self.env = env
        self.agent = FakeAgent()
        env.agent = self.agent
        env._elapsed_steps = torch.tensor([0], dtype=torch.int32)
        self.agent.reset(reset_panda.get_reset_panda_param("qpos"))

    # ── 构建 ────────────────────────────────────────────────────────────
    @classmethod
    def from_env(cls, env, *, demo: bool = False):
        """对已跑过 ``_load_scene`` 的 env 跑两次真实 ``_initialize_episode``：评估链里 ``gym.make`` 时
        BaseEnv 自带一次 reset（含 reconfigure → ``_load_scene``），评估再 reset 一次，所以初始化恰好两次
        （包内规格的 ``initializations.0``／``.1`` 两段即由此而来）。"""
        world = cls(env)
        for _ in range(2):
            env._initialize_episode(torch.arange(1), {})
        env.use_demonstrationwrapper = demo
        env.demonstration_record_traj = False
        return world

    @classmethod
    def build(cls, task: str, tier: str, k: int = 0, *, demo: bool = False, spec=None):
        """包内第 k 个正式局的规格回放建场（与评估链同参数），再跑两次真实 ``_initialize_episode``。"""
        header, rows = O.delivered_rows(task, tier, k + 1)
        row = rows[k]
        env = O.make_offline(task, seed=row["seed"], difficulty=tier,
                             sampling_config=header["sampling_config"][task],
                             spec=row["spec"] if spec is None else spec)
        return cls.from_env(env, demo=demo)

    # ── 原语 ────────────────────────────────────────────────────────────
    @staticmethod
    def xyz(actor) -> np.ndarray:
        return actor.pose.p[0].detach().cpu().numpy().astype(np.float64)

    def move(self, actor, xyz, q=None):
        q = q if q is not None else actor.pose.q[0].tolist()
        actor.set_pose(sapien.Pose(p=[float(v) for v in xyz], q=[float(v) for v in q]))

    def tcp_to(self, xyz):
        self.agent.tcp.pose = _pose_at(xyz)

    def grasp(self, actor, z=LIFT_Z):
        """抓起并抬到 z：夹持该物体、TCP 跟到物体处。"""
        x, y, _ = self.xyz(actor)
        self.move(actor, (x, y, z))
        self.agent.held = actor
        self.tcp_to((x, y, z))

    def release_onto(self, actor, xy, z=TABLE_Z):
        """在 xy 处松手落桌、TCP 抬高离开。"""
        self.move(actor, (xy[0], xy[1], z))
        if self.agent.held is actor:
            self.agent.held = None
        self.tcp_to((xy[0], xy[1], TCP_UP_Z))

    def press(self, button, depth=None):
        """按钮按下：关节位置 = -depth（生产 ``get_button_depth`` 取负）；缺省按到行程底。"""
        travel = float(getattr(self.env, "button_travel", 0.0) or 0.0)
        d = travel if depth is None else depth
        button.set_qpos([-d])

    def unpress(self, button):
        button.set_qpos([0.0])

    def still(self):
        self.agent.robot.set_qvel(torch.zeros((1, 9)))

    def moving(self):
        self.agent.robot.set_qvel(torch.ones((1, 9)))

    # ── 推进 ────────────────────────────────────────────────────────────
    def evaluate(self, solve_complete_eval=False) -> dict:
        info = self.env.evaluate(solve_complete_eval=solve_complete_eval)
        return {"success": bool(torch.as_tensor(info["success"]).any()),
                "fail": bool(torch.as_tensor(info["fail"]).any())}

    def tick(self, n: int = 1) -> dict:
        """时钟推进 n 步（每步 evaluate 一次）；返回最后一步的 success／fail。"""
        out = None
        for _ in range(n):
            self.env._elapsed_steps = self.env._elapsed_steps + 1
            out = self.evaluate()
        return out

    def step(self, n: int = 1) -> dict:
        """经任务类真实 ``step``（其前后处理照常执行）推进 n 步；返回最后一步的 success／fail。"""
        out = None
        for _ in range(n):
            _, _, _, _, info = self.env.step(None)
            out = {"success": bool(torch.as_tensor(info["success"]).any()),
                   "fail": bool(torch.as_tensor(info["fail"]).any())}
        return out

    @property
    def stage(self) -> int:
        """sequential_task_check 的当前任务序号（生产属性 ``timestep``）。"""
        return int(getattr(self.env, "timestep", 0))
