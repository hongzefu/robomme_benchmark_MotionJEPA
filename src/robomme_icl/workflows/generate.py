"""按冻结套件生成数据，恢复时核对内容及设备绑定。"""

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

from .workers import run_episode_process, new_manager, gpu_limits, run_jobs
from .staging import _run_staged

def generate_one(
    spec: Any,
    path: str | Path,
    *,
    runner: Callable[[Any, Path], Path] | None = None,
    expected_content_hash: str | None = None,
    expected_runtime_fingerprint: dict[str, Any] | None = None,
    timeout_seconds: float = 240,
) -> dict[str, Any]:
    """断点只接受完整且同规格的记录；任务失败不换 seed。"""
    target = output_path(path, create_parent=True)
    render_gpu = _render_gpu_from_fingerprint(expected_runtime_fingerprint) if expected_runtime_fingerprint is not None else 0
    operation = runner or (lambda candidate, destination: run_episode_process(candidate, destination, timeout_seconds=timeout_seconds, render_gpu=render_gpu))
    record, resumed = _run_staged(spec, target, operation, fingerprint=expected_runtime_fingerprint,
                                 content_hash=expected_content_hash)
    return {"seed": spec.seed, "spec_hash": spec.spec_hash, "path": str(target), "resumed": resumed, "content_hash": record.content_hash}


def _render_gpu_from_fingerprint(fingerprint: dict[str, Any]) -> int:
    gpu = fingerprint.get("render_gpu")
    if type(gpu) is not int or gpu < 0:
        raise RecordError("认证记录缺少有效物理 GPU 绑定，禁止换卡重建")
    return gpu


def generate_spec_job(job: dict) -> dict[str, Any]:
    """记录的读取、恢复和逐字节核对在独立进程内完成。"""
    stop = job["stop"]
    if stop.is_set():
        raise RecordError("其他生成任务已失败，停止后续生成")
    try:
        spec = EpisodeSpec.from_dict(job["episode_spec"])
        certification = job["certification"]
        fingerprint = certification.get("runtime_fingerprint")
        if not fingerprint or not certification.get("content_hash"):
            raise RecordError("套件认证缺少运行指纹或逐帧内容摘要")
        render_gpu = _render_gpu_from_fingerprint(fingerprint)
        if certification.get("render_gpu") != render_gpu:
            raise RecordError("套件 GPU 绑定与认证指纹不一致")
        assert_identical(fingerprint, runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
        path = Path(job["output"]) / spec.task_kind / f"seed_{spec.seed}.h5"

        def run(candidate: Any, destination: Path) -> Path:
            with job["gpu_limit"]:
                if stop.is_set():
                    raise RecordError("其他生成任务已失败，停止启动后续物理进程")
                return run_episode_process(candidate, destination, timeout_seconds=job["timeout_seconds"], render_gpu=render_gpu)

        result = generate_one(spec, path, expected_content_hash=certification["content_hash"],
                              expected_runtime_fingerprint=fingerprint, runner=run, timeout_seconds=job["timeout_seconds"])
        print(f"{'已复用' if result['resumed'] else '已生成'} {spec.task_kind} seed={spec.seed} GPU={render_gpu}", flush=True)
        return {**result, "render_gpu": render_gpu}
    except BaseException:
        stop.set()
        raise


def generate_suite(
    suite_path: str | Path,
    output_dir: str | Path,
    *,
    tasks: Sequence[str] | None = None,
    episodes_per_task: int | None = None,
    workers: int = 32,
    timeout_seconds: float = 240,
) -> list[dict[str, Any]]:
    from ..io.suite import load_suite

    if workers < 1:
        raise ValueError("workers 必须大于零")
    suite = load_suite(suite_path)
    from ..runtime import configure_runtime
    configure_runtime()
    fingerprint = runtime_fingerprint()
    specs = [EpisodeSpec.from_dict(value) for value in suite["episodes"]]
    if tasks is not None:
        requested = set(tasks)
        found = {spec.task_kind for spec in specs}
        if not requested <= found:
            raise ValueError(f"套件缺少任务：{sorted(requested - found)}")
        specs = [spec for spec in specs if spec.task_kind in requested]
    if episodes_per_task is not None:
        if episodes_per_task < 1:
            raise ValueError("episodes_per_task 必须大于零")
        counts: dict[str, int] = {}
        selected = []
        for spec in specs:
            if counts.get(spec.task_kind, 0) < episodes_per_task:
                selected.append(spec)
                counts[spec.task_kind] = counts.get(spec.task_kind, 0) + 1
        specs = selected
    output = output_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with new_manager() as manager:
        stop = manager.Event()
        gpus = sorted({_render_gpu_from_fingerprint(suite["certification"][spec.spec_hash]["runtime_fingerprint"]) for spec in specs})
        limits = gpu_limits(manager, gpus, workers)
        jobs = [{"episode_spec": spec.to_dict(), "certification": suite["certification"][spec.spec_hash],
                 "gpu_limit": limits[_render_gpu_from_fingerprint(suite["certification"][spec.spec_hash]["runtime_fingerprint"])],
                 "output": str(output), "timeout_seconds": timeout_seconds, "stop": stop} for spec in specs]
        results = run_jobs(generate_spec_job, jobs, workers, stop)
    assert_identical(fingerprint, runtime_fingerprint(), path="runtime_fingerprint")
    return results
