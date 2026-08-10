#!/usr/bin/env python3
"""RoboMME 数据生成的唯一入口（v2.1：带 2D flow ground truth 与 masked-rgb-v2 遮蔽图）。

一次完整调用依次做四件事：**并行生成 → 按任务合并 → 契约校验与参考对拍 → 写报告**。

相对 `scripts/data-generation-v2/` 只有**遮蔽图口径**一处不同（见 `masked_rgb.py`）：
机器人整根涂掉、只按像素豁免夹爪指尖的黑色接触面，panda_stick 不做任何保留，桌面不再涂色。
flow 链路、契约校验、参考对拍、报告格式全部逐字沿用 v2。

相对 v1 的差别集中在四处，都是「只增」：

- 换用 `record_wrapper_v2.RobommeRecordWrapperV2`（薄子类，父类 RecordWrapper 一字未改）；
- 新增 `--reference-root`：v1 把官方参考路径硬编码成仓库内 `data/robomme_data_h5` 且没有开关，
  参考数据在仓库外时根本跑不起来；
- 新增 `--flow` / `--no-flow`：控制是否采集 flow。关掉时行为与父类完全一致，专供自对拍基线；
- 新增 `--no-reference-validation`：本机参考数据不覆盖全部 16 个任务时，跳过末尾那次对拍。
  生成阶段本身与参考数据无关，跳过的只是验收环节。

另外给规划器加了一组**纯观测**计数（`planner_fallback`），见 `_planner_classes`。
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_generated_dataset_contract import (
    MAX_EPISODES,
    METADATA_ROOT,
    REFERENCE_ROOT,
    DatasetContractError,
    inspect_episode_terminal,
    parse_tasks,
    read_train_metadata,
)
from write_generation_report import (
    build_validation_report,
    new_generation_report,
    write_generation_report,
    write_text_atomic,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
STICK_TASKS = frozenset(("PatternLock", "RouteStick"))
DEFAULT_WORKERS = 20
GPU_ID = "0"


class DatasetGenerationError(RuntimeError):
    """生成、合并或生成后的验收环节不满足既定契约。"""


class PlannerExhausted(RuntimeError):
    """局部规划器的 screw 与 RRTStar 重试次数都已用尽。"""


@dataclass(frozen=True)
class EpisodeJob:
    task: str
    episode: int
    seed: int
    difficulty: str
    worker_dir: str
    gpu: str
    repo_root: str
    record_flow: bool = False
    record_masked_rgb: bool = False

    @property
    def recovery_mode(self) -> str | None:
        if self.episode <= 2:
            return "z"
        if self.episode <= 5:
            return "xy"
        return None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ensure_layout(reference_root: Path) -> None:
    required = (REPO_ROOT / "uv.lock", SRC_ROOT, METADATA_ROOT, reference_root)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise DatasetGenerationError("缺少必需的路径：" + ", ".join(missing))


def _prepare_output(value: str | Path, reference_root: Path) -> Path:
    requested = Path(value).expanduser()
    if requested.is_symlink():
        raise DatasetGenerationError(f"输出目录不能是符号链接：{requested}")
    parent = requested.parent
    while parent != parent.parent:
        if parent.exists() and parent.is_symlink():
            raise DatasetGenerationError(f"输出路径的上级目录里含有符号链接：{parent}")
        if parent == REPO_ROOT:
            break
        parent = parent.parent
    output = requested.resolve()
    repo = REPO_ROOT.resolve()
    reference = reference_root.resolve()
    if output == repo or not _inside(output, repo):
        raise DatasetGenerationError(f"输出目录必须位于仓库内部：{output}")
    if _inside(output, reference):
        raise DatasetGenerationError(f"输出目录不能落在参考数据目录里：{output}")
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise DatasetGenerationError(f"输出目录必须不存在，或者存在但为空：{output}")
    else:
        output.mkdir(parents=True, exist_ok=False)
    return output


def _parse_gpus(value: str | Sequence[str | int]) -> tuple[str, ...]:
    raw = value.split(",") if isinstance(value, str) else value
    gpus = tuple(str(item).strip() for item in raw if str(item).strip())
    if gpus != (GPU_ID,):
        raise DatasetGenerationError("--gpus 只能是 0：生成过程锁定在物理 GPU 0 上")
    return gpus


def _runtime_bool(value: Any, torch_module: Any) -> bool:
    if isinstance(value, torch_module.Tensor):
        if value.numel() != 1:
            raise DatasetGenerationError("evaluate 返回了非标量的 Tensor")
        return bool(value.detach().cpu().item())
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise DatasetGenerationError("evaluate 返回了非标量的 ndarray")
        return bool(value.item())
    return bool(value)


def _is_failure(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and int(value) == -1


def _planner_classes(
    arm_base: type,
    stick_base: type,
    screw_error: type[BaseException],
) -> tuple[type, type, dict[str, int]]:
    """用局部子类实现不打猴补丁的兜底：先试三次 screw，再试三次 RRTStar。

    额外返回一个计数字典。RRTStar 是带墙钟预算的采样式规划器，依赖当时的 CPU 负载，是整条
    链路里**唯一的非确定性来源**——joint_action 做不到逐位一致时，第一嫌疑永远是它。这里把
    「有没有退避到 RRTStar」变成可观测量写进生成报告，出现差异时能立刻定位，而不必靠猜。

    计数器只做自增，**不改变任何控制流、不改变调用顺序**，因此对生成结果零影响。
    """

    counters: dict[str, int] = {
        "screw_calls": 0,  # move_to_pose_with_screw 被调用的次数
        "screw_rounds_failed": 0,  # 三次 screw 全败、不得不退避的次数
        "rrtstar_attempts": 0,  # 实际调用 RRTStar 的次数（判据：全程应为 0）
        "rrtstar_successes": 0,  # RRTStar 成功返回的次数
    }

    class ScrewThenRRT:
        def move_to_pose_with_screw(self, *args: Any, **kwargs: Any) -> Any:
            counters["screw_calls"] += 1
            last_error: BaseException | None = None
            for _ in range(3):
                try:
                    result = super().move_to_pose_with_screw(*args, **kwargs)
                except screw_error as exc:
                    last_error = exc
                    continue
                if not _is_failure(result):
                    return result
            counters["screw_rounds_failed"] += 1
            for _ in range(3):
                counters["rrtstar_attempts"] += 1
                try:
                    result = super().move_to_pose_with_RRTStar(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    continue
                if not _is_failure(result):
                    counters["rrtstar_successes"] += 1
                    return result
            suffix = f": {last_error}" if last_error is not None else ""
            raise PlannerExhausted("All three screw and three RRTStar attempts failed" + suffix)

    class NoPatchArm(ScrewThenRRT, arm_base):
        pass

    class NoPatchStick(ScrewThenRRT, stick_base):
        pass

    return NoPatchArm, NoPatchStick, counters


def _execute_tasks(record_env: Any, planner: Any, torch_module: Any, job: EpisodeJob) -> None:
    task_list = list(getattr(record_env.unwrapped, "task_list", []) or [])
    if not task_list:
        raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: task_list 为空")
    for entry in task_list:
        solve = entry.get("solve") if isinstance(entry, Mapping) else None
        if not callable(solve):
            raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: 该子任务没有 solve 方法")
        record_env.unwrapped.evaluate(solve_complete_eval=True)
        result = solve(record_env, planner)
        if _is_failure(result):
            raise PlannerExhausted(
                f"{job.task}/episode_{job.episode}: solve 返回了 -1"
            )
        evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
        if _runtime_bool(evaluation.get("fail", False), torch_module):
            raise DatasetGenerationError(
                f"{job.task}/episode_{job.episode}: 环境判定为失败"
            )
        if _runtime_bool(evaluation.get("success", False), torch_module):
            return
    evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
    if not _runtime_bool(evaluation.get("success", False), torch_module):
        raise DatasetGenerationError(
            f"{job.task}/episode_{job.episode}: 跑完整个 task_list 之后仍未成功"
        )


def _raw_summary(path: Path, job: EpisodeJob) -> dict[str, Any]:
    """worker 成功之后，立刻用共享的契约辅助函数检查原始轨迹的终止状态。"""
    if not path.is_file():
        raise DatasetGenerationError(f"缺少原始 HDF5：{path}")
    name = f"episode_{job.episode}"
    with h5py.File(path, "r") as handle:
        if name not in handle or not isinstance(handle[name], h5py.Group):
            raise DatasetGenerationError(f"{path}: 缺少 {name}")
        timesteps, done, errors = inspect_episode_terminal(
            handle[name],
            f"{path}/{name}",
        )
        if errors:
            raise DatasetGenerationError("; ".join(errors))
        if done is not True:
            raise DatasetGenerationError(f"{path}/{name}: 末帧的 is_completed 不为 true")
    return {"raw_h5_path": str(path), "timestep_count": len(timesteps)}


def _worker(job: EpisodeJob) -> dict[str, Any]:
    os.environ["CUDA_VISIBLE_DEVICES"] = job.gpu
    worker_dir = Path(job.worker_dir)
    raw_path = worker_dir / "hdf5_files" / (
        f"{job.task}_ep{job.episode}_seed{job.seed}.h5"
    )
    record_env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None
    # 规划器兜底计数与 flow 采集开销，都是纯观测量，先给默认值以免异常路径下未定义
    planner_counters: dict[str, int] = {}
    flow_capture_ms_per_step = 0.0
    flow_capture_count = 0
    masked_rgb_seconds = 0.0
    masked_rgb_frames = 0
    masked_rgb_painted_pixels = 0
    masked_rgb_black_exempt_pixels = 0
    try:
        source_root = Path(job.repo_root) / "src"
        if not source_root.is_dir():
            raise DatasetGenerationError(f"src 目录不存在：{source_root}")
        sys.path.insert(0, str(source_root))
        import gymnasium as gym
        import torch
        import robomme.robomme_env
        from robomme.env_record_wrapper import FailsafeTimeout
        from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
        from robomme.robomme_env.utils.planner_fail_safe import (
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )

        # v2 链路用带 flow 与遮蔽图采集的薄子类；两个开关都关时行为与父类完全一致
        from record_wrapper_v2 import RobommeRecordWrapperV2

        arm_cls, stick_cls, planner_counters = _planner_classes(
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
        worker_dir.mkdir(parents=True, exist_ok=False)
        base_env = gym.make(job.task, **kwargs)
        record_env = RobommeRecordWrapperV2(
            base_env,
            dataset=str(worker_dir),
            env_id=job.task,
            episode=job.episode,
            seed=job.seed,
            save_video=True,
            record_flow=job.record_flow,
            record_masked_rgb=job.record_masked_rgb,
        )
        record_env.reset()
        planner_kwargs: dict[str, Any] = {
            "debug": False,
            "vis": False,
            "base_pose": record_env.unwrapped.agent.robot.pose,
            "visualize_target_grasp_pose": False,
            "print_env_info": False,
        }
        if job.task in STICK_TASKS:
            planner_kwargs["joint_vel_limits"] = 0.3
            planner = stick_cls(record_env, **planner_kwargs)
        else:
            planner = arm_cls(record_env, **planner_kwargs)
        _execute_tasks(record_env, planner, torch, job)
    except (
        SceneGenerationError,
        FailsafeTimeout,
        PlannerExhausted,
        ScrewPlanFailure,
        DatasetGenerationError,
    ) as exc:
        caught = exc
        error_traceback = traceback.format_exc()
    except Exception as exc:
        caught = exc
        error_traceback = traceback.format_exc()
    finally:
        if record_env is not None:
            try:
                record_env.close()
            except Exception as close_exc:
                if caught is None:
                    caught = close_exc
                    error_traceback = traceback.format_exc()
            # close() 之后再读采集开销：flow 与遮蔽图的写盘都发生在 close() 里
            flow_capture_ms_per_step = float(
                getattr(record_env, "flow_capture_ms_per_step", 0.0)
            )
            flow_capture_count = int(getattr(record_env, "flow_capture_count", 0))
            masked_rgb_seconds = float(getattr(record_env, "masked_rgb_seconds", 0.0))
            masked_rgb_frames = int(getattr(record_env, "masked_rgb_frames", 0))
            masked_rgb_painted_pixels = int(
                getattr(record_env, "masked_rgb_painted_pixels", 0)
            )
            masked_rgb_black_exempt_pixels = int(
                getattr(record_env, "masked_rgb_black_exempt_pixels", 0)
            )

    base = {
        "task": job.task,
        "episode": job.episode,
        "seed": job.seed,
        "difficulty": job.difficulty,
        "gpu": job.gpu,
        "recovery_mode": job.recovery_mode,
        "attempt_count": 1,
        "record_flow": bool(job.record_flow),
        "record_masked_rgb": bool(job.record_masked_rgb),
        "planner_fallback": dict(planner_counters),
        "flow_capture_ms_per_step": flow_capture_ms_per_step,
        "flow_capture_count": flow_capture_count,
        "masked_rgb_seconds": masked_rgb_seconds,
        "masked_rgb_frames": masked_rgb_frames,
        "masked_rgb_painted_pixels": masked_rgb_painted_pixels,
        "masked_rgb_black_exempt_pixels": masked_rgb_black_exempt_pixels,
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
        return {**base, "ok": True, **_raw_summary(raw_path, job)}
    except Exception as exc:
        return {
            **base,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _merge(output: Path, task: str, results: Sequence[Mapping[str, Any]]) -> Path:
    target = output / f"record_dataset_{task}.h5"
    temporary = output / f".record_dataset_{task}.h5.tmp"
    try:
        with h5py.File(temporary, "w") as merged:
            for result in sorted(results, key=lambda item: int(item["episode"])):
                episode = int(result["episode"])
                name = f"episode_{episode}"
                with h5py.File(str(result["raw_h5_path"]), "r") as raw:
                    if name not in raw:
                        raise DatasetGenerationError(f"{raw.filename}: 缺少 {name}")
                    raw.copy(raw[name], merged, name=name)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _write_metadata(
    output: Path,
    task: str,
    records: Sequence[Mapping[str, Any]],
) -> None:
    payload = {"env_id": task, "record_count": len(records), "records": list(records)}
    write_text_atomic(
        output / f"record_dataset_{task}_metadata.json",
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def generate_dataset(
    output_dir: str | Path,
    env: str = "all",
    episodes: int = MAX_EPISODES,
    workers: int = DEFAULT_WORKERS,
    gpus: str | Sequence[str | int] = GPU_ID,
    reference_root: str | Path = REFERENCE_ROOT,
    record_flow: bool = True,
    record_masked_rgb: bool = True,
    reference_validation: bool = True,
) -> dict[str, Any]:
    """在同一个进程内完成生成、合并，以及拆分开的契约校验与数值对拍。"""
    reference = Path(reference_root).expanduser().resolve()
    _ensure_layout(reference)
    output = _prepare_output(output_dir, reference)
    temporary = output / ".workers"
    results: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": 2,
        "status": "running",
        "parameters": {
            "output_dir": str(output),
            "env": env,
            "episodes": episodes,
            "workers": workers,
            "requested_gpus": str(gpus),
            "metadata_root": str(METADATA_ROOT),
            "reference_root": str(reference),
            "max_abs_diff": 1e-8,
            "seed_attempts_per_episode": 1,
            "save_video_for_recording": True,
            "record_flow": bool(record_flow),
            "record_masked_rgb": bool(record_masked_rgb),
            "reference_validation": bool(reference_validation),
        },
    }
    try:
        if not 1 <= episodes <= MAX_EPISODES:
            raise DatasetGenerationError(f"episodes 必须在 1..{MAX_EPISODES} 之间")
        if workers < 1:
            raise DatasetGenerationError("workers 必须大于 0")
        report = new_generation_report(report["parameters"])
        tasks = parse_tasks(env)
        gpu_ids = _parse_gpus(gpus)
        os.environ["CUDA_VISIBLE_DEVICES"] = GPU_ID
        records_by_task = read_train_metadata()
        episode_indices = list(range(episodes))
        report["parameters"].update(
            {
                "tasks": tasks,
                "gpus": list(gpu_ids),
            }
        )
        temporary.mkdir()
        jobs: list[EpisodeJob] = []
        for task in tasks:
            for episode in episode_indices:
                record = records_by_task[task][episode]
                jobs.append(
                    EpisodeJob(
                        task=task,
                        episode=episode,
                        seed=int(record["seed"]),
                        difficulty=str(record["difficulty"]),
                        worker_dir=str(temporary / f"{task}_episode_{episode}"),
                        gpu=gpu_ids[len(jobs) % len(gpu_ids)],
                        repo_root=str(REPO_ROOT),
                        record_flow=bool(record_flow),
                        record_masked_rgb=bool(record_masked_rgb),
                    )
                )
        with ProcessPoolExecutor(
            max_workers=min(workers, len(jobs)),
            mp_context=mp.get_context("spawn"),
        ) as executor:
            futures = {executor.submit(_worker, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    results.append(future.result())
                except BaseException as exc:
                    results.append(
                        {
                            "task": job.task,
                            "episode": job.episode,
                            "seed": job.seed,
                            "difficulty": job.difficulty,
                            "gpu": job.gpu,
                            "recovery_mode": job.recovery_mode,
                            "attempt_count": 1,
                            "ok": False,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        }
                    )
        results.sort(key=lambda item: (str(item["task"]), int(item["episode"])))
        failures = [item for item in results if not item.get("ok")]
        report["generation"] = {
            "requested_count": len(jobs),
            "success_count": len(results) - len(failures),
            "failure_count": len(failures),
            "results": results,
        }
        if failures:
            details = "; ".join(
                f"{item['task']}/episode_{item['episode']}: "
                f"{item.get('error_type')} {item.get('error')}"
                for item in failures
            )
            raise DatasetGenerationError(f"按原始 seed 单次尝试的生成失败：{details}")
        for task in tasks:
            task_results = [item for item in results if item["task"] == task]
            _merge(output, task, task_results)
            _write_metadata(
                output,
                task,
                [records_by_task[task][episode] for episode in episode_indices],
            )
        if reference_validation:
            report["validation"] = build_validation_report(
                output,
                tasks,
                episode_indices,
                records_by_task=records_by_task,
                reference_root=reference,
                metadata_root=METADATA_ROOT,
                max_abs_diff=1e-8,
            )
            report["status"] = "passed" if report["validation"]["passed"] else "failed"
            if not report["validation"]["passed"]:
                raise DatasetGenerationError("生成后的契约校验或 joint_action 对拍未达到验收标准")
        else:
            # 本机参考数据不全时（16 个任务只到了一部分），生成阶段本身与参考数据无关，
            # 但末尾的契约校验与 joint_action 对拍会因为缺参考文件而失败。这里允许把这一步
            # 跳过，先把产物落下来，之后用 compare_joint_actions.py 单独对有参考的任务对拍。
            report["validation"] = {
                "passed": None,
                "status": "skipped",
                "reason": "调用方传了 --no-reference-validation：跳过与官方参考数据的契约校验与 joint_action 对拍",
            }
            report["status"] = "generated"
        write_generation_report(output, report)
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        if "generation" not in report:
            failures = [item for item in results if not item.get("ok")]
            report["generation"] = {
                "requested_count": len(results),
                "success_count": len(results) - len(failures),
                "failure_count": len(failures),
                "results": results,
            }
        try:
            write_generation_report(output, report)
        except Exception as report_error:
            raise DatasetGenerationError(
                f"{exc}；此外报告写入也失败了：{report_error}"
            ) from exc
        if isinstance(exc, DatasetGenerationError):
            raise
        raise DatasetGenerationError(str(exc)) from exc
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RoboMME 数据生成与校验（v2.1，带 2D flow ground truth 与 masked-rgb-v2 遮蔽图）；最新的完整报告始终写到 scripts/data-generation-v2.1/reports/ 下的 generation_report.json 与 generation_report.md")
    parser.add_argument("--output-dir", required=True, help="仓库内的输出目录，必须不存在或为空")
    parser.add_argument("--env", "--environment", default="all", help="all，或逗号分隔的环境名列表")
    parser.add_argument(
        "--episodes",
        type=int,
        default=MAX_EPISODES,
        help="每个环境从 episode 0 起生成的 episode 数量",
    )
    parser.add_argument("--workers", "--max-workers", dest="workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--gpus", "--gpu", dest="gpus", default=GPU_ID, help="must be 0; generation is locked to physical GPU 0")
    parser.add_argument(
        "--reference-root",
        default=str(REFERENCE_ROOT),
        help="官方参考数据目录；默认指向仓库内 data/robomme_data_h5，本机参考数据在仓库外时必须显式传",
    )
    parser.add_argument(
        "--flow",
        dest="record_flow",
        action="store_true",
        default=True,
        help="采集并写入 2D flow ground truth（默认开启，v2 链路的存在意义）",
    )
    parser.add_argument(
        "--no-flow",
        dest="record_flow",
        action="store_false",
        help="关闭 flow 采集；与 --no-masked-rgb 合用即退化为与父类 RecordWrapper 完全一致，用于自对拍基线",
    )
    parser.add_argument(
        "--masked-rgb",
        dest="record_masked_rgb",
        action="store_true",
        default=True,
        help="写入 obs/front_rgb_masked（默认开启）：白名单只把机器人 link 涂成纯棕色，"
        "夹爪指尖的黑色像素逐像素豁免；桌面、地面与全部任务物体保留原像素",
    )
    parser.add_argument(
        "--no-masked-rgb",
        dest="record_masked_rgb",
        action="store_false",
        help="关闭遮蔽图采集；与 --no-flow 合用即得到自对拍基线",
    )
    parser.add_argument(
        "--no-reference-validation",
        dest="reference_validation",
        action="store_false",
        default=True,
        help="跳过末尾与官方参考数据的契约校验与 joint_action 对拍；本机参考数据不覆盖全部任务时用",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        report = generate_dataset(
            output_dir=args.output_dir,
            env=args.env,
            episodes=args.episodes,
            workers=args.workers,
            gpus=args.gpus,
            reference_root=args.reference_root,
            record_flow=args.record_flow,
            record_masked_rgb=args.record_masked_rgb,
            reference_validation=args.reference_validation,
        )
    except DatasetGenerationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    comparison = report["validation"].get("joint_action_comparison")
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_paths": report["report_paths"],
                "max_abs_diff": (
                    comparison["max_abs_diff"] if comparison is not None else None
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
