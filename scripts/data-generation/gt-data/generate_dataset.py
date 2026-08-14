#!/usr/bin/env python3
"""带 GT segmentation 的数据生成入口。

用某个 split 的官方 seed 重新渲染一份数据，逐帧多落一份 GT segmentation
（``timestep_<k>/obs/front_camera_segmentation``）与 seg_id 枚举表（``setup/segmentation_*``）。
产物有两个用途：拟合像素表（颜色表），以及给 arm-mask 的实测当尺子。

## ⚠ 不回放、不对拍（用户 2026-08-14 拍板）

- **不使用任何 joint angle 回放功能**：动作全部由 planner 重新规划，本文件不读官方
  h5 的任何动作。同 seed 只保证**场景初始摆放**与官方一致，轨迹会不同，因此
  **RGB 观察与官方不完全一致**。
- **可能无法 100% 完成全部 episode**：planner 失败的 episode 会被跳过并记入摘要，
  其余照常合并落盘——不再像历史版本那样一条失败就整批作废。
- 因此与官方参考数据的契约校验、``joint_action`` 逐位对拍、生成报告那一整套
  （历史上约 1400 行）全部删除，不存在开关。

## seed 口径

``env_metadata/{train,val,test}/`` 里记的就是官方当时实际用的 seed（含官方遇到失败时
递增过的值，如 MoveCube ep6 = 14602），**直接取用、单次尝试、不做任何递增重试**，
照抄即与官方同场景。

## 用法（在仓库根）

    uv run --locked scripts/data-generation/gt-data/generate_dataset.py \\
      --output-dir artifacts/generated/<名字> --env all --episodes 10 \\
      --split train --workers 16 --gpus 0,1
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

from contract import (  # noqa: E402
    ENV_METADATA_ROOT,
    MAX_EPISODES,
    REFERENCE_ROOT,
    SPLIT_EPISODE_COUNTS,
    DatasetContractError,
    inspect_episode_terminal,
    parse_tasks,
    read_split_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
STICK_TASKS = frozenset(("PatternLock", "RouteStick"))
DEFAULT_WORKERS = 16
DEFAULT_GPUS = "0"
SUMMARY_NAME = "generation_summary.json"


class DatasetGenerationError(RuntimeError):
    """生成流程失败。"""


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

    @property
    def recovery_mode(self) -> str | None:
        if self.episode <= 2:
            return "z"
        if self.episode <= 5:
            return "xy"
        return None


def write_text_atomic(path: Path, text: str) -> None:
    """先写临时文件再 replace，避免中途失败留下半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ensure_layout(reference_root: Path, metadata_root: Path) -> None:
    required = (REPO_ROOT / "uv.lock", SRC_ROOT, metadata_root)
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
    if output == repo or not _inside(output, repo):
        raise DatasetGenerationError(f"输出目录必须位于仓库内部：{output}")
    if _inside(output, reference_root.resolve()):
        raise DatasetGenerationError(f"输出目录不能落在参考数据目录里：{output}")
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise DatasetGenerationError(f"输出目录必须不存在，或者存在但为空：{output}")
    else:
        output.mkdir(parents=True, exist_ok=False)
    return output


