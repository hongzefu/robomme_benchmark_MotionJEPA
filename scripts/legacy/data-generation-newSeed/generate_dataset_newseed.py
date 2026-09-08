#!/usr/bin/env python3
"""无 seed 独立生成：seed 由公式自算，失败自动 attempt+1 重试。

与 ``scripts/legacy/data-generation/generate_dataset.py``（复现型，读 train metadata 里的死 seed、
单次尝试、锁死 GPU 0）的差别：

* seed 不再读表，由 ``seed_layout`` 按 ``offset + env_code*env_block + episode*100 + attempt`` 现算
* 单条失败不再让整体 raise，而是 attempt+1 重新入队，直到成功或达到上限
* 每卡一个进程池、进程终身绑卡，支持多 GPU
* 每 worker 的 CPU 线程被压到 1（骨架完全没设，32 核上会严重过度订阅）
* 结果边跑边写 JSONL，中途崩溃不丢已完成的部分
* 不合并 h5（合并见 merge_episode_h5.py）、不做 replay、不与官方 reference 做数值比对

env kwargs、FailRecover 分档、planner 的 screw×3 → RRT*×3 重试、成功判定，
均与骨架逐字相同 —— 本脚本的用途之一是验证当前环境代码与 2025-12 环境代码的行为等价性，
这些口径一旦改动，比对结果就失去意义。
"""

from __future__ import annotations

import os


# ── 线程限制必须在 import numpy 之前生效 ──────────────────────────────────────
# OpenBLAS/libgomp 都是在 .so 加载时读取线程数的，放到进程池 initializer 里已经太晚：
# spawn 的子进程 bootstrap 会重跑本模块顶层（为了还原 _worker 的定义），
# 那时 numpy 已经 import 完毕。所以只能放在顶层、且在 import numpy 之前。
# 父进程解析完 CLI 后会改写 NEWSEED_LIMIT_THREADS 再建池，子进程继承后在这里读到。
_THREAD_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "OPENCV_FOR_THREADS_NUM",
)
LIMIT_THREADS_ENV = "NEWSEED_LIMIT_THREADS"


def _apply_thread_env(value: str) -> None:
    for name in _THREAD_VARS:
        os.environ[name] = value


def _clear_thread_env() -> None:
    for name in _THREAD_VARS:
        os.environ.pop(name, None)


if os.environ.get(LIMIT_THREADS_ENV, "1") != "0":
    _apply_thread_env("1")

import argparse  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import resource  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from collections import deque  # noqa: E402
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait  # noqa: E402
from concurrent.futures.process import BrokenProcessPool  # noqa: E402
from dataclasses import dataclass, replace  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Mapping, Sequence  # noqa: E402

import h5py  # noqa: E402
import numpy as np  # noqa: E402


