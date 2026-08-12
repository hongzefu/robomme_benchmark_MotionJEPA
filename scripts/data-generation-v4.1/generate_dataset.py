#!/usr/bin/env python3
"""RoboMME 数据生成入口（v4：在 v2.1 基础上多落一份 GT segmentation）。

一次完整调用依次做四件事：**并行生成 → 按任务合并 → 契约校验与参考对拍 → 写报告**，
整套流程逐字沿用 v2.1，本文件相对它只有三处「只增」的差别：

- 换用 `record_wrapper_v4.RobommeRecordWrapperV4`（薄子类的薄子类，父类一字未改）；
- 新增 `--segmentation` / `--no-segmentation`：把父类本来就缓存着的
  `front_camera_segmentation` 逐帧写进 `timestep_<k>/obs/`，**默认开启**——
  这是 v4 存在的唯一理由，三类像素分布与验证尺子都取自它；
- `--masked-rgb` 的默认值从开改为**关**：有了真 segmentation 之后，v2.1 那张
  `front_rgb_masked` 对 v4 已无用处，关掉可省下约 23% 的 h5 体积与一点写盘时间；
  需要交叉对照时显式传 `--masked-rgb` 即可。

另有一处**放宽**：`--gpus` 接受多卡（如 `0,1`）。v2.1 把生成锁死在物理 GPU 0 上是为了
与官方参考数据逐位对拍时消除扰动源；v4 产物自成一体、不与任何既有产物对拍，而 episode
之间本来就互不耦合，因此按轮转把 episode 分到多张卡上跑，纯粹是拿满机器。

flow 仍然默认开启：`setup/flow_objects` 与 `setup/flow_excluded` 里的 seg_id 枚举表
是 v4 把 seg id 映射成「背景 / 物体 / 机械臂」三类的唯一依据，关掉 flow 就没有这张表。

其余模块（flow 采集、遮蔽图、契约校验、报告写入）一律直接 import
`scripts/data-generation-v2.1/` 下的现成实现，不拷贝不重写，避免同一口径出现第二份。
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
# 校验、报告、flow、遮蔽图四件套一律复用 v2.1 的现成实现，v4 目录只放自己新增的东西
V21_DIR = SCRIPT_DIR.parent / "data-generation-v2.1"
for _path in (SCRIPT_DIR, V21_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from validate_generated_dataset_contract import (
    MAX_EPISODES,
    METADATA_ROOT,
    REFERENCE_ROOT,
    DatasetContractError,
    inspect_episode_terminal,
    parse_tasks,
    read_train_metadata,
)
import write_generation_report as _report_module
from write_generation_report import (
    build_validation_report,
    new_generation_report,
    write_generation_report,
    write_text_atomic,
)

# 报告模块把落点写死成「自己所在目录 / reports」，直接复用会覆盖 v2.1 已归档的报告。
# 这里把模块级落点改指到 v4 目录——写报告的函数体读的就是这个模块全局名。
_report_module.REPORTS_ROOT = SCRIPT_DIR / "reports"


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
STICK_TASKS = frozenset(("PatternLock", "RouteStick"))
DEFAULT_WORKERS = 20
GPU_ID = "0"


class DatasetGenerationError(RuntimeError):
    """生成、合并或生成后的验收环节不满足既定契约。"""


# 各 split 的 episode 条数是 benchmark 定死的（readme：train 100，val/test 各 50）
SPLIT_EPISODE_COUNTS = {"train": 100, "val": 50, "test": 50}


def _read_split_metadata(
    metadata_root: Path, split: str
) -> dict[str, dict[int, dict[str, Any]]]:
    """按 split 读取 seed/difficulty metadata。

    v2.1 的 `read_train_metadata` 把「恰好 100 条、episode 0..99」写死成 train 口径，
    val/test 每任务只有 50 条，直接调用必炸。v2.1 是被 v2.1/v4 共享的冻结实现，不动它；
    这里对 train 仍走原函数（校验一字不差），对 val/test 本地复刻同等强度的校验、只把
    条数换成该 split 的定值。
    """
    if split == "train":
        return read_train_metadata(metadata_root=metadata_root)
    expected = SPLIT_EPISODE_COUNTS[split]
    all_records: dict[str, dict[int, dict[str, Any]]] = {}
    for task in parse_tasks("all"):
        path = Path(metadata_root) / f"record_dataset_{task}_metadata.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetGenerationError(f"读取 {path} 失败：{exc}") from exc
        if payload.get("env_id") != task:
            raise DatasetGenerationError(f"{path}: env_id 不匹配")
        records = payload.get("records")
        if not isinstance(records, list) or len(records) != expected:
            raise DatasetGenerationError(
                f"{path}: {split} split 的 records 必须恰好 {expected} 条"
            )
        if int(payload.get("record_count", -1)) != len(records):
            raise DatasetGenerationError(f"{path}: record_count 与 records 长度不相等")
        indexed: dict[int, dict[str, Any]] = {}
        for record in records:
            if any(key not in record for key in ("task", "episode", "seed", "difficulty")):
                raise DatasetGenerationError(f"{path}: record 缺少 task/episode/seed/difficulty")
            if record["task"] != task:
                raise DatasetGenerationError(f"{path}: record 的 task 不匹配")
            episode = int(record["episode"])
            if episode in indexed:
                raise DatasetGenerationError(f"{path}: episode {episode} 重复出现")
            difficulty = record["difficulty"]
            if not isinstance(difficulty, str) or not difficulty:
                raise DatasetGenerationError(f"{path}: difficulty 必须是非空字符串")
            indexed[episode] = {
                "task": task,
                "episode": episode,
                "seed": int(record["seed"]),
                "difficulty": difficulty,
            }
        if set(indexed) != set(range(expected)):
            raise DatasetGenerationError(f"{path}: episode 集合必须恰好是 0..{expected - 1}")
        all_records[task] = indexed
    return all_records


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
    record_segmentation: bool = False

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


def _ensure_layout(reference_root: Path, metadata_root: Path) -> None:
    required = (REPO_ROOT / "uv.lock", SRC_ROOT, metadata_root, reference_root)
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
    """解析 --gpus，允许多卡（v4 相对 v2.1 的唯一放宽处）。

    v2.1 把生成锁死在物理 GPU 0 上，理由是与官方参考数据逐位对拍时要消除一切扰动源。
    v4 产物是自成一体的新数据集，**不与任何既有产物对拍**，多卡只是把互不相干的
    episode 分到两张卡上跑，episode 之间本来就没有任何耦合，因此这里放开限制。
    每个 worker 进程在 ``_worker`` 里各自设 ``CUDA_VISIBLE_DEVICES=job.gpu``，
    job 按轮转分配（见 ``generate_dataset``）。
    """
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
    segmentation_seconds = 0.0
    segmentation_frames = 0
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

        # v4 链路在 v2.1 子类之上再多落一份 GT segmentation；三个开关都关时行为与父类完全一致
        from record_wrapper_v4 import RobommeRecordWrapperV4

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
        record_env = RobommeRecordWrapperV4(
            base_env,
            dataset=str(worker_dir),
            env_id=job.task,
            episode=job.episode,
            seed=job.seed,
            save_video=True,
            record_flow=job.record_flow,
            record_masked_rgb=job.record_masked_rgb,
            record_segmentation=job.record_segmentation,
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
            segmentation_seconds = float(getattr(record_env, "segmentation_seconds", 0.0))
            segmentation_frames = int(getattr(record_env, "segmentation_frames", 0))

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
        "record_segmentation": bool(job.record_segmentation),
        "planner_fallback": dict(planner_counters),
        "flow_capture_ms_per_step": flow_capture_ms_per_step,
        "flow_capture_count": flow_capture_count,
        "masked_rgb_seconds": masked_rgb_seconds,
        "masked_rgb_frames": masked_rgb_frames,
        "masked_rgb_painted_pixels": masked_rgb_painted_pixels,
        "masked_rgb_black_exempt_pixels": masked_rgb_black_exempt_pixels,
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
    record_masked_rgb: bool = False,
    record_segmentation: bool = True,
    reference_validation: bool = True,
    split: str = "train",
) -> dict[str, Any]:
    """在同一个进程内完成生成、合并，以及拆分开的契约校验与数值对拍。"""
    if split not in ("train", "val", "test"):
        raise DatasetGenerationError(f"split 只接受 train/val/test，实际拿到 {split!r}")
    # 三套 split 的 metadata 平行放在 env_metadata/{train,val,test}/，seed 与 difficulty
    # 逐 episode 固定；这里只换读取目录，生成侧其余口径（seed 单次尝试、difficulty 透传）不变
    metadata_root = METADATA_ROOT.parent / split
    reference = Path(reference_root).expanduser().resolve()
    _ensure_layout(reference, metadata_root)
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
            "split": split,
            "metadata_root": str(metadata_root),
            "reference_root": str(reference),
            "max_abs_diff": 1e-8,
            "seed_attempts_per_episode": 1,
            "save_video_for_recording": True,
            "record_flow": bool(record_flow),
            "record_masked_rgb": bool(record_masked_rgb),
            "record_segmentation": bool(record_segmentation),
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
        # 主进程自己不渲染，只负责派活与合并；这里让它看见全部目标卡即可，
        # 真正决定用哪张卡的是每个 worker 进程开头那行 CUDA_VISIBLE_DEVICES=job.gpu
        os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)
        records_by_task = _read_split_metadata(metadata_root, split)
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
                        record_segmentation=bool(record_segmentation),
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
                metadata_root=metadata_root,
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
    parser = argparse.ArgumentParser(description="RoboMME 数据生成与校验（v4，在 v2.1 之上多落一份 GT segmentation）；最新的完整报告始终写到 scripts/data-generation-v4/reports/ 下的 generation_report.json 与 generation_report.md")
    parser.add_argument("--output-dir", required=True, help="仓库内的输出目录，必须不存在或为空")
    parser.add_argument("--env", "--environment", default="all", help="all，或逗号分隔的环境名列表")
    parser.add_argument(
        "--episodes",
        type=int,
        default=MAX_EPISODES,
        help="每个环境从 episode 0 起生成的 episode 数量",
    )
    parser.add_argument("--workers", "--max-workers", dest="workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--gpus",
        "--gpu",
        dest="gpus",
        default=GPU_ID,
        help="逗号分隔的物理卡号（v4 放开多卡，如 0,1）：episode 之间互不耦合，按轮转分到各卡",
    )
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
        default=False,
        help="写入 obs/front_rgb_masked（v4 默认关闭）：白名单只把机器人 link 涂成纯棕色，"
        "夹爪指尖的黑色像素逐像素豁免。有了真 segmentation 之后 v4 用不上它，"
        "只在需要与 v2.1 交叉对照时才显式打开",
    )
    parser.add_argument(
        "--segmentation",
        dest="record_segmentation",
        action="store_true",
        default=True,
        help="写入 obs/front_camera_segmentation（默认开启，v4 链路的存在意义）："
        "父类本来就缓存着这张 GT segmentation，只是写盘那行是注释状态",
    )
    parser.add_argument(
        "--no-segmentation",
        dest="record_segmentation",
        action="store_false",
        help="关闭 segmentation 落盘；与 --no-flow 合用即退化为与父类 RecordWrapper 完全一致",
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
    parser.add_argument(
        "--split",
        choices=("train", "val", "test"),
        default="train",
        help="episode seed/difficulty 读哪套 metadata（env_metadata/{train,val,test}）；"
        "官方参考数据只有 train，val/test 须配 --no-reference-validation",
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
            record_segmentation=args.record_segmentation,
            reference_validation=args.reference_validation,
            split=args.split,
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
