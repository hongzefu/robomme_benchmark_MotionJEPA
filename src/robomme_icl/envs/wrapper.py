"""只封装 joint_angle 的新版 Gym 接口，演示由新版 oracle 生成。"""

import gymnasium as gym
import numpy as np

from ..errors import TaskExecutionError


class ICLJointAngleEnv(gym.Wrapper):
    """固定动作维度；reset 的演示和执行阶段使用明确边界。"""

    def __init__(self, env, *, record_demonstration=True):
        super().__init__(env)
        self.record_demonstration = record_demonstration
        self.action_dimension = 7 if self.unwrapped.robot_kind == "panda_stick" else 8
        self._last_observation = None

    def reset(self, *, seed=None, options=None):
        from ..oracle import Oracle

        raw, _ = self.env.reset(seed=seed, options=options)
        base = self.unwrapped
        base.set_phase("demonstration")
        self._last_observation = base.normalized_observation(raw)
        oracle = Oracle(self)
        demonstration = oracle.demonstrate()
        base.set_phase("evaluation")
        raw = base.get_obs()
        self._last_observation = base.normalized_observation(raw)
        info = base.normalized_info()
        info["demonstration"] = demonstration if self.record_demonstration else []
        return self._last_observation, info

    def step(self, action):
        a = np.asarray(action, dtype=np.float64)
        if a.shape != (self.action_dimension,) or not np.isfinite(a).all():
            raise ValueError(f"joint_angle 必须是 {self.action_dimension} 维有限数组")
        raw, reward, terminated, truncated, _ = self.env.step(a)
        base = self.unwrapped
        self._last_observation = base.normalized_observation(raw)
        info = base.normalized_info()
        # 方块已被独立判定器确认完全投入后才移走，计数保留在判定状态中。
        if base.task_kind == "BinFill":
            for name in base._task_result.get("inserted_ids", []):
                if name not in base._parked:
                    base.park(name)
            if base._parked:
                self._last_observation = base.normalized_observation(base.get_obs())
        limited = int(base.elapsed_steps.item()) >= int(base.definition["schedule"]["max_episode_steps"])
        return self._last_observation, float(np.asarray(reward).reshape(-1)[0]), bool(terminated), bool(truncated or (limited and not terminated)), info
