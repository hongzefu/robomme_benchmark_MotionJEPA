"""joint_angle接口只适配输入输出；演示、额外终止步及任务判定沿用原版。"""

import copy

import gymnasium as gym
import numpy as np

from ..execution.recording import RecordingEnv
from ..io.observations import normalized_info, normalized_observation
from ..native.imports import DemonstrationWrapper, task_goal


class ICLJointAngleEnv(gym.Wrapper):
    def __init__(self, raw_factory, *, task_kind, seed, record_demonstration=True):
        self.raw_factory = raw_factory
        self.task_kind = task_kind
        self.seed = seed
        self.record_demonstration = record_demonstration
        self.action_dimension = 7 if task_kind == "RouteStick" else 8
        self.has_reset = False
        self._build_wrappers()
        super().__init__(self.native_wrapper)

    def _build_wrappers(self):
        self.recorder = RecordingEnv(self.raw_factory())
        self.native_wrapper = DemonstrationWrapper(
            self.recorder, max_steps_without_demonstration=10000, gui_render=False,
            include_maniskill_obs=True,
        )

    def reset(self, *, seed=None, options=None):
        if seed is not None and seed != self.seed:
            raise ValueError("环境固定到一个seed；其他seed请重新make_env")
        if self.has_reset:
            self.native_wrapper.close()
            self._build_wrappers()
            self.env = self.native_wrapper
        batch, native_info = self.native_wrapper.reset(seed=self.seed, options=options)
        self.has_reset = True
        marker = self.recorder.reset_marker()
        if hasattr(self, "geometry_report"):
            marker["info"]["geometry_report"] = copy.deepcopy(self.geometry_report)
        info = copy.deepcopy(marker["info"])
        goals = task_goal.get_language_goal(self.native_wrapper, self.task_kind)
        info["task_goal"] = goals
        info["demonstration"] = copy.deepcopy(self.recorder.frames[:-1]) if self.record_demonstration else []
        observation = normalized_observation(batch["maniskill_obs"][-1], self.unwrapped)
        return observation, info

    def step(self, action):
        value = np.asarray(action, dtype=np.float64)
        if value.shape != (self.action_dimension,) or not np.isfinite(value).all():
            raise ValueError(f"joint_angle 必须是{self.action_dimension}维有限数组")
        batch, reward, terminated, truncated, native_info = self.native_wrapper.step(value)
        # 原版终止时会额外执行一步，但返回外层调用的图像，不能替换为内部末帧。
        observation = normalized_observation(batch["maniskill_obs"][-1], self.unwrapped)
        info = normalized_info(native_info, self.unwrapped)
        info["task_goal"] = native_info["task_goal"]
        return observation, float(reward), bool(terminated), bool(truncated), info
