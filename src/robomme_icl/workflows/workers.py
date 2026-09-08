"""工作进程隔离、设备并发、超时和同规格基础设施重试。"""

from __future__ import annotations

from pathlib import Path
import json
import os
import time
from typing import Any, Callable, Mapping, Sequence

import h5py

from ..errors import CandidateRejected, InfrastructureError
from ..specs import EpisodeSpec
from ..io.paths import output_path
from ..io.fingerprint import runtime_fingerprint, source_commit
from ..io.hdf5 import (
    EpisodeRecord, RecordError, ReproducibilityError, assert_identical,
    assert_records_identical, read_episode, write_episode,
)
from ..validation.reproducibility import check_terminal

import multiprocessing as mp
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from ..validation.reproducibility import replay_frames

def _child_run(connection: Any, spec_data: dict[str, Any], target: str, replay_source: str | None, render_gpu: int) -> None:
    """每次调用运行在一个全新的 spawn 进程中，管道只传小型状态。"""
    env = None
    started = time.monotonic()
    try:
        from ..api import make_env_from_spec
        from ..execution.episode import run_episode

        fingerprint = runtime_fingerprint(render_gpu=render_gpu)
        commit = source_commit()
        spec = EpisodeSpec.from_dict(spec_data)
        env = make_env_from_spec(spec, record_demonstration=True, render_gpu=render_gpu)
        from ..validation.geometry import validate_scene_geometry
        geometry = validate_scene_geometry(env.unwrapped, spec)
        if not geometry["ok"]:
            raise CandidateRejected("；".join(geometry["reasons"]))
        env.geometry_report = geometry
        built = time.monotonic()
        if replay_source is None:
            frames = run_episode(env)
        else:
            frames = replay_frames(env, read_episode(replay_source))
        check_terminal(frames)
        executed = time.monotonic()
        env.close()
        env = None
        assert_identical(fingerprint, runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
        write_started = time.monotonic()
        write_episode(target, spec, frames, runtime_fingerprint=fingerprint, source_commit=commit)
        timings = {"build_seconds": built-started, "run_seconds": executed-built,
                   "write_seconds": time.monotonic()-write_started}
        # 耗时只进入日志和控制消息，不写入需要逐位相同的轨迹内容。
        print(f"ICL_TIMING seed={spec.seed} GPU={render_gpu} frames={len(frames)} " + json.dumps(timings, sort_keys=True), flush=True)
        connection.send({"ok": True, "path": target, "timings": timings})
    except BaseException as exc:
        from ..errors import ReproducibilityError as SharedReproducibilityError, SceneRejected, TaskExecutionError

        if isinstance(exc, (SceneRejected, TaskExecutionError, CandidateRejected)):
            kind = "candidate"
        elif isinstance(exc, SharedReproducibilityError):
            kind = "reproducibility"
        elif isinstance(exc, (OSError, TimeoutError, InterruptedError)) and not isinstance(exc, FileExistsError):
            kind = "infrastructure"
        else:
            kind = "fatal"
        connection.send({"ok": False, "kind": kind, "error": str(exc), "type": type(exc).__name__, "traceback": traceback.format_exc()})
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:
                # 主过程的失败证据优先，不让关闭异常掩盖原始诊断。
                pass
        connection.close()


def run_episode_process(
    spec: Any,
    target: str | Path,
    *,
    replay_source: str | Path | None = None,
    timeout_seconds: float = 240,
    render_gpu: int = 0,
) -> Path:
    """独立进程执行完整 episode，不使用会残留 RNG 的常驻 worker。"""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必须大于零")
    if type(render_gpu) is not int or render_gpu < 0:
        raise ValueError("render_gpu 必须为非负物理 GPU 编号")
    target = output_path(target, create_parent=True)
    if target.exists():
        raise FileExistsError(f"拒绝覆盖已有记录：{target}")
    # spawn 进程导入 numpy 之前便继承这些线程和缓存配置。
    from ..runtime import configure_runtime
    configure_runtime()
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_child_run,
        args=(sender, spec.to_dict(), str(target), str(replay_source) if replay_source else None, render_gpu),
    )
    process.start()
    sender.close()
    deadline = time.monotonic() + timeout_seconds
    message = None
    try:
        while time.monotonic() < deadline:
            if receiver.poll(0.1):
                try:
                    message = receiver.recv()
                except EOFError:
                    pass
                break
            if not process.is_alive():
                break
        if message is None:
            raise InfrastructureError(f"子进程无结果，seed={spec.seed}，exitcode={process.exitcode}")
    finally:
        receiver.close()
        process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
    if not message["ok"]:
        details = f"{message['type']}: {message['error']}\n{message['traceback']}"
        error_cls = {
            "candidate": CandidateRejected,
            "infrastructure": InfrastructureError,
            "reproducibility": ReproducibilityError,
        }.get(message["kind"], RecordError)
        raise error_cls(details)
    return Path(message["path"])


def retry_same_spec(spec: Any, operation: Callable[[Any], Any], *, retries: int = 2) -> Any:
    """基础设施最多额外重试两次，绝不换 seed 或重新编译配置。"""
    for attempt in range(retries + 1):
        try:
            return operation(spec)
        except (OSError, TimeoutError, InterruptedError) as exc:
            if isinstance(exc, FileExistsError) or attempt == retries:
                raise
            print(f"基础设施重试 {attempt + 1}/{retries}：seed={spec.seed} spec_hash={spec.spec_hash}：{exc}", flush=True)
    raise AssertionError("基础设施重试循环不应落空")


def new_manager():
    return mp.get_context("spawn").Manager()


def gpu_limits(manager: Any, gpus: Sequence[int], workers: int) -> dict[int, Any]:
    """限制每卡真实渲染并发；少 worker 时仍能顺序使用全部指定卡。"""
    return {gpu: manager.BoundedSemaphore(max(1, workers // len(gpus) + (index < workers % len(gpus))))
            for index, gpu in enumerate(sorted(gpus))}


def run_jobs(operation: Callable, jobs: Sequence[dict], workers: int, stop: Any) -> list[Any]:
    """复用纯 CPU/I/O worker，并限制在途数量，避免停止时补建无用进程。"""
    results = [None] * len(jobs)
    executor = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"))
    futures = {}
    next_index = 0

    def fill_available() -> None:
        nonlocal next_index
        while next_index < len(jobs) and len(futures) < workers and not stop.is_set():
            future = executor.submit(operation, jobs[next_index])
            futures[future] = next_index
            next_index += 1

    try:
        fill_available()
        while futures:
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            # 先处理这一批全部结果；任何失败都不能触发后续队列补充。
            for future in sorted(completed, key=lambda item: futures[item]):
                index = futures.pop(future)
                results[index] = future.result()
            fill_available()
        if next_index < len(jobs):
            raise RecordError("调度已停止，未提交剩余 CPU/I/O 任务")
        return results
    except BaseException:
        stop.set()
        for future in futures:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
