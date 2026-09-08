"""冻结套件的认证、生成与回放；失败重试不改变规格和 seed。"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing as mp
import os
from pathlib import Path
import time
import traceback
from typing import Any, Callable, Mapping, Sequence

import h5py

from .hdf5 import (
    EpisodeRecord,
    RecordError,
    ReproducibilityError,
    assert_identical,
    assert_records_identical,
    read_episode,
    write_episode,
)
from .paths import output_path
from .fingerprint import runtime_fingerprint, source_commit


class CandidateRejected(RuntimeError):
    """确定性场景或任务失败，可以尝试同一配额槽的下一候选。"""


class InfrastructureError(OSError):
    """进程或设备暂时不可用，只能重试完全相同的规格。"""


def _spec_class():
    # 纯 HDF5 工具无需导入仿真环境，套件类型也在实际消费时才加载。
    from ..suite import EpisodeSpec
    return EpisodeSpec


def _check_terminal(frames: Sequence[Mapping[str, Any]]) -> None:
    if not frames:
        raise CandidateRejected("rollout 没有产生帧")
    info = frames[-1].get("info", {})
    if info.get("success") is not True or info.get("fail") is not False:
        raise CandidateRejected("rollout 终态必须严格为 success=True 且 fail=False")


def _replay_frames(env: Any, expected: EpisodeRecord) -> list[dict[str, Any]]:
    """重放动作前先重建并严格核对 reset 内部的演示。"""
    from ..oracle import frame_record

    observation, info = env.reset()
    frames = list(info.get("demonstration", []))
    frames.append(frame_record(observation, None, info))
    if len(frames) > len(expected.frames):
        raise ReproducibilityError("reset 产生的帧数超过已认证记录")
    assert_identical(expected.frames[:len(frames)], frames, path="reset")
    for index in range(len(frames), len(expected.frames)):
        action = expected.frames[index].get("joint_action")
        if action is None:
            raise RecordError(f"非 reset 帧缺少 joint_action：{index}")
        observation, _, terminated, truncated, info = env.step(action)
        frame = frame_record(observation, action, info)
        assert_identical(expected.frames[index], frame, path=f"frames/{index}")
        frames.append(frame)
        if (bool(terminated) or bool(truncated)) and index != len(expected.frames) - 1:
            raise ReproducibilityError(f"回放在第 {index} 帧提前结束")
    _check_terminal(frames)
    return frames


def _child_run(connection: Any, spec_data: dict[str, Any], target: str, replay_source: str | None, render_gpu: int) -> None:
    """每次调用运行在一个全新的 spawn 进程中，管道只传小型状态。"""
    env = None
    started = time.monotonic()
    try:
        from ..api import make_env_from_spec
        from ..oracle import run_episode

        fingerprint = runtime_fingerprint(render_gpu=render_gpu)
        commit = source_commit()
        spec = _spec_class().from_dict(spec_data)
        env = make_env_from_spec(spec, record_demonstration=True, render_gpu=render_gpu)
        built = time.monotonic()
        if replay_source is None:
            frames = run_episode(env)
        else:
            frames = _replay_frames(env, read_episode(replay_source))
        _check_terminal(frames)
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


def run_fresh_process(
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


def _exclusive_json(path: Path, payload: Any) -> None:
    target = output_path(path, create_parent=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise RecordError(f"恢复记录损坏，已保留原文件：{path}：{exc}") from exc


def _bind_context(path: Path, expected: dict[str, Any]) -> None:
    """首次运行固定恢复身份；代码、配置或配额变化必须另用新目录。"""
    path = output_path(path, create_parent=True)
    if path.exists():
        assert_identical(expected, _read_json(path), path=f"恢复上下文/{path.name}")
    else:
        if any(path.parent.iterdir()):
            raise RecordError(f"已有产物缺少恢复上下文，无法证明配置和运行指纹相同：{path.parent}")
        _exclusive_json(path, expected)


def _complete_record(path: Path) -> EpisodeRecord | None:
    """只跳过明确未完成的 staging；有完成标记但摘要坏了必须停止。"""
    path = output_path(path)
    try:
        with h5py.File(path, "r") as handle:
            complete = bool(handle.attrs.get("complete", False))
    except OSError:
        # 写到一半的 HDF5 可能还没有有效文件头，保留它并换明确的新 attempt 文件。
        return None
    return read_episode(path) if complete else None


def _validate_record(
    record: EpisodeRecord,
    spec: Any,
    *,
    fingerprint: dict[str, Any] | None = None,
    content_hash: str | None = None,
    path: str | Path = "record",
) -> None:
    if record.spec_hash != spec.spec_hash:
        raise RecordError(f"已有记录规格不符，拒绝覆盖：{path}")
    assert_identical(spec.to_dict(), record.episode_spec, path="episode_spec")
    if fingerprint is not None:
        assert_identical(fingerprint, record.runtime_fingerprint, path="runtime_fingerprint")
    try:
        _check_terminal(record.frames)
    except CandidateRejected as exc:
        raise RecordError(f"完整缓存记录的终态非法，已保留原文件：{path}") from exc
    if content_hash is not None and record.content_hash != content_hash:
        raise ReproducibilityError(f"正式生成与认证内容不同，记录已保留：{path}")


def _prior_complete(
    paths: Sequence[Path], spec: Any, *, fingerprint: dict[str, Any] | None,
    content_hash: str | None = None,
) -> tuple[Path, EpisodeRecord] | None:
    """未知退出状态下，完整产物可复用；多个完整产物也必须相互一致。"""
    result = None
    for path in sorted(paths):
        record = _complete_record(path)
        if record is None:
            continue
        _validate_record(record, spec, fingerprint=fingerprint, content_hash=content_hash, path=path)
        if result is None:
            result = (path, record)
        else:
            assert_records_identical(result[1], record)
    return result


def _atomic_publish(staging: Path, target: Path) -> None:
    """同仓库内已关闭的完整文件原子发布，绝不替换已存在的最终路径。"""
    staging, target = output_path(staging), output_path(target, create_parent=True)
    with staging.open("rb") as stream:
        os.fsync(stream.fileno())
    # 同一目标旁的 staging 与目标处于同一文件系统；硬链接创建是原子的且不覆盖。
    # staging 保留作为执行证据，两个名字都实际存储在本仓库内。
    os.link(staging, target)
    descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _run_staged(
    spec: Any, target: Path, operation: Callable[[Any, Path], Path], *,
    fingerprint: dict[str, Any] | None, content_hash: str | None,
) -> tuple[EpisodeRecord, bool]:
    """基础设施失败留下独立 staging，再以完全相同 spec/seed 重试。"""
    target = output_path(target, create_parent=True)
    if target.exists():
        record = read_episode(target)
        _validate_record(record, spec, fingerprint=fingerprint, content_hash=content_hash, path=target)
        return record, True
    directory = target.parent / ".staging" / target.name
    _bind_context(directory / "context.json", {
        "schema_version": 1, "episode_spec": spec.to_dict(),
        "runtime_fingerprint": fingerprint, "expected_content_hash": content_hash,
    })
    # 重试计数不只取已存在文件：失败尚未来得及创建文件时也使用新的明确 attempt 名称。
    indices = [int(path.stem.split("_")[-1]) for path in directory.glob("attempt_*.h5")]
    next_index = [max(indices, default=-1) + 1]
    reused = [False]

    def attempt(candidate: Any) -> EpisodeRecord:
        if target.exists():
            record = read_episode(target)
            _validate_record(record, candidate, fingerprint=fingerprint, content_hash=content_hash, path=target)
            reused[0] = True
            return record
        previous = _prior_complete(list(directory.glob("attempt_*.h5")), candidate,
                                   fingerprint=fingerprint, content_hash=content_hash)
        if previous is not None:
            staging, record = previous
            reused[0] = True
        else:
            staging = directory / f"attempt_{next_index[0]:04d}.h5"
            next_index[0] += 1
            result = operation(candidate, staging)
            if Path(result).resolve() != staging.resolve():
                raise RecordError("执行器返回了非预期 staging 路径")
            record = read_episode(staging)
            _validate_record(record, candidate, fingerprint=fingerprint, content_hash=content_hash, path=staging)
        _atomic_publish(staging, target)
        return record

    return retry_same_spec(spec, attempt), reused[0]


def _new_manager():
    return mp.get_context("spawn").Manager()


def _gpu_limits(manager: Any, gpus: Sequence[int], workers: int) -> dict[int, Any]:
    """限制每卡真实渲染并发；少 worker 时仍能顺序使用全部指定卡。"""
    return {gpu: manager.BoundedSemaphore(max(1, workers // len(gpus) + (index < workers % len(gpus))))
            for index, gpu in enumerate(sorted(gpus))}


def _run_process_jobs(operation: Callable, jobs: Sequence[dict], workers: int, stop: Any) -> list[Any]:
    """主进程只接小摘要；几何、HDF5 解码和严格核对均在各 slot 进程。"""
    results = [None] * len(jobs)
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"), max_tasks_per_child=1) as executor:
        futures = {executor.submit(operation, job): index for index, job in enumerate(jobs)}
        try:
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        except BaseException:
            stop.set()
            for future in futures:
                future.cancel()
            raise
    return results


def _certify_slot_job(job: dict) -> tuple[dict, dict]:
    """一个全新 slot 进程负责编译、候选搜索及两次独立物理进程认证。"""
    from ..geometry import validate_spec_geometry
    from ..suite import candidate_for_slot

    slot, output, stop = job["slot"], Path(job["output"]), job["stop"]
    fingerprint, render_gpu = job["fingerprint"], job["render_gpu"]
    assert_identical(fingerprint, runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
    limit = min(int(slot.get("max_candidates", 1024)), job["max_candidates"] or 1024)
    for candidate_index in range(limit):
        if stop.is_set():
            raise RecordError("其他配额槽已出现阻断错误，停止认证")
        spec = candidate_for_slot(slot, candidate_index)
        candidate_dir = output / "certification" / str(slot["slot_id"]) / f"candidate_{candidate_index:04d}"
        try:
            rejection_path = candidate_dir / "rejected.json"
            if rejection_path.exists():
                rejection = _read_json(rejection_path)
                expected_identity = {"seed": spec.seed, "spec_hash": spec.spec_hash,
                                     "candidate_index": candidate_index, "runtime_fingerprint": fingerprint}
                assert_identical(expected_identity,
                                 {key: rejection.get(key) for key in expected_identity}, path="已拒绝候选身份")
                print(f"复用已拒绝候选：{slot['slot_id']} candidate={candidate_index}", flush=True)
                continue
            geometry_report = validate_spec_geometry(spec)
            if not geometry_report["ok"]:
                raise CandidateRejected("；".join(geometry_report["reasons"]))
            paths = []
            for repeat in range(2):
                if stop.is_set():
                    raise RecordError("其他配额槽已出现阻断错误，停止认证")
                prefix = f"repeat_{repeat}_infra_"
                indices = [int(path.stem.removeprefix(prefix)) for path in candidate_dir.glob(prefix + "*.h5")]
                infra_attempt = [max(indices, default=-1) + 1]

                def run(candidate: Any) -> Path:
                    previous = _prior_complete(list(candidate_dir.glob(prefix + "*.h5")), candidate, fingerprint=fingerprint)
                    if previous is not None:
                        print(f"复用完整认证记录：{previous[0]}", flush=True)
                        return previous[0]
                    path = candidate_dir / f"repeat_{repeat}_infra_{infra_attempt[0]}.h5"
                    infra_attempt[0] += 1
                    with job["gpu_limit"]:
                        if stop.is_set():
                            raise RecordError("其他配额槽已失败，停止启动后续物理进程")
                        return run_fresh_process(candidate, path, timeout_seconds=job["timeout_seconds"], render_gpu=render_gpu)

                try:
                    paths.append(retry_same_spec(spec, run))
                except Exception as exc:
                    from ..errors import SceneRejected, TaskExecutionError
                    if repeat > 0 and isinstance(exc, (SceneRejected, TaskExecutionError, CandidateRejected)):
                        raise ReproducibilityError("同一规格首次运行成功，重复运行失败，禁止换候选") from exc
                    raise
            verify_started = time.monotonic()
            left, right = (read_episode(path) for path in paths)
            assert_records_identical(left, right)
            assert_identical(fingerprint, left.runtime_fingerprint, path="runtime_fingerprint")
            print(f"ICL_VERIFY seed={spec.seed} GPU={render_gpu} seconds={time.monotonic()-verify_started:.6f}", flush=True)
            certification = {
                "passed": True, "repeat_equal": True, "fresh_process": True,
                "comparison": "dtype_shape_bytes_all_frames_including_rgb",
                "candidate_index": candidate_index, "render_gpu": render_gpu,
                "record_paths": [str(path) for path in paths], "content_hash": left.content_hash,
                "frame_count": len(left.frames), "geometry": geometry_report,
                "runtime_fingerprint": fingerprint, "source_commit": job["source_commit"],
            }
            print(f"已认证 {slot['slot_id']}：seed={spec.seed} GPU={render_gpu}，帧数={len(left.frames)}", flush=True)
            return spec.to_dict(), certification
        except Exception as exc:
            from ..errors import SceneRejected, TaskExecutionError
            if not isinstance(exc, (SceneRejected, TaskExecutionError, CandidateRejected)):
                stop.set()
                raise
            _exclusive_json(candidate_dir / "rejected.json", {
                "seed": spec.seed, "spec_hash": spec.spec_hash,
                "candidate_index": candidate_index, "runtime_fingerprint": fingerprint, "error": str(exc),
            })
            print(f"候选不满足任务要求：{slot['slot_id']} candidate={candidate_index}：{exc}", flush=True)
    stop.set()
    raise CandidateRejected(f"配额槽 {slot['slot_id']} 用尽 {limit} 个候选，未发布不完整套件")


def prepare_suite(
    output_dir: str | Path,
    *,
    task_config: str | Path | None = None,
    position_config: str | Path | None = None,
    tasks: Sequence[str] | None = None,
    episodes_per_task: int | None = None,
    workers: int = 32,
    max_candidates: int | None = None,
    timeout_seconds: float = 240,
    gpus: Sequence[int] = (0, 1),
) -> Path:
    """固定 seed 到物理 GPU 的映射，再并行认证；全部通过后才发布。"""
    from ..suite import EpisodeSpec, load_configs, plan_slots, save_suite

    if workers < 1 or (max_candidates is not None and max_candidates < 1):
        raise ValueError("workers 和 max_candidates 必须大于零")
    if not gpus or any(type(gpu) is not int or gpu < 0 for gpu in gpus) or len(set(gpus)) != len(gpus):
        raise ValueError("gpus 必须包含不重复的非负物理 GPU 编号")
    gpus = sorted(gpus)
    output = output_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "suite.json"
    if manifest.exists():
        raise FileExistsError(f"认证套件已存在，拒绝覆盖：{manifest}")
    configs = load_configs(task_config, position_config)
    slots = plan_slots(*configs, tasks=tasks, episodes_per_task=episodes_per_task)
    from ..runtime import configure_runtime
    configure_runtime()
    fingerprint = runtime_fingerprint()
    gpu_fingerprints = {gpu: runtime_fingerprint(render_gpu=gpu) for gpu in gpus}
    commit = source_commit()
    _bind_context(output / "prepare_state.json", {
        "schema_version": 1, "configs": {"task": configs[0], "position": configs[1]},
        "slots": slots, "runtime_fingerprint": fingerprint, "gpus": gpus,
    })
    with _new_manager() as manager:
        stop = manager.Event()
        gpu_limits = _gpu_limits(manager, gpus, workers)
        jobs = [{"slot": slot, "output": str(output), "stop": stop,
                 "render_gpu": gpus[int(slot["seed"]) % len(gpus)],
                 "gpu_limit": gpu_limits[gpus[int(slot["seed"]) % len(gpus)]],
                 "fingerprint": gpu_fingerprints[gpus[int(slot["seed"]) % len(gpus)]],
                 "max_candidates": max_candidates, "timeout_seconds": timeout_seconds,
                 "source_commit": commit} for slot in slots]
        results = _run_process_jobs(_certify_slot_job, jobs, workers, stop)
    specs = [EpisodeSpec.from_dict(item[0]) for item in results]
    certification = {spec.spec_hash: result[1] for spec, result in zip(specs, results)}
    assert_identical(fingerprint, runtime_fingerprint(), path="runtime_fingerprint")
    save_suite(manifest, specs, configs, certification)
    return manifest


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
    operation = runner or (lambda candidate, destination: run_fresh_process(candidate, destination, timeout_seconds=timeout_seconds, render_gpu=render_gpu))
    record, resumed = _run_staged(spec, target, operation, fingerprint=expected_runtime_fingerprint,
                                 content_hash=expected_content_hash)
    return {"seed": spec.seed, "spec_hash": spec.spec_hash, "path": str(target), "resumed": resumed, "content_hash": record.content_hash}


def _render_gpu_from_fingerprint(fingerprint: dict[str, Any]) -> int:
    gpu = fingerprint.get("render_gpu")
    if type(gpu) is not int or gpu < 0:
        raise RecordError("认证记录缺少有效物理 GPU 绑定，禁止换卡重建")
    return gpu


def _generate_spec_job(job: dict) -> dict[str, Any]:
    """记录的读取、恢复和逐字节核对在独立进程内完成。"""
    stop = job["stop"]
    if stop.is_set():
        raise RecordError("其他生成任务已失败，停止后续生成")
    try:
        spec = _spec_class().from_dict(job["episode_spec"])
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
                return run_fresh_process(candidate, destination, timeout_seconds=job["timeout_seconds"], render_gpu=render_gpu)

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
    from ..suite import load_suite

    if workers < 1:
        raise ValueError("workers 必须大于零")
    suite = load_suite(suite_path)
    from ..runtime import configure_runtime
    configure_runtime()
    fingerprint = runtime_fingerprint()
    specs = [_spec_class().from_dict(value) for value in suite["episodes"]]
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

    with _new_manager() as manager:
        stop = manager.Event()
        gpus = sorted({_render_gpu_from_fingerprint(suite["certification"][spec.spec_hash]["runtime_fingerprint"]) for spec in specs})
        gpu_limits = _gpu_limits(manager, gpus, workers)
        jobs = [{"episode_spec": spec.to_dict(), "certification": suite["certification"][spec.spec_hash],
                 "gpu_limit": gpu_limits[_render_gpu_from_fingerprint(suite["certification"][spec.spec_hash]["runtime_fingerprint"])],
                 "output": str(output), "timeout_seconds": timeout_seconds, "stop": stop} for spec in specs]
        results = _run_process_jobs(_generate_spec_job, jobs, workers, stop)
    assert_identical(fingerprint, runtime_fingerprint(), path="runtime_fingerprint")
    return results


def replay_episode(path: str | Path, output_file: str | Path, *, timeout_seconds: float = 240) -> dict[str, Any]:
    """只依赖当前 HDF5 的规格和动作，完全不读取原版 metadata。"""
    expected = read_episode(path)
    from ..runtime import configure_runtime
    configure_runtime()
    if expected.runtime_fingerprint is None:
        raise RecordError("输入记录没有运行指纹，禁止进行认证回放")
    render_gpu = _render_gpu_from_fingerprint(expected.runtime_fingerprint)
    assert_identical(expected.runtime_fingerprint, runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
    spec = _spec_class().from_dict(expected.episode_spec)
    target = output_path(output_file)
    actual, resumed = _run_staged(
        spec, target,
        lambda candidate, staging: run_fresh_process(candidate, staging, replay_source=path, timeout_seconds=timeout_seconds, render_gpu=render_gpu),
        fingerprint=expected.runtime_fingerprint, content_hash=expected.content_hash,
    )
    assert_records_identical(expected, actual)
    return {"passed": True, "seed": spec.seed, "spec_hash": spec.spec_hash,
            "frame_count": len(actual.frames), "path": str(target), "resumed": resumed, "render_gpu": render_gpu}