def _parse_gpus(value: str | Sequence[str | int]) -> tuple[str, ...]:
    """解析 --gpus：episode 之间互不耦合，按轮转分到各卡。"""
    raw = value.split(",") if isinstance(value, str) else value
    gpus = tuple(str(item).strip() for item in raw if str(item).strip())
    if not gpus:
        raise DatasetGenerationError("--gpus 不能为空")
    for item in gpus:
        if not item.isdigit():
            raise DatasetGenerationError(f"--gpus 只接受物理卡号，收到：{item}")
    if len(set(gpus)) != len(gpus):
        raise DatasetGenerationError(f"--gpus 里有重复卡号：{','.join(gpus)}")
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

    额外返回一个计数字典。RRTStar 是带墙钟预算的采样式规划器、依赖当时的 CPU 负载，
    是整条链路的非确定性来源；把「有没有退避到 RRTStar」做成可观测量写进摘要，
    episode 失败时能立刻定位。计数器只做自增，**不改变任何控制流**。
    """

    counters: dict[str, int] = {
        "screw_calls": 0,  # move_to_pose_with_screw 被调用的次数
        "screw_rounds_failed": 0,  # 三次 screw 全败、不得不退避的次数
        "rrtstar_attempts": 0,  # 实际调用 RRTStar 的次数
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
            raise PlannerExhausted(f"{job.task}/episode_{job.episode}: solve 返回了 -1")
        evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
        if _runtime_bool(evaluation.get("fail", False), torch_module):
            raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: 环境判定为失败")
        if _runtime_bool(evaluation.get("success", False), torch_module):
            return
    evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
    if not _runtime_bool(evaluation.get("success", False), torch_module):
        raise DatasetGenerationError(
            f"{job.task}/episode_{job.episode}: 跑完整个 task_list 之后仍未成功"
        )


def _raw_summary(path: Path, job: EpisodeJob) -> dict[str, Any]:
    """worker 成功之后，立刻检查原始轨迹的终止状态。"""
    if not path.is_file():
        raise DatasetGenerationError(f"缺少原始 HDF5：{path}")
    name = f"episode_{job.episode}"
    with h5py.File(path, "r") as handle:
        if name not in handle or not isinstance(handle[name], h5py.Group):
            raise DatasetGenerationError(f"{path}: 缺少 {name}")
        timesteps, done, errors = inspect_episode_terminal(handle[name], f"{path}/{name}")
        if errors:
            raise DatasetGenerationError("; ".join(errors))
        if done is not True:
            raise DatasetGenerationError(f"{path}/{name}: 末帧的 is_completed 不为 true")
    return {"raw_h5_path": str(path), "timestep_count": len(timesteps)}


def _worker(job: EpisodeJob) -> dict[str, Any]:
    os.environ["CUDA_VISIBLE_DEVICES"] = job.gpu
    worker_dir = Path(job.worker_dir)
    raw_path = worker_dir / "hdf5_files" / f"{job.task}_ep{job.episode}_seed{job.seed}.h5"
    record_env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None
    planner_counters: dict[str, int] = {}
    segmentation_seconds = 0.0
    segmentation_frames = 0
    try:
        source_root = Path(job.repo_root) / "src"
        if not source_root.is_dir():
            raise DatasetGenerationError(f"src 目录不存在：{source_root}")
        sys.path.insert(0, str(source_root))
        import gymnasium as gym
        import torch
        import robomme.robomme_env  # noqa: F401
        from robomme.env_record_wrapper import FailsafeTimeout
        from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
        from robomme.robomme_env.utils.planner_fail_safe import (
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )

        from record_wrapper import RobommeRecordWrapperGT

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
        record_env = RobommeRecordWrapperGT(
            base_env,
            dataset=str(worker_dir),
            env_id=job.task,
            episode=job.episode,
            seed=job.seed,
            save_video=True,
            record_segmentation=True,
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
            # close() 之后再读：segmentation 的写盘就发生在 close() 里
            segmentation_seconds = float(getattr(record_env, "segmentation_seconds", 0.0))
            segmentation_frames = int(getattr(record_env, "segmentation_frames", 0))

    base = {
        "task": job.task,
        "episode": job.episode,
        "seed": job.seed,
        "difficulty": job.difficulty,
        "gpu": job.gpu,
        "recovery_mode": job.recovery_mode,
        "planner_fallback": dict(planner_counters),
        "segmentation_seconds": segmentation_seconds,
        "segmentation_frames": segmentation_frames,
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


def _write_metadata(output: Path, task: str, records: Sequence[Mapping[str, Any]]) -> None:
    """只写**实际成功**的 episode，保证 metadata 与 h5 内容严格一致。"""
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
    gpus: str | Sequence[str | int] = DEFAULT_GPUS,
    split: str = "train",
    reference_root: str | Path = REFERENCE_ROOT,
) -> dict[str, Any]:
    """生成 + 合并。planner 失败的 episode 跳过并记录，不影响其余产物落盘。"""
    if split not in SPLIT_EPISODE_COUNTS:
        raise DatasetGenerationError(f"split 只接受 train/val/test，实际拿到 {split!r}")
    metadata_root = ENV_METADATA_ROOT / split
    reference = Path(reference_root).expanduser()
    _ensure_layout(reference, metadata_root)
    output = _prepare_output(output_dir, reference)
    temporary = output / ".workers"
    results: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "参数": {
            "output_dir": str(output),
            "env": env,
            "episodes": episodes,
            "workers": workers,
            "split": split,
            "metadata_root": str(metadata_root),
            "seed_attempts_per_episode": 1,
            "joint_angle_replay": False,
            "reference_joint_action_comparison": False,
            "record_segmentation": True,
        },
    }
    try:
        limit = SPLIT_EPISODE_COUNTS[split]
        if not 1 <= episodes <= limit:
            raise DatasetGenerationError(f"episodes 必须在 1..{limit} 之间（split={split}）")
        if workers < 1:
            raise DatasetGenerationError("workers 必须大于 0")
        tasks = parse_tasks(env)
        gpu_ids = _parse_gpus(gpus)
        # 主进程自己不渲染，只负责派活与合并；真正决定用哪张卡的是每个 worker 开头那行
        os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)
        records_by_task = read_split_metadata(split, tasks, metadata_root)
        episode_indices = list(range(episodes))
        summary["参数"].update({"tasks": tasks, "gpus": list(gpu_ids)})

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
                            "ok": False,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        }
                    )
        results.sort(key=lambda item: (str(item["task"]), int(item["episode"])))
        successes = [item for item in results if item.get("ok")]
        failures = [item for item in results if not item.get("ok")]

        # ⚠ 这里刻意**不** raise：不回放 joint angle 时 planner 本就可能规划失败，
        # 一条失败让整批作废会让全量生成几乎不可能跑完。失败的跳过、记录，其余照常落盘。
        if not successes:
            raise DatasetGenerationError(
                "全部 episode 都生成失败，没有任何产物可合并："
                + "; ".join(
                    f"{item['task']}/episode_{item['episode']}: {item.get('error_type')}"
                    for item in failures[:8]
                )
            )

        merged_tasks: dict[str, int] = {}
        for task in tasks:
            task_results = [item for item in successes if item["task"] == task]
            if not task_results:
                # 该任务整个失败：不产 h5，也不写 metadata，由摘要如实记录
                continue
            _merge(output, task, task_results)
            _write_metadata(
                output,
                task,
                [records_by_task[task][int(item["episode"])] for item in task_results],
            )
            merged_tasks[task] = len(task_results)

        summary["生成"] = {
            "请求数": len(jobs),
            "成功数": len(successes),
            "失败数": len(failures),
            "逐任务成功数": merged_tasks,
            "失败清单": [
                {
                    "task": item["task"],
                    "episode": item["episode"],
                    "seed": item.get("seed"),
                    "error_type": item.get("error_type"),
                    "error": item.get("error"),
                }
                for item in failures
            ],
            "逐 episode 结果": results,
        }
        summary["status"] = "generated" if not failures else "generated_with_failures"
        write_text_atomic(
            output / SUMMARY_NAME,
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        )
        return summary
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
        summary.setdefault(
            "生成",
            {
                "请求数": len(results),
                "成功数": len([item for item in results if item.get("ok")]),
                "失败数": len([item for item in results if not item.get("ok")]),
                "逐 episode 结果": results,
            },
        )
        try:
            write_text_atomic(
                output / SUMMARY_NAME,
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            )
        except Exception as summary_error:
            raise DatasetGenerationError(
                f"{exc}；此外摘要写入也失败了：{summary_error}"
            ) from exc
        if isinstance(exc, (DatasetGenerationError, DatasetContractError)):
            raise
        raise DatasetGenerationError(str(exc)) from exc
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="带 GT segmentation 的 RoboMME 数据生成（planner 重新规划，不回放 joint angle、"
        "不与官方对拍；失败 episode 跳过并记入 generation_summary.json）"
    )
    parser.add_argument("--output-dir", required=True, help="仓库内的输出目录，必须不存在或为空")
    parser.add_argument("--env", "--environment", default="all", help="all，或逗号分隔的环境名列表")
    parser.add_argument(
        "--episodes",
        type=int,
        default=10,
        help="每个环境从 episode 0 起生成的 episode 数量（默认 10 = 官方前 10 条）",
    )
    parser.add_argument("--workers", "--max-workers", dest="workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--gpus",
        "--gpu",
        dest="gpus",
        default=DEFAULT_GPUS,
        help="逗号分隔的物理卡号（如 0,1）：episode 之间互不耦合，按轮转分到各卡",
    )
    parser.add_argument(
        "--split",
        choices=("train", "val", "test"),
        default="train",
        help="episode seed/difficulty 读哪套 metadata（env_metadata/{train,val,test}）",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        summary = generate_dataset(
            output_dir=args.output_dir,
            env=args.env,
            episodes=args.episodes,
            workers=args.workers,
            gpus=args.gpus,
            split=args.split,
        )
    except (DatasetGenerationError, DatasetContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    generation = summary["生成"]
    print(
        json.dumps(
            {
                "status": summary["status"],
                "成功数": generation["成功数"],
                "失败数": generation["失败数"],
                "摘要": str(Path(summary["参数"]["output_dir"]) / SUMMARY_NAME),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
