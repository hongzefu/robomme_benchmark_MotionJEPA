#!/usr/bin/env python3
"""C／D 路的 worker：官方 ``_worker`` 的最小镜像，只多传两个显式输入。

方案第三节要求 C 路在 B 的基础上显式传 ``sampling_config``、D 路再加 ``episode_spec``，
而官方 ``_worker`` 的 ``gym.make`` 参数表是写死的，无法从外部注入这两个键。

为把「镜像漂移」压到最小，本文件**只复制 `gym.make` 参数表那一段**，其余全部直接调用
官方模块里的同一批函数：``_planner_classes``、``_execute_tasks``、``_raw_summary``、
``STICK_TASKS`` 与几个异常类。官方源码本身不改、不打补丁。

与官方 ``_worker`` 的差异清单（除此之外逐句一致）：
1. ``kwargs`` 里按需加入 ``sampling_config`` 与 ``episode_spec``；两者都为 ``None`` 时
   参数表与官方完全相同，因此 B 路仍可继续用官方 ``_worker``。
2. 返回体多一个 ``inputs`` 字段，记录本局实际传入了哪两个显式输入的散列，供 G4 核验。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


def _digest(payload: Any) -> str | None:
    if payload is None:
        return None
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def run_one(payload: tuple) -> dict[str, Any]:
    """在 spawn 子进程里跑一条身份；``payload=(job, sampling_config, episode_spec)``。"""
    job, sampling_config, episode_spec = payload
    import generate_dataset as official  # 官方固定源码，父进程已把其目录放进 sys.path

    os.environ["CUDA_VISIBLE_DEVICES"] = job.gpu
    worker_dir = Path(job.worker_dir)
    raw_path = worker_dir / "hdf5_files" / f"{job.task}_ep{job.episode}_seed{job.seed}.h5"
    record_env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None
    try:
        source_root = Path(job.repo_root) / "src"
        if not source_root.is_dir():
            raise official.DatasetGenerationError(f"src does not exist: {source_root}")
        sys.path.insert(0, str(source_root))
        import gymnasium as gym
        import torch
        import robomme.robomme_env  # noqa: F401 注册环境
        from robomme.env_record_wrapper import FailsafeTimeout, RobommeRecordWrapper  # noqa: F401
        from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: F401
        from robomme.robomme_env.utils.planner_fail_safe import (
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )

        arm_cls, stick_cls = official._planner_classes(
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )
        kwargs: dict[str, Any] = {
            "obs_mode": "rgb+depth+segmentation",
            "control_mode": "pd_joint_pos",
            "render_mode": "rgb_array",
            "reward_mode": "dense",
            "seed": job.seed,
            "difficulty": job.difficulty,
        }
        if job.recovery_mode is not None:
            kwargs["robomme_failure_recovery"] = True
            kwargs["robomme_failure_recovery_mode"] = job.recovery_mode
        # ── 与官方 _worker 的唯一参数差异 ──────────────────────────────────────
        if sampling_config is not None:
            kwargs["sampling_config"] = sampling_config
        if episode_spec is not None:
            kwargs["episode_spec"] = episode_spec
        # ─────────────────────────────────────────────────────────────────────
        worker_dir.mkdir(parents=True, exist_ok=False)
        base_env = gym.make(job.task, **kwargs)
        record_env = RobommeRecordWrapper(
            base_env,
            dataset=str(worker_dir),
            env_id=job.task,
            episode=job.episode,
            seed=job.seed,
            save_video=True,
        )
        record_env.reset()
        planner_kwargs: dict[str, Any] = {
            "debug": False,
            "vis": False,
            "base_pose": record_env.unwrapped.agent.robot.pose,
            "visualize_target_grasp_pose": False,
            "print_env_info": False,
        }
        if job.task in official.STICK_TASKS:
            planner_kwargs["joint_vel_limits"] = 0.3
            planner = stick_cls(record_env, **planner_kwargs)
        else:
            planner = arm_cls(record_env, **planner_kwargs)
        official._execute_tasks(record_env, planner, torch, job)
    except Exception as exc:  # noqa: BLE001 官方同样先分类后兜底，这里合并但保留类型名
        caught = exc
        error_traceback = traceback.format_exc()
    finally:
        if record_env is not None:
            try:
                record_env.close()
            except Exception as close_exc:  # noqa: BLE001 与官方一致
                if caught is None:
                    caught = close_exc
                    error_traceback = traceback.format_exc()

    base = {
        "task": job.task,
        "episode": job.episode,
        "seed": job.seed,
        "difficulty": job.difficulty,
        "gpu": job.gpu,
        "recovery_mode": job.recovery_mode,
        "attempt_count": 1,
        "inputs": {
            "sampling_config_sha256": _digest(sampling_config),
            "episode_spec_sha256": _digest(episode_spec),
        },
    }
    if caught is not None:
        return {
            **base,
            "ok": False,
            "error_type": type(caught).__name__,
            "error": str(caught),
            "traceback": error_traceback,
        }
    try:
        return {**base, "ok": True, **official._raw_summary(raw_path, job)}
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
