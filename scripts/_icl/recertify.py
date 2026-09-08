"""对既有冻结场景重新认证；只允许新版源码变化，不重新选候选。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from robomme_icl.errors import ReproducibilityError as SharedReproducibilityError, SceneRejected
from robomme_icl.geometry import validate_spec_geometry
from robomme_icl.io.fingerprint import runtime_fingerprint, source_commit
from robomme_icl.io.hdf5 import (
    RecordError, ReproducibilityError, assert_identical,
    assert_records_identical, read_episode,
)
from robomme_icl.io.paths import output_path
from robomme_icl.io.pipeline import (
    CandidateRejected, _bind_context, _exclusive_json, _gpu_limits,
    _new_manager, _read_json, _render_gpu_from_fingerprint, _run_process_jobs,
    _validate_record, retry_same_spec, run_fresh_process,
)
from robomme_icl.runtime import configure_runtime
from robomme_icl.suite import EpisodeSpec, load_suite, save_suite


def _compatible_fingerprint(previous: dict, current: dict) -> None:
    """仅源码迁移可触发重新认证，其余运行条件必须完全相同。"""
    for fingerprint in (previous, current):
        if not isinstance(fingerprint, dict) or not fingerprint.get("icl_source_hash"):
            raise RecordError("重新认证要求旧、新指纹均包含 icl_source_hash")
    assert_identical(
        {key: value for key, value in previous.items() if key != "icl_source_hash"},
        {key: value for key, value in current.items() if key != "icl_source_hash"},
        path="重新认证运行条件（只允许 icl_source_hash 变化）",
    )


def _select_specs(suite: dict, tasks: Sequence[str] | None, episodes_per_task: int | None) -> list:
    """按源清单原顺序筛选，保留全局 seed、原 episode 编号和完整 spec。"""
    specs = [EpisodeSpec.from_dict(row) for row in suite["episodes"]]
    if tasks is not None:
        available = {spec.task_kind for spec in specs}
        if not tasks or len(set(tasks)) != len(tasks) or not set(tasks) <= available:
            raise ValueError(f"tasks 必须为源清单中不重复的任务名：{sorted(available)}")
        specs = [spec for spec in specs if spec.task_kind in set(tasks)]
    if episodes_per_task is not None:
        if type(episodes_per_task) is not int or episodes_per_task < 1:
            raise ValueError("episodes_per_task 必须为正整数")
        counts, selected = {}, []
        for spec in specs:
            if counts.get(spec.task_kind, 0) < episodes_per_task:
                selected.append(spec)
                counts[spec.task_kind] = counts.get(spec.task_kind, 0) + 1
        specs = selected
    return specs


def _source_record_paths(certification: dict, source_dir: Path) -> list[Path]:
    """源记录只读且必须为两个独立实体文件，不能用同一文件冒充重复运行。"""
    paths = certification.get("record_paths")
    if not isinstance(paths, list) or len(paths) != 2:
        raise RecordError("源认证必须保存两个独立新进程的原始记录")
    result = [output_path(Path(path) if Path(path).is_absolute() else source_dir / path) for path in paths]
    if result[0] == result[1] or result[0].samefile(result[1]):
        raise RecordError("源认证的两次记录指向同一实体文件")
    return result


def _assert_cross_version(old_record: Any, new_record: Any) -> None:
    """源码指纹独立验证；任务参数和所有原始帧继续逐类型、形状及字节比较。"""
    assert_identical(old_record.episode_spec, new_record.episode_spec, path="跨版本 episode_spec")
    assert_identical(old_record.frames, new_record.frames, path="跨版本 frames")


def _recovery_identity(job: dict, spec: EpisodeSpec) -> dict:
    """完成、中断和失败凭证均绑定同一不可替换的恢复身份。"""
    return {"schema_version": 2, "seed": spec.seed, "spec_hash": spec.spec_hash,
            "source_suite_hash": job["source_suite_hash"], "runtime_fingerprint": job["fingerprint"]}


def _check_receipt(path: Path, identity: dict) -> dict:
    value = _read_json(path)
    assert_identical(identity, {key: value.get(key) for key in identity}, path=f"恢复凭证/{path.name}")
    return value


def _completion_receipt(job: dict, spec: EpisodeSpec, path: Path, record: Any) -> None:
    """确认完成后留下凭证，后续丢文件或坏文件头不能冒充正常中断。"""
    receipt = path.parent / "completed.json"
    expected = {**_recovery_identity(job, spec), "content_hash": record.content_hash}
    if receipt.exists():
        assert_identical(expected, _read_json(receipt), path="完整记录凭证")
    else:
        _exclusive_json(receipt, expected)


def _check_failure_latch(job: dict, spec: EpisodeSpec) -> None:
    path = Path(job["directory"]) / "failure_latched.json"
    if path.exists():
        failure = _check_receipt(path, _recovery_identity(job, spec))
        raise ReproducibilityError(f"该冻结场景已有锁存失败，禁止重新执行：{failure['error_type']}：{failure['error']}")


def _latch_failure(job: dict, spec: EpisodeSpec, error: BaseException) -> None:
    """明确失败立即锁存且绝不覆盖，恢复不能把任务失败误判为进程中断。"""
    path = Path(job["directory"]) / "failure_latched.json"
    identity = _recovery_identity(job, spec)
    if path.exists():
        _check_receipt(path, identity)
    else:
        _exclusive_json(path, {**identity, "error_type": type(error).__name__, "error": str(error)})


def _repeat_record(job: dict, spec: EpisodeSpec, repeat: int, old_record: Any) -> tuple[Path, Any]:
    """完整结果可恢复；有身份的未完成 attempt 原样保留并按同 spec 重试。"""
    directory = Path(job["directory"]) / f"repeat_{repeat}"
    _bind_context(directory / "context.json", {
        "schema_version": 2, "episode_spec": spec.to_dict(),
        "runtime_fingerprint": job["fingerprint"], "repeat": repeat,
        "source_suite_hash": job["source_suite_hash"],
    })
    allowed = {"context.json"}
    attempts = sorted(directory.glob("attempt_*"))
    for attempt in attempts:
        suffix = attempt.name.removeprefix("attempt_")
        if attempt.is_symlink() or not attempt.is_dir() or not suffix.isdecimal():
            raise RecordError(f"重新认证缓存包含未知路径，已保留：{attempt}")
        allowed.add(attempt.name)
    unknown = {path.name for path in directory.iterdir()} - allowed
    if unknown:
        raise RecordError(f"重新认证缓存包含未知文件，已保留：{sorted(unknown)}")
    published_paths = set()
    published_report = Path(job["directory"]) / "certification.json"
    if published_report.exists():
        published_paths = {Path(path) for path in _read_json(published_report)["record_paths"]}
        if any(not path.is_file() for path in published_paths if path.is_relative_to(directory)):
            raise RecordError("已认证完整记录缺失，不能按中断重试")
    completed = []
    for attempt in attempts:
        if any(path.is_symlink() or not path.is_file() for path in attempt.iterdir()):
            raise RecordError(f"重新认证 attempt 包含非实体文件，已保留：{attempt}")
        identity = _read_json(attempt / "identity.json")
        assert_identical({"seed": spec.seed, "spec_hash": spec.spec_hash}, identity, path="重试身份")
        if {path.name for path in attempt.iterdir()} - {
                "identity.json", "episode.h5", "infrastructure_error.json", "interrupted.json", "completed.json"}:
            raise RecordError(f"重新认证 attempt 包含未知文件，已保留：{attempt}")
        record_path = attempt / "episode.h5"
        failure_path = attempt / "infrastructure_error.json"
        completion_path = attempt / "completed.json"
        interrupted_path = attempt / "interrupted.json"
        if completion_path.exists():
            _check_receipt(completion_path, _recovery_identity(job, spec))
        if interrupted_path.exists():
            _check_receipt(interrupted_path, _recovery_identity(job, spec))
        if failure_path.exists():
            failure = _read_json(failure_path)
            assert_identical(identity, {key: failure.get(key) for key in identity}, path="基础设施失败身份")
        complete, interrupted_reason = False, "missing_record"
        if record_path.exists():
            import h5py
            try:
                with h5py.File(record_path, "r") as handle:
                    complete = bool(handle.attrs.get("complete", False))
                interrupted_reason = "incomplete_record"
            except OSError:
                interrupted_reason = "unreadable_record"
        if complete or completion_path.exists() or record_path in published_paths:
            # 完成凭证或 complete 标记均是硬约束，文件丢失、坏头或摘要坏都不能跳过。
            completed.append((record_path, read_episode(record_path)))
        elif not failure_path.exists() and not interrupted_path.exists():
            _exclusive_json(interrupted_path, {**_recovery_identity(job, spec), "reason": interrupted_reason})
    for path, record in completed:
        _validate_record(record, spec, fingerprint=job["fingerprint"], path=path)
        _assert_cross_version(old_record, record)
        _completion_receipt(job, spec, path, record)
    if completed:
        for _, other in completed[1:]:
            assert_records_identical(completed[0][1], other)
        return completed[0]

    next_index = [max((int(path.name.removeprefix("attempt_")) for path in attempts), default=-1) + 1]

    def run(candidate: EpisodeSpec):
        attempt = directory / f"attempt_{next_index[0]:04d}"
        next_index[0] += 1
        attempt.mkdir()
        identity = {"seed": candidate.seed, "spec_hash": candidate.spec_hash}
        _exclusive_json(attempt / "identity.json", identity)
        record_path = attempt / "episode.h5"
        try:
            with job["gpu_limit"]:
                if job["stop"].is_set():
                    raise RecordError("其他冻结场景已失败，停止后续物理进程")
                result = run_fresh_process(candidate, record_path, render_gpu=job["render_gpu"],
                                           timeout_seconds=job["timeout_seconds"])
        except (OSError, TimeoutError, InterruptedError) as exc:
            if isinstance(exc, FileExistsError):
                raise
            _exclusive_json(attempt / "infrastructure_error.json", {
                **identity, "error_type": type(exc).__name__, "error": str(exc),
            })
            raise
        if Path(result).resolve() != record_path.resolve():
            raise RecordError("执行器返回非预期认证路径")
        record = read_episode(record_path)
        _validate_record(record, candidate, fingerprint=job["fingerprint"], path=record_path)
        _assert_cross_version(old_record, record)
        _completion_receipt(job, candidate, record_path, record)
        return record_path, record

    return retry_same_spec(spec, run)


def _recertify_job(job: dict) -> tuple[dict, dict]:
    """旧记录核对、几何核对、两次新物理执行构成一个不可替换的认证单元。"""
    spec, context_bound = None, False
    try:
        if job["stop"].is_set():
            raise RecordError("其他冻结场景已失败，停止重新认证")
        spec = EpisodeSpec.from_dict(job["episode_spec"])
        old = job["old_certification"]
        directory = Path(job["directory"])
        _bind_context(directory / "context.json", {
            "schema_version": 2, "episode_spec": spec.to_dict(),
            "source_suite_hash": job["source_suite_hash"], "old_certification": old,
            "runtime_fingerprint": job["fingerprint"],
        })
        context_bound = True
        _check_failure_latch(job, spec)
        assert_identical(job["fingerprint"], runtime_fingerprint(render_gpu=job["render_gpu"]), path="runtime_fingerprint")
        paths = _source_record_paths(old, Path(job["source_dir"]))
        records = [read_episode(path) for path in paths]
        for path, record in zip(paths, records):
            _validate_record(record, spec, fingerprint=old["runtime_fingerprint"],
                             content_hash=old["content_hash"], path=path)
            if len(record.frames) != old["frame_count"]:
                raise RecordError("源认证 frame_count 与原始记录不符")
        assert_records_identical(records[0], records[1])
        geometry = validate_spec_geometry(spec)
        if geometry.get("ok") is not True:
            raise ReproducibilityError(f"冻结场景在当前几何检查中失败，禁止换候选：{geometry}")
        unknown = {path.name for path in directory.iterdir()} - {
            "context.json", "repeat_0", "repeat_1", "certification.json", "failure_latched.json"}
        if unknown:
            raise RecordError(f"认证目录包含未知文件，已保留：{sorted(unknown)}")
        results = []
        for repeat in range(2):
            try:
                results.append(_repeat_record(job, spec, repeat, records[repeat]))
            except (CandidateRejected, SceneRejected) as exc:
                raise ReproducibilityError(
                    f"既有冻结场景运行失败，禁止修改 seed 或更换候选：{type(exc).__name__}：{exc}"
                ) from exc
        assert_records_identical(results[0][1], results[1][1])
        report = {
            "passed": True, "repeat_equal": True, "fresh_process": True,
            "comparison": "dtype_shape_bytes_all_frames_including_rgb",
            "source_frames_equal": True, "source_suite_hash": job["source_suite_hash"],
            "source_certification_commit": old["source_commit"],
            "source_record_paths": [str(path) for path in paths],
            "source_content_hash": old["content_hash"],
            "candidate_index": old["candidate_index"], "render_gpu": job["render_gpu"],
            "record_paths": [str(path) for path, _ in results],
            "content_hash": results[0][1].content_hash, "frame_count": len(results[0][1].frames),
            "geometry": geometry, "runtime_fingerprint": job["fingerprint"],
            "source_commit": job["source_commit"],
        }
        report_path = directory / "certification.json"
        if report_path.exists():
            previous = _read_json(report_path)
            # 文档提交可以改变 HEAD，已经完成的认证保留当时提交作为来源。
            report["source_commit"] = previous["source_commit"]
            assert_identical(previous, report, path="已完成认证")
        else:
            _exclusive_json(report_path, report)
        print(f"已重新认证 {spec.task_kind} seed={spec.seed} GPU={job['render_gpu']}：两次新进程与旧帧逐位相同", flush=True)
        return spec.to_dict(), report
    except BaseException as exc:
        explicit_failure = isinstance(exc, (CandidateRejected, SceneRejected, SharedReproducibilityError))
        invalid_record = isinstance(exc, RecordError) and not job["stop"].is_set()
        if context_bound and (explicit_failure or invalid_record):
            _latch_failure(job, spec, exc)
        job["stop"].set()
        raise


def recertify_suite(source_suite, output_suite_dir, *, workers=32, timeout_seconds=1200,
                    tasks=None, episodes_per_task=None) -> Path:
    """只消费源冻结清单；全部旧、新记录严格一致后才发布新认证清单。"""
    if type(workers) is not int or workers < 1 or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("workers 必须为正整数，timeout_seconds 必须大于零")
    source = Path(source_suite)
    source = output_path(source if source.suffix == ".json" else source / "suite.json")
    output = output_path(output_suite_dir)
    if output.is_relative_to(source.parent) or source.is_relative_to(output):
        raise ValueError("新认证输出必须与源清单目录隔离，禁止写入或包围原数据")
    suite = load_suite(source)
    specs = _select_specs(suite, tasks, episodes_per_task)
    configure_runtime()
    fingerprint = runtime_fingerprint()
    gpu_fingerprints = {}
    for spec in specs:
        old = suite["certification"][spec.spec_hash]
        if old.get("fresh_process") is not True or not old.get("content_hash") or not old.get("source_commit"):
            raise RecordError("源认证缺少新进程、内容摘要或提交证据")
        gpu = _render_gpu_from_fingerprint(old.get("runtime_fingerprint", {}))
        if old.get("render_gpu") != gpu:
            raise RecordError("源认证 GPU 与指纹绑定不符")
        if gpu not in gpu_fingerprints:
            gpu_fingerprints[gpu] = runtime_fingerprint(render_gpu=gpu)
        _compatible_fingerprint(old["runtime_fingerprint"], gpu_fingerprints[gpu])
    _bind_context(output / "recertify_state.json", {
        "schema_version": 2, "source_suite": str(source), "source_suite_hash": suite["suite_hash"],
        "episodes": [spec.to_dict() for spec in specs], "runtime_fingerprint": fingerprint,
        "gpu_fingerprints": {str(gpu): value for gpu, value in gpu_fingerprints.items()},
    })
    unknown = {path.name for path in output.iterdir()} - {"recertify_state.json", "certification", "suite.json"}
    if unknown:
        raise RecordError(f"重新认证输出包含未知产物，已保留：{sorted(unknown)}")
    certificate_root = output / "certification"
    if certificate_root.exists():
        expected_tasks = {spec.task_kind for spec in specs}
        for task_dir in certificate_root.iterdir():
            if task_dir.name not in expected_tasks or not task_dir.is_dir():
                raise RecordError(f"认证缓存包含未知任务路径，已保留：{task_dir}")
            expected_seeds = {f"seed_{spec.seed}" for spec in specs if spec.task_kind == task_dir.name}
            for seed_dir in task_dir.iterdir():
                if seed_dir.name not in expected_seeds or not seed_dir.is_dir():
                    raise RecordError(f"认证缓存包含未知 seed 路径，已保留：{seed_dir}")
    manifest = output / "suite.json"
    if manifest.exists():
        published = load_suite(manifest)
        assert_identical(suite["configs"], published["configs"], path="恢复配置")
        assert_identical([spec.to_dict() for spec in specs], published["episodes"], path="恢复规格")
    commit = source_commit()
    with _new_manager() as manager:
        stop = manager.Event()
        limits = _gpu_limits(manager, sorted(gpu_fingerprints), workers)
        jobs = []
        for spec in specs:
            old = suite["certification"][spec.spec_hash]
            gpu = old["render_gpu"]
            jobs.append({
                "episode_spec": spec.to_dict(), "old_certification": old,
                "source_suite_hash": suite["suite_hash"], "source_dir": str(source.parent),
                "directory": str(output / "certification" / spec.task_kind / f"seed_{spec.seed}"),
                "fingerprint": gpu_fingerprints[gpu], "render_gpu": gpu, "gpu_limit": limits[gpu],
                "stop": stop, "timeout_seconds": timeout_seconds, "source_commit": commit,
            })
        results = _run_process_jobs(_recertify_job, jobs, workers, stop)
    assert_identical(fingerprint, runtime_fingerprint(), path="runtime_fingerprint")
    assert_identical(suite, load_suite(source), path="源清单运行期间保持不变")
    certification = {row["spec_hash"]: report for row, report in results}
    if manifest.exists():
        published = load_suite(manifest)
        assert_identical(suite["configs"], published["configs"], path="恢复配置")
        assert_identical([spec.to_dict() for spec in specs], published["episodes"], path="恢复规格")
        assert_identical(certification, published["certification"], path="恢复认证")
        return manifest
    return save_suite(manifest, specs, (suite["configs"]["task"], suite["configs"]["position"]), certification)
