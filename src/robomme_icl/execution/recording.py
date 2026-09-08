"""在原版包装器内部记录物理步及显式判定调用。"""

import copy

import gymnasium as gym

from ..io.observations import (
    normalized_info,
    normalized_observation,
    task_inventory,
    state_snapshot,
    copy_tree,
    native_parameters,
)
from ..validation.assets import array_copy, actor_asset, scene_assets
from ..io.identities import scene_names


class RecordingEnv(gym.Wrapper):
    def __init__(self, env):
        super().__init__(env)
        self.frames = []
        self.known_actors = set()
        self.runtime_names = {}

    def reset(self, **kwargs):
        raw, info = self.env.reset(**kwargs)
        self.last_info = info
        self.frames = []
        self.runtime_names = scene_names(self.unwrapped)
        self.known_actors = set(self.runtime_names.values())
        self.initial_assets = scene_assets(self.unwrapped)
        self.initial_tasks = task_inventory(self.unwrapped)
        self.initial_state = state_snapshot(self.unwrapped)
        self.initial_sensor_parameters = copy_tree(raw["sensor_param"])
        self.native_parameters = native_parameters(self.unwrapped)
        from ..native.imports import task_goal

        task_id = getattr(self.unwrapped, "native_task_id", self.unwrapped.spec.id)
        self.task_goals = task_goal.get_language_goal(self, task_id)
        return raw, info

    def _record(self, raw, native_info, action, operation, **details):
        base = self.unwrapped
        info = normalized_info(native_info, base)
        info["task_goal"] = copy.deepcopy(self.task_goals)
        info.update(details)
        info["operation"] = operation
        added = {}
        names = scene_names(base)
        self.runtime_names.update(names)
        for raw_name, actor in base.scene.actors.items():
            name = names[raw_name]
            if name not in self.known_actors:
                added[name] = actor_asset(actor)
                self.known_actors.add(name)
        info["added_assets"] = added
        if operation != "step":
            info["deliver_frame"] = False
        frame = {
            "observation": normalized_observation(raw, base),
            "joint_action": None if action is None else array_copy(action),
            "info": info,
        }
        self.frames.append(frame)
        return frame

    def step(self, action):
        before = int(self.unwrapped.elapsed_steps.item())
        context = getattr(self, "delivery_context", None)
        internal = bool(context is not None and context._doing_extra_step)
        raw, reward, terminated, truncated, info = self.env.step(action)
        self.last_info = info
        frame = self._record(
            raw,
            info,
            action,
            "step",
            control_step_before=before,
            internal_terminal_step=internal,
        )
        if internal:
            frame["info"]["deliver_frame"] = False
        return raw, reward, terminated, truncated, info

    def evaluate(self, solve_complete_eval=False):
        # 只记录调用方本来就要执行的判定，不为采集额外求值。
        result = self.unwrapped.evaluate(solve_complete_eval=solve_complete_eval)
        self.last_info = {"elapsed_steps": self.unwrapped.elapsed_steps, **result}
        # get_obs不传info会隐式调用get_info/evaluate，必须传入已有结果。
        self._record(
            self.unwrapped.get_obs(info=self.last_info),
            result,
            None,
            "evaluate",
            solve_complete_eval=bool(solve_complete_eval),
        )
        return result

    def reset_marker(self):
        frame = self._record(
            self.unwrapped.get_obs(info=self.last_info),
            self.last_info,
            None,
            "reset_complete",
        )
        frame["info"]["initial_assets"] = self.initial_assets
        frame["info"]["initial_state"] = self.initial_state
        frame["info"]["initial_sensor_parameters"] = self.initial_sensor_parameters
        frame["info"]["native_parameters"] = self.native_parameters
        frame["info"]["task_inventory"] = self.initial_tasks
        device = self.unwrapped.scene.sub_scenes[0].render_system.device
        frame["info"]["native_runtime"] = {
            "sim_freq": self.unwrapped.sim_freq,
            "control_freq": self.unwrapped.control_freq,
            "control_mode": self.unwrapped.control_mode,
            "render_gpu": device.cuda_id,
            "render_gpu_pci": device.pci_string,
        }
        return frame