SCRIPT_DIR = Path(__file__).resolve().parent
CONTRACT_DIR = SCRIPT_DIR.parent / "data-generation"
for _extra in (str(SCRIPT_DIR), str(CONTRACT_DIR)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from validate_generated_dataset_contract import (  # noqa: E402
    MAX_EPISODES,
    inspect_episode_terminal,
    parse_tasks,
)
from write_generation_report import write_text_atomic  # noqa: E402

from seed_layout import (  # noqa: E402
    DEFAULT_LAYOUT,
    LAYOUTS,
    MAX_ATTEMPTS,
    difficulty_for,
    get_layout,
    parse_difficulty_ratio,
)


REPO_ROOT = SCRIPT_DIR.parents[2]
SRC_ROOT = REPO_ROOT / "src"
STICK_TASKS = frozenset(("PatternLock", "RouteStick"))
DEFAULT_WORKERS = 20
DEFAULT_DIFFICULTY_RATIO = "211"
# 每个池进程跑多少个 job 后强制回收：太小则反复付 import/CUDA 上下文成本，
# 太大则 RecordWrapper 的显存/内存残留会跨 episode 累积、且一次段错误牵连更多 job。
DEFAULT_MAX_TASKS_PER_CHILD = 8
# 同一个 episode 连续这么多次非任务性失败（真 bug、池崩溃）就放弃，
# 避免对着一个必然复现的 bug 空转到 attempt 上限
MAX_NON_TASK_STRIKES = 3

# 池进程私有：由 initializer 填，worker 回传供审计（证明确实绑到了预期的物理卡）
_BOUND: dict[str, Any] = {}


class DatasetGenerationError(RuntimeError):
    """生成过程违反约定。"""


class PlannerExhausted(RuntimeError):
    """planner 的 screw 与 RRTStar 重试均已耗尽。"""


@dataclass(frozen=True)
class EpisodeJob:
    task: str
    episode: int
    attempt: int
    seed: int
    difficulty: str
    output_root: str
    repo_root: str

    @property
    def recovery_mode(self) -> str | None:
        """FailRecover 分档按 episode 序号决定，与 seed / attempt 无关（与骨架一致）。"""
        if self.episode <= 2:
            return "z"
        if self.episode <= 5:
            return "xy"
        return None

    def bump(self, seed: int) -> "EpisodeJob":
        return replace(self, attempt=self.attempt + 1, seed=seed)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ensure_layout() -> None:
    """只校验生成必需的路径。

    骨架还要求 ``data/robomme_data_h5``（官方 reference）存在，那是为了跑 1e-8 数值比对；
    本脚本不做该比对，而且该目录在本仓库根本不存在，照搬会直接失败。
    """
    required = (REPO_ROOT / "uv.lock", SRC_ROOT)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise DatasetGenerationError("缺少必需路径：" + ", ".join(missing))


def _prepare_output(value: str | Path) -> Path:
    requested = Path(value).expanduser()
    if requested.is_symlink():
        raise DatasetGenerationError(f"输出目录不能是符号链接：{requested}")
    parent = requested.parent
    while parent != parent.parent:
        if parent.exists() and parent.is_symlink():
            raise DatasetGenerationError(f"输出路径含符号链接父目录：{parent}")
        if parent == REPO_ROOT:
            break
        parent = parent.parent
    output = requested.resolve()
    repo = REPO_ROOT.resolve()
    if output == repo or not _inside(output, repo):
        raise DatasetGenerationError(f"输出目录必须在仓库内：{output}")
    if output.exists():
        if not output.is_dir():
            raise DatasetGenerationError(f"输出路径已存在且不是目录：{output}")
    else:
        output.mkdir(parents=True, exist_ok=True)
    return output


def _parse_gpus(value: str | Sequence[str | int]) -> tuple[str, ...]:
    """解析 --gpus。骨架把它锁死为 "0"，这里放开为逗号分隔的多卡。"""
    raw = value.split(",") if isinstance(value, str) else value
    gpus = tuple(str(item).strip() for item in raw if str(item).strip())
    if not gpus:
        raise DatasetGenerationError("--gpus 不能为空")
    if len(gpus) != len(set(gpus)):
        raise DatasetGenerationError(f"--gpus 有重复项：{gpus}")
    for gpu in gpus:
        if not gpu.isdigit():
            raise DatasetGenerationError(f"--gpus 只接受物理卡号：{gpu!r}")
    return gpus


def _runtime_bool(value: Any, torch_module: Any) -> bool:
    if isinstance(value, torch_module.Tensor):
        if value.numel() != 1:
            raise DatasetGenerationError("evaluate 返回了非标量 Tensor")
        return bool(value.detach().cpu().item())
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise DatasetGenerationError("evaluate 返回了非标量 ndarray")
        return bool(value.item())
    return bool(value)


def _is_failure(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and int(value) == -1


def _planner_classes(
    arm_base: type,
    stick_base: type,
    screw_error: type[BaseException],
) -> tuple[type, type]:
    """局部子类实现 screw 三次 → RRTStar 三次的回退，不做 monkeypatch（与骨架一致）。"""

    class ScrewThenRRT:
        def move_to_pose_with_screw(self, *args: Any, **kwargs: Any) -> Any:
            last_error: BaseException | None = None
            for _ in range(3):
                try:
                    result = super().move_to_pose_with_screw(*args, **kwargs)
                except screw_error as exc:
                    last_error = exc
                    continue
                if not _is_failure(result):
                    return result
            for _ in range(3):
                try:
                    result = super().move_to_pose_with_RRTStar(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    continue
                if not _is_failure(result):
                    return result
            suffix = f": {last_error}" if last_error is not None else ""
            raise PlannerExhausted("screw 三次与 RRTStar 三次均失败" + suffix)

    class NoPatchArm(ScrewThenRRT, arm_base):
        pass

    class NoPatchStick(ScrewThenRRT, stick_base):
        pass

    return NoPatchArm, NoPatchStick


def _execute_tasks(record_env: Any, planner: Any, torch_module: Any, job: EpisodeJob) -> None:
    """成功判定与骨架逐字相同：跑完 task_list 且 evaluate 报 success 真、fail 假。"""
    task_list = list(getattr(record_env.unwrapped, "task_list", []) or [])
    if not task_list:
        raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: task_list 为空")
    for entry in task_list:
        solve = entry.get("solve") if isinstance(entry, Mapping) else None
        if not callable(solve):
            raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: task 没有 solve 方法")
        record_env.unwrapped.evaluate(solve_complete_eval=True)
        result = solve(record_env, planner)
        if _is_failure(result):
            raise PlannerExhausted(f"{job.task}/episode_{job.episode}: solve 返回 -1")
        evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
        if _runtime_bool(evaluation.get("fail", False), torch_module):
            raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: 环境报告失败")
        if _runtime_bool(evaluation.get("success", False), torch_module):
            return
    evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
    if not _runtime_bool(evaluation.get("success", False), torch_module):
        raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: 跑完整个 task_list 仍未成功")


def _raw_summary(path: Path, job: EpisodeJob) -> dict[str, Any]:
    """worker 成功后立刻用共享的合约辅助函数检查原始轨迹的终态。"""
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
            raise DatasetGenerationError(f"{path}/{name}: 末帧 is_completed 不为真")
    return {"h5_path": str(path), "timestep_count": len(timesteps)}


def _h5_path(output_root: Path, job: EpisodeJob) -> Path:
    """与 RecordWrapper 的命名约定一致（RecordWrapper.py:145,152）。"""
    return output_root / "hdf5_files" / f"{job.task}_ep{job.episode}_seed{job.seed}.h5"


def _pool_init(gpu: str, cpus: tuple[int, ...] | None, src_root: str) -> None:
    """池进程一生只跑一次：绑卡、压线程、预热 import。

    绑卡必须早于任何 torch / sapien import —— 此刻 CUDA 尚未初始化（本模块顶层只 import
    了 h5py/numpy，二者不碰 CUDA），所以 setenv 有效且对该进程终身有效。
    GPU 号是池的静态属性（从 initargs 来），因此 worker 被回收或崩溃重建后依然正确。
    """
    global _BOUND
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu

    limit_threads = os.environ.get(LIMIT_THREADS_ENV, "1") != "0"
    if limit_threads:
        _apply_thread_env("1")

    # CPU 亲和会被 ffmpeg 子进程继承 —— x264 按 sched_getaffinity 自动决定线程数，
    # 不看 OMP_NUM_THREADS，这是唯一能在不改 RecordWrapper 的前提下压住它的手段。
    if cpus:
        try:
            os.sched_setaffinity(0, set(cpus))
        except OSError:
            pass

    if src_root not in sys.path:
        sys.path.insert(0, src_root)

    # initializer 里抛异常会让整个池立刻 broken，所以全部包起来
    info: dict[str, Any] = {"gpu": gpu, "pid": os.getpid()}
    try:
        import cv2
        import torch

        if limit_threads:
            torch.set_num_threads(1)
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass  # 已有并行工作启动过就不能再设，忽略
            cv2.setNumThreads(0)

        import gymnasium  # noqa: F401
        import sapien

        import robomme.robomme_env  # noqa: F401
        from robomme.env_record_wrapper import RobommeRecordWrapper  # noqa: F401

        device = sapien.Device("cuda")
        info.update(
            {
                "cuda_id": getattr(device, "cuda_id", None),
                "pci": getattr(device, "pci_string", None),
                "can_render": bool(device.can_render()),
                "torch_threads": torch.get_num_threads(),
            }
        )
    except Exception as exc:
        info["error"] = repr(exc)
    try:
        info["affinity"] = sorted(os.sched_getaffinity(0))
    except OSError:
        pass
    _BOUND = info


def _worker(job: EpisodeJob) -> dict[str, Any]:
    """跑一次 attempt。重试由父进程负责（失败的 job 会带新 seed 重新入队）。"""
    started = time.time()
    clock = time.monotonic()
    phases: dict[str, float] = {}
    output_root = Path(job.output_root)
    raw_path = _h5_path(output_root, job)
    record_env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None

    # import 单独成段：若这里失败，下面的 except 子句会因为异常类未定义而变成 NameError
    try:
        source_root = Path(job.repo_root) / "src"
        if not source_root.is_dir():
            raise DatasetGenerationError(f"src 不存在：{source_root}")
        if str(source_root) not in sys.path:
            sys.path.insert(0, str(source_root))
        import gymnasium as gym
        import torch
        import robomme.robomme_env  # noqa: F401
        from robomme.env_record_wrapper import FailsafeTimeout, RobommeRecordWrapper
        from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
        from robomme.robomme_env.utils.planner_fail_safe import (
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )

        arm_cls, stick_cls = _planner_classes(
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )
    except Exception as exc:
        return {
            "task": job.task,
            "episode": job.episode,
            "attempt": job.attempt,
            "seed": job.seed,
            "difficulty": job.difficulty,
            "recovery_mode": job.recovery_mode,
            "bound": dict(_BOUND),
            "ok": False,
            "failure_class": "code",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "finished_at": time.time(),
        }

    # 这五类是「该 seed 不通」，应当换 seed 重试；其余异常视为代码/环境层面的真 bug
    retryable = (
        SceneGenerationError,
        FailsafeTimeout,
        PlannerExhausted,
        ScrewPlanFailure,
        DatasetGenerationError,
    )

    try:
        # 以下 kwargs 与骨架逐字相同，不要改动
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

        mark = time.monotonic()
        base_env = gym.make(job.task, **kwargs)
        # 产物直接落共享输出根：h5 进 hdf5_files/、视频进 videos/，
        # 文件名已含 task/episode/seed 天然唯一，因此不需要 per-job 的临时目录。
        record_env = RobommeRecordWrapper(
            base_env,
            dataset=str(output_root),
            env_id=job.task,
            episode=job.episode,
            seed=job.seed,
            save_video=True,
        )
        phases["make_s"] = time.monotonic() - mark

        mark = time.monotonic()
        record_env.reset()
        phases["reset_s"] = time.monotonic() - mark

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

        mark = time.monotonic()
        _execute_tasks(record_env, planner, torch, job)
        phases["solve_s"] = time.monotonic() - mark
    except Exception as exc:
        caught = exc
        error_traceback = traceback.format_exc()
    finally:
        if record_env is not None:
            mark = time.monotonic()
            try:
                # h5 落盘与 mp4 编码都发生在 close 里
                record_env.close()
            except Exception as close_exc:
                if caught is None:
                    caught = close_exc
                    error_traceback = traceback.format_exc()
            phases["close_s"] = time.monotonic() - mark

    base = {
        "task": job.task,
        "episode": job.episode,
        "attempt": job.attempt,
        "seed": job.seed,
        "difficulty": job.difficulty,
        "recovery_mode": job.recovery_mode,
        "bound": dict(_BOUND),
        "phases": {name: round(value, 3) for name, value in phases.items()},
        "wall_s": round(time.monotonic() - clock, 3),
        "started_at": started,
        "finished_at": time.time(),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }
    if caught is not None:
        # 失败的 attempt 不写 h5 内容（RecordWrapper.py:1152 只在 episode_success 时写），
        # 但文件在 __init__ 里就被创建了，会留下几 KB 空壳 —— 删掉，
        # 让 hdf5_files/ 里只剩真正成功的轨迹。FAILED_ 视频保留作为失败演进的证据。
        _discard_empty_h5(raw_path, job)
        return {
            **base,
            "ok": False,
            "failure_class": "task" if isinstance(caught, retryable) else "code",
            "error_type": type(caught).__name__,
            "error": str(caught),
            "traceback": error_traceback,
        }
    try:
        return {**base, "ok": True, **_raw_summary(raw_path, job)}
    except Exception as exc:
        _discard_empty_h5(raw_path, job)
        return {
            **base,
            "ok": False,
            "failure_class": "task" if isinstance(exc, retryable) else "code",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _discard_empty_h5(path: Path, job: EpisodeJob) -> None:
    """删掉失败 attempt 留下的空 h5；万一里面确实有内容就保留，交人工判断。"""
    if not path.is_file():
        return
    try:
        with h5py.File(path, "r") as handle:
            if f"episode_{job.episode}" in handle:
                return
    except Exception:
        pass  # 打不开就是坏文件，照删
    try:
        path.unlink()
    except OSError:
        pass


def _synth_failure(job: EpisodeJob, exc: BaseException, failure_class: str) -> dict[str, Any]:
    """worker 进程本身没能返回结果（池崩溃 / 被杀）时，父进程合成一条记录。"""
    return {
        "task": job.task,
        "episode": job.episode,
        "attempt": job.attempt,
        "seed": job.seed,
        "difficulty": job.difficulty,
        "recovery_mode": job.recovery_mode,
        "ok": False,
        "failure_class": failure_class,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "finished_at": time.time(),
    }


def _run_jobs(
    jobs: Sequence[EpisodeJob],
    gpu_ids: Sequence[str],
    workers: int,
    layout_name: str,
    jsonl_path: Path,
    max_attempts: int,
    max_tasks_per_child: int | None,
    cpu_plan: Mapping[str, tuple[int, ...] | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """每卡一个池，按剩余容量动态派发；失败 attempt+1 重新入队；池崩溃则重建。"""
    layout = get_layout(layout_name)
    context = mp.get_context("spawn")
    per_gpu = max(1, workers // len(gpu_ids))

    def new_pool(gpu: str) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=per_gpu,
            mp_context=context,
            initializer=_pool_init,
            initargs=(gpu, cpu_plan.get(gpu), str(SRC_ROOT)),
            max_tasks_per_child=max_tasks_per_child,
        )

    pools = {gpu: new_pool(gpu) for gpu in gpu_ids}
    capacity = {gpu: per_gpu for gpu in gpu_ids}
    pending: deque[EpisodeJob] = deque(jobs)
    inflight: dict[Future, tuple[str, EpisodeJob]] = {}
    succeeded: list[dict[str, Any]] = []
    exhausted: list[dict[str, Any]] = []
    total = len(jobs)
    # 连续的非任务性失败（真 bug、池崩溃）计数，用来避免对着同一个 bug 空转到 attempt 上限
    strikes: dict[tuple[str, int], int] = {}

    with jsonl_path.open("a", buffering=1, encoding="utf-8") as sink:

        def record(result: Mapping[str, Any]) -> None:
            sink.write(json.dumps(result, ensure_ascii=False) + "\n")

        while pending or inflight:
            while pending and any(capacity[gpu] > 0 for gpu in gpu_ids):
                gpu = max(gpu_ids, key=lambda item: capacity[item])
                if capacity[gpu] <= 0:
                    break
                job = pending.popleft()
                inflight[pools[gpu].submit(_worker, job)] = (gpu, job)
                capacity[gpu] -= 1

            if not inflight:
                break
            finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)

            broken: set[str] = set()
            for future in finished:
                gpu, job = inflight.pop(future)
                capacity[gpu] += 1
                try:
                    result = future.result()
                except BrokenProcessPool as exc:
                    broken.add(gpu)
                    result = _synth_failure(job, exc, "infra")
                except BaseException as exc:  # noqa: BLE001
                    result = _synth_failure(job, exc, "infra")
                record(result)
                key = (job.task, job.episode)
                if result.get("ok"):
                    strikes.pop(key, None)
                    succeeded.append(result)
                    print(
                        f"[{len(succeeded)}/{total}] {job.task}/episode_{job.episode} "
                        f"succeeded with seed {job.seed} (attempt {job.attempt}, "
                        f"{result.get('wall_s')}s)",
                        flush=True,
                    )
                    continue

                if result.get("failure_class") == "task":
                    strikes.pop(key, None)
                else:
                    strikes[key] = strikes.get(key, 0) + 1

                if strikes.get(key, 0) >= MAX_NON_TASK_STRIKES:
                    exhausted.append(result)
                    print(
                        f"    {job.task}/episode_{job.episode} 连续 {MAX_NON_TASK_STRIKES} 次非任务性失败"
                        f"（{result.get('error_type')}），判定为代码问题，放弃",
                        flush=True,
                    )
                elif job.attempt + 1 < max_attempts:
                    print(
                        f"    {job.task}/episode_{job.episode} seed {job.seed} failed "
                        f"({result.get('error_type')}), retrying attempt {job.attempt + 1}",
                        flush=True,
                    )
                    pending.append(job.bump(layout.seed(job.task, job.episode, job.attempt + 1)))
                else:
                    exhausted.append(result)
                    print(
                        f"    {job.task}/episode_{job.episode} 用尽 {max_attempts} 次 attempt，放弃",
                        flush=True,
                    )

            # 池整体崩溃（worker 段错误会让 in-flight 与 pending 的 future 全部失败）：
            # 重建该池，并把它名下未完成的 job 退回队列，否则一次段错误就会报废整批任务。
            for gpu in broken:
                print(f"    GPU {gpu} 的进程池已损坏，正在重建", flush=True)
                for future, (owner, job) in list(inflight.items()):
                    if owner != gpu:
                        continue
                    inflight.pop(future)
                    capacity[gpu] += 1
                    record(_synth_failure(job, RuntimeError("池重建，任务退回队列"), "infra"))
                    if job.attempt + 1 < max_attempts:
                        pending.appendleft(
                            job.bump(layout.seed(job.task, job.episode, job.attempt + 1))
                        )
                    else:
                        exhausted.append(_synth_failure(job, RuntimeError("池重建且已用尽 attempt"), "infra"))
                try:
                    pools[gpu].shutdown(wait=False, cancel_futures=True)
                except Exception:  # noqa: BLE001
                    pass
                pools[gpu] = new_pool(gpu)
                capacity[gpu] = per_gpu

    for pool in pools.values():
        try:
            pool.shutdown(wait=True)
        except Exception:  # noqa: BLE001
            pass
    return succeeded, exhausted


def _write_metadata(output: Path, task: str, records: Sequence[Mapping[str, Any]]) -> None:
    """写出与 src/robomme/env_metadata 同构的 metadata（字段：task/episode/seed/difficulty）。"""
    payload = {
        "env_id": task,
        "record_count": len(records),
        "records": [
            {
                "task": str(item["task"]),
                "episode": int(item["episode"]),
                "seed": int(item["seed"]),
                "difficulty": str(item["difficulty"]),
            }
            for item in sorted(records, key=lambda item: int(item["episode"]))
        ],
    }
    write_text_atomic(
        output / f"record_dataset_{task}_metadata.json",
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _cpu_plan(gpu_ids: Sequence[str], affinity: str) -> dict[str, tuple[int, ...] | None]:
    """把物理核按卡切分。exclusive 模式下每个池只能用自己那一段，用于压住 x264 的自动并行。"""
    if affinity == "none":
        return {gpu: None for gpu in gpu_ids}
    try:
        available = sorted(os.sched_getaffinity(0))
    except OSError:
        available = list(range(os.cpu_count() or 1))
    chunk = max(1, len(available) // len(gpu_ids))
    plan: dict[str, tuple[int, ...] | None] = {}
    for index, gpu in enumerate(gpu_ids):
        start = index * chunk
        end = len(available) if index == len(gpu_ids) - 1 else start + chunk
        plan[gpu] = tuple(available[start:end])
    return plan


def generate_dataset_newseed(
    output_dir: str | Path,
    env: str = "all",
    episodes: int = MAX_EPISODES,
    episode_start: int = 0,
    workers: int = DEFAULT_WORKERS,
    gpus: str | Sequence[str | int] = "0",
    difficulty_ratio: str = DEFAULT_DIFFICULTY_RATIO,
    layout_name: str = DEFAULT_LAYOUT,
    max_attempts: int = MAX_ATTEMPTS,
    limit_threads: bool = True,
    max_tasks_per_child: int | None = DEFAULT_MAX_TASKS_PER_CHILD,
    affinity: str = "none",
) -> dict[str, Any]:
    _ensure_layout()
    if episodes < 1:
        raise DatasetGenerationError("episodes 必须大于 0")
    if episode_start < 0:
        raise DatasetGenerationError("episode-start 必须不小于 0")
    if workers < 1:
        raise DatasetGenerationError("workers 必须大于 0")
    if not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise DatasetGenerationError(f"max-attempts 必须落在 1..{MAX_ATTEMPTS}")

    output = _prepare_output(output_dir)
    tasks = parse_tasks(env)
    gpu_ids = _parse_gpus(gpus)
    layout = get_layout(layout_name)
    cycle = parse_difficulty_ratio(difficulty_ratio)

    # 护栏：episode 号太大时 seed 会越过下一代布局的 offset，与 test/val/heldout 的 seed 空间相撞。
    next_offsets = [item.offset for item in LAYOUTS.values() if item.offset > layout.offset]
    if next_offsets:
        seed_ceiling = min(next_offsets)
        last_episode = episode_start + episodes - 1
        for task in tasks:
            max_seed = layout.seed(task, last_episode, MAX_ATTEMPTS - 1)
            if max_seed >= seed_ceiling:
                raise DatasetGenerationError(
                    f"{task} episode {last_episode} 的最大可能 seed {max_seed} "
                    f"越过下一代布局的 offset {seed_ceiling}，请缩小 episode 范围"
                )

    # 父进程在建池之前定好线程环境；spawn 的子进程会继承，
    # 并在重跑本模块顶层时（早于 import numpy）据此设置 OpenBLAS/libgomp。
    os.environ[LIMIT_THREADS_ENV] = "1" if limit_threads else "0"
    if limit_threads:
        _apply_thread_env("1")
    else:
        _clear_thread_env()

    jobs = [
        EpisodeJob(
            task=task,
            episode=episode,
            attempt=0,
            seed=layout.seed(task, episode, 0),
            difficulty=difficulty_for(episode, cycle),
            output_root=str(output),
            repo_root=str(REPO_ROOT),
        )
        for task in tasks
        for episode in range(episode_start, episode_start + episodes)
    ]

    parameters = {
        "output_dir": str(output),
        "env": env,
        "tasks": tasks,
        "episodes": episodes,
        "episode_start": episode_start,
        "workers": workers,
        "gpus": list(gpu_ids),
        "seed_layout": layout_name,
        "difficulty_ratio": difficulty_ratio,
        "difficulty_cycle": list(cycle),
        "max_attempts": max_attempts,
        "limit_threads": limit_threads,
        "max_tasks_per_child": max_tasks_per_child,
        "affinity": affinity,
        "save_video_for_recording": True,
    }
    write_text_atomic(
        output / "run_parameters.json",
        json.dumps(parameters, ensure_ascii=False, indent=2) + "\n",
    )

    started = time.monotonic()
    succeeded, exhausted = _run_jobs(
        jobs=jobs,
        gpu_ids=gpu_ids,
        workers=workers,
        layout_name=layout_name,
        jsonl_path=output / "episode_results.jsonl",
        max_attempts=max_attempts,
        max_tasks_per_child=max_tasks_per_child,
        cpu_plan=_cpu_plan(gpu_ids, affinity),
    )
    elapsed = time.monotonic() - started

    for task in tasks:
        task_records = [item for item in succeeded if item["task"] == task]
        if task_records:
            _write_metadata(output, task, task_records)

    summary = {
        "parameters": parameters,
        "requested_count": len(jobs),
        "success_count": len(succeeded),
        "exhausted_count": len(exhausted),
        "elapsed_s": round(elapsed, 1),
        "throughput_ep_per_min": round(len(succeeded) / (elapsed / 60), 2) if elapsed > 0 else None,
        "peak_rss_mb": max((item.get("peak_rss_mb") or 0 for item in succeeded), default=0),
    }
    write_text_atomic(
        output / "run_summary.json",
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    return summary


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="无 seed 独立生成：seed 由公式自算，失败自动 attempt+1 重试"
    )
    parser.add_argument("--output-dir", required=True, help="仓库内的输出目录")
    parser.add_argument("--env", "--environment", default="all", help="all 或逗号分隔的环境名")
    parser.add_argument("--episodes", type=int, default=MAX_EPISODES, help="每个环境的条数（配合 --episode-start）")
    parser.add_argument(
        "--episode-start",
        type=int,
        default=0,
        help="起始 episode 号（默认 0）；难度循环与 seed 都按绝对 episode 号计算，接续生成时口径自然延续",
    )
    parser.add_argument("--workers", "--max-workers", dest="workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--gpus", "--gpu", dest="gpus", default="0", help="逗号分隔的物理卡号，如 0,1")
    parser.add_argument(
        "--difficulty",
        dest="difficulty_ratio",
        default=DEFAULT_DIFFICULTY_RATIO,
        help="难度循环比例，三位数字对应 easy/medium/hard，如 211",
    )
    parser.add_argument("--layout", default=DEFAULT_LAYOUT, choices=sorted(LAYOUTS), help="seed 布局代")
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS, help="单个 episode 的最大 attempt 数")
    parser.add_argument(
        "--no-limit-threads",
        dest="limit_threads",
        action="store_false",
        help="不把每个 worker 的 CPU 线程压到 1（用于并行度标定的对照组）",
    )
    parser.add_argument(
        "--max-tasks-per-child",
        type=int,
        default=DEFAULT_MAX_TASKS_PER_CHILD,
        help="每个池进程跑多少 job 后回收，0 表示永不回收",
    )
    parser.add_argument(
        "--affinity",
        default="none",
        choices=("none", "per-gpu"),
        help="per-gpu 时把物理核按卡切分并绑定，用于压住 ffmpeg/x264 的自动并行",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        summary = generate_dataset_newseed(
            output_dir=args.output_dir,
            env=args.env,
            episodes=args.episodes,
            episode_start=args.episode_start,
            workers=args.workers,
            gpus=args.gpus,
            difficulty_ratio=args.difficulty_ratio,
            layout_name=args.layout,
            max_attempts=args.max_attempts,
            limit_threads=args.limit_threads,
            max_tasks_per_child=args.max_tasks_per_child or None,
            affinity=args.affinity,
        )
    except DatasetGenerationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["exhausted_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
