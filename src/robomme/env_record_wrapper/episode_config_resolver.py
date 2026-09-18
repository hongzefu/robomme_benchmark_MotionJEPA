"""
Episode configuration resolver: Parse episode seed and difficulty from metadata, and build wrapped environment.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import gymnasium as gym

from ..logging_utils import logger

DATASET_ROOT = Path(__file__).resolve().parents[1] / "env_metadata"

_ALLOWED_DATASETS = {"train", "test", "val"}
_ALLOWED_ACTION_SPACES = {"joint_angle", "ee_pose", "waypoint", "multi_choice"}
_DEFAULT_TASK_LIST = [
    "PickXtimes",
    "StopCube",
    "SwingXtimes",
    "BinFill",
    "VideoUnmaskSwap",
    "VideoUnmask",
    "ButtonUnmaskSwap",
    "ButtonUnmask",
    "VideoRepick",
    "VideoPlaceButton",
    "VideoPlaceOrder",
    "PickHighlight",
    "InsertPeg",
    "MoveCube",
    "PatternLock",
    "RouteStick",
]


def load_episode_metadata(metadata_path: Union[str, Path, None]) -> Dict[Tuple[str, int], Dict[str, object]]:
    """
    Read episode metadata from JSON file; return empty dictionary if missing or invalid.
    Used to restore specific episode configuration (e.g., seed, difficulty).
    """

    metadata_index: Dict[Tuple[str, int], Dict[str, object]] = {}
    if not metadata_path:
        return metadata_index

    path = Path(metadata_path)
    if not path.exists():
        logger.debug(f"Metadata file not found, skipping: {path}")
        return metadata_index

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:  # pragma: no cover - informational logging only
        logger.debug(f"Failed to read metadata {path}: {exc}")
        return metadata_index

    default_task = str(payload.get("env_id") or "").strip()
    for record in payload.get("records", []):
        task_name = str(record.get("task") or default_task or "").strip()
        episode = record.get("episode")
        if not task_name or episode is None:
            continue
        try:
            episode_idx = int(episode)
        except (TypeError, ValueError):
            continue
        metadata_index[(task_name, episode_idx)] = record

    if metadata_index:
        logger.debug(f"Loaded {len(metadata_index)} metadata records from {path}")
    else:
        logger.debug(f"No valid metadata entries found in {path}")
    return metadata_index


def get_episode_metadata(
    metadata_index: Dict[Tuple[str, int], Dict[str, object]],
    task: str,
    episode: int,
) -> Optional[Dict[str, object]]:
    """Find metadata entry for specific (task, episode) pair."""

    if not metadata_index:
        return None
    return metadata_index.get((task, episode))


class BenchmarkEnvBuilder:
    """
    Episode environment builder.

    Automatically parse metadata based on dataset and env_id, and build wrapped environment according to action_space.
    """

    def __init__(
        self,
        env_id: str,
        dataset: str = "test",
        action_space: str = "joint_angle",
        gui_render: bool = False,
        override_metadata_path: Optional[Union[str, Path]] = None,
        max_steps: int = 10000,
    ):
        if dataset not in _ALLOWED_DATASETS:
            raise ValueError(f"Unsupported dataset '{dataset}'. Allowed datasets: {sorted(_ALLOWED_DATASETS)}")
        if action_space not in _ALLOWED_ACTION_SPACES:
            raise ValueError(
                f"Unsupported action_space '{action_space}'. "
                f"Allowed action spaces: {sorted(_ALLOWED_ACTION_SPACES)}"
            )

        self.env_id = env_id
        self.dataset = dataset
        self.action_space = action_space
        self.gui_render = gui_render
        self.override_metadata_path = (
            Path(override_metadata_path) if override_metadata_path is not None else None
        )
        self.render_mode = "human" if gui_render else "rgb_array"
        self.max_steps_without_demonstration = max_steps+2

        metadata_path = self._resolve_metadata_path()
        self.metadata_index = load_episode_metadata(metadata_path)

    @classmethod
    def get_task_list(cls) -> List[str]:
        """
        Return list of evaluatable tasks.
        Task list is fixed to built-in default order, not automatically discovered from metadata.
        """

        return list(_DEFAULT_TASK_LIST)

    def _resolve_metadata_path(self) -> str:
        if self.override_metadata_path is not None:
            return str(
                self.override_metadata_path / f"record_dataset_{self.env_id}_metadata.json"
            )
        if self.dataset in _ALLOWED_DATASETS:
            return os.path.join(str(DATASET_ROOT), self.dataset, f"record_dataset_{self.env_id}_metadata.json")
        raise ValueError(f"Unsupported dataset '{self.dataset}'.")

    def resolve_episode(self, episode: int):
        """Parse episode configuration based on metadata."""
        seed = None
        difficulty_hint = None

        metadata = get_episode_metadata(self.metadata_index, self.env_id, episode)
        if metadata:
            metadata_seed = metadata.get("seed")
            if metadata_seed is not None:
                try:
                    seed = int(metadata_seed)
                except (TypeError, ValueError):
                    logger.debug(f"[{self.env_id}] Invalid metadata seed for episode {episode}: {metadata_seed}")
            difficulty_hint = metadata.get("difficulty")

        return seed, difficulty_hint

    def get_episode_num(self) -> int:
        """
        Return number of episodes for current env_id in metadata.
        Note: By convention, this method returns count (int) instead of list.
        """
        if not self.metadata_index:
            return 0
        episode_set = {episode for (task, episode) in self.metadata_index if task == self.env_id}
        return len(episode_set)

    def make_env_for_episode(
        self,
        episode_idx: int,
        max_steps: Optional[int] = None,
        include_maniskill_obs: bool = False,
        include_front_depth: bool = False,
        include_wrist_depth: bool = False,
        include_front_camera_extrinsic: bool = False,
        include_wrist_camera_extrinsic: bool = False,
        include_available_multi_choices: bool = False,
        include_front_camera_intrinsic: bool = False,
        include_wrist_camera_intrinsic: bool = False,
    ):
        """Create and configure environment for specific episode. Wrap EndeffectorDemonstrationWrapper for action_space=ee_pose, MultiStepDemonstrationWrapper for waypoint, OraclePlannerDemonstrationWrapper for multi_choice."""
        max_steps_without_demo = (
            max_steps + 2 if max_steps is not None else self.max_steps_without_demonstration
        )

        seed, difficulty_hint = self.resolve_episode(episode_idx)
        env_kwargs = dict(
            obs_mode="rgb+depth+segmentation",
            control_mode="pd_joint_pos",
            render_mode=self.render_mode,
            reward_mode="dense",
        )
        if seed is not None:
            env_kwargs["seed"] = seed
        if difficulty_hint:
            env_kwargs["difficulty"] = difficulty_hint
        seed_desc = seed if seed is not None else "default"
        difficulty_str = f", difficulty={difficulty_hint}" if difficulty_hint else ""
        logger.debug(f"[{self.env_id}] Episode {episode_idx}: seed={seed_desc}{difficulty_str}")

        env = gym.make(self.env_id, **env_kwargs)
        return _wrap_env(
            env,
            env_id=self.env_id,
            action_space=self.action_space,
            gui_render=self.gui_render,
            max_steps_without_demo=max_steps_without_demo,
            include_maniskill_obs=include_maniskill_obs,
            include_front_depth=include_front_depth,
            include_wrist_depth=include_wrist_depth,
            include_front_camera_extrinsic=include_front_camera_extrinsic,
            include_wrist_camera_extrinsic=include_wrist_camera_extrinsic,
            include_available_multi_choices=include_available_multi_choices,
            include_front_camera_intrinsic=include_front_camera_intrinsic,
            include_wrist_camera_intrinsic=include_wrist_camera_intrinsic,
        )


def _wrap_env(
    env,
    *,
    env_id: str,
    action_space: str,
    gui_render: bool,
    max_steps_without_demo: int,
    include_maniskill_obs: bool = False,
    include_front_depth: bool = False,
    include_wrist_depth: bool = False,
    include_front_camera_extrinsic: bool = False,
    include_wrist_camera_extrinsic: bool = False,
    include_available_multi_choices: bool = False,
    include_front_camera_intrinsic: bool = False,
    include_wrist_camera_intrinsic: bool = False,
):
    """把裸 gym 环境套上评测用的 wrapper 链。

    这段逻辑原本内联在 ``BenchmarkEnvBuilder.make_env_for_episode`` 里，抽出来是为了让
    ``make_env_for_spec``（按候选规格起环境）复用同一套装配，而不是在下游仓库手抄一遍——
    手抄会让 ``+2``、11 个 ``include_*`` 默认值、``multi_choice`` 强制打开相机参数这些细节
    静默漂移。装配顺序与原实现逐字一致，行为不变。
    """
    from .DemonstrationWrapper import DemonstrationWrapper

    force_front_camera_params = action_space == "multi_choice"
    include_front_camera_extrinsic_effective = (
        include_front_camera_extrinsic or force_front_camera_params
    )
    include_front_camera_intrinsic_effective = (
        include_front_camera_intrinsic or force_front_camera_params
    )
    env = DemonstrationWrapper(
        env,
        max_steps_without_demonstration=max_steps_without_demo,
        gui_render=gui_render,
        include_maniskill_obs=include_maniskill_obs,
        include_front_depth=include_front_depth,
        include_wrist_depth=include_wrist_depth,
        include_front_camera_extrinsic=include_front_camera_extrinsic_effective,
        include_wrist_camera_extrinsic=include_wrist_camera_extrinsic,
        include_available_multi_choices=include_available_multi_choices,
        include_front_camera_intrinsic=include_front_camera_intrinsic_effective,
        include_wrist_camera_intrinsic=include_wrist_camera_intrinsic,
    )
    if action_space == "joint_angle":
        pass
    elif action_space == "ee_pose":
        from .EndeffectorDemonstrationWrapper import EndeffectorDemonstrationWrapper

        env = EndeffectorDemonstrationWrapper(env, action_repr="rpy")

    elif action_space == "waypoint":
        from .MultiStepDemonstrationWrapper import MultiStepDemonstrationWrapper

        env = MultiStepDemonstrationWrapper(env, gui_render=gui_render, vis=gui_render)
    elif action_space == "multi_choice":
        from .OraclePlannerDemonstrationWrapper import OraclePlannerDemonstrationWrapper
        env = OraclePlannerDemonstrationWrapper(env, env_id=env_id, gui_render=gui_render)

    # ====== After all wrappers are packaged, add a fallback Try...Except ErrorWrapper =====
    from .FailAwareWrapper import FailAwareWrapper
    env = FailAwareWrapper(env)

    return env


def make_env_for_spec(
    task: str,
    seed: int,
    difficulty: str,
    episode_spec: Dict[str, object],
    sampling_config: Dict[str, object],
    *,
    action_space: str = "joint_angle",
    max_steps: Optional[int] = None,
    **include_flags,
):
    """按注入候选的规格起一个可供策略 rollout 的环境。

    这是 ``scripts/INJECTION.md`` 三消费者表里「策略侧入口」所需的那一块：候选
    （``candidates.jsonl`` 里 ``split="test"`` 且 ``role="primary"`` 的行）不在
    ``env_metadata`` 里，``make_env_for_episode`` 走不到，必须把 ``episode_spec`` 与
    ``sampling_config`` 直接交给 ``gym.make``。

    与 ``scripts/injection/rollout/reset_check.py::check_one`` 的区别只有一点：那边只
    ``make → reset → close``，本函数额外套上 ``_wrap_env`` 的评测 wrapper 链，所以能 step、
    能拿 ``info["status"]``、能取 ``front_rgb_list`` / ``wrist_rgb_list`` 录像。四项固定
    kwargs 取自 ``injection_candidates.RUNTIME``，与候选 header 的 ``runtime`` 同一真值源，
    ``render_mode`` 因此固定 ``rgb_array``（本入口不支持 gui_render，避免偏离候选 runtime）。

    参数 ``seed`` / ``difficulty`` / ``episode_spec`` 全部来自候选行，``sampling_config``
    取 header 里该任务那一份（形如 ``{"parameters": ..., "positions": ...}``）。
    """
    from ..injection_candidates import RUNTIME

    env_kwargs = dict(RUNTIME["kwargs"])
    env_kwargs["seed"] = seed
    env_kwargs["difficulty"] = difficulty
    env_kwargs["sampling_config"] = sampling_config
    env_kwargs["episode_spec"] = episode_spec

    max_steps_without_demo = max_steps + 2 if max_steps is not None else 10002
    logger.debug(
        f"[{task}] spec episode {episode_spec.get('episode')}: seed={seed}, difficulty={difficulty}"
    )

    env = gym.make(task, **env_kwargs)
    return _wrap_env(
        env,
        env_id=task,
        action_space=action_space,
        gui_render=False,
        max_steps_without_demo=max_steps_without_demo,
        **include_flags,
    )
