"""固定配额内认证候选，全部通过才发布版本2套件。"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Sequence


from ..errors import CandidateRejected
from ..specs import EpisodeSpec
from ..io.paths import output_path
from ..io.fingerprint import runtime_fingerprint, source_commit
from ..io.hdf5 import (
    RecordError,
    ReproducibilityError,
    assert_identical,
    assert_records_identical,
    read_episode,
)

from ..io.state import _read_json, _exclusive_json, _bind_context, _prior_complete
from .workers import (
    run_episode_process,
    retry_same_spec,
    new_manager,
    gpu_limits,
    run_jobs,
)


def _certify_slot_job(job: dict) -> tuple[dict, dict]:
    """CPU/I/O worker 处理一个槽位；两次真实物理运行仍各自独立新进程。"""
    from ..sampling.compiler import candidate_for_slot

    slot, output, stop = job["slot"], Path(job["output"]), job["stop"]
    fingerprint, render_gpu = job["fingerprint"], job["render_gpu"]
    assert_identical(
        fingerprint,
        runtime_fingerprint(render_gpu=render_gpu),
        path="runtime_fingerprint",
    )
    limit = min(int(slot.get("max_candidates", 1024)), job["max_candidates"] or 1024)
    for candidate_index in range(limit):
        if stop.is_set():
            raise RecordError("其他配额槽已出现阻断错误，停止认证")
        spec = candidate_for_slot(slot, candidate_index)
        candidate_dir = (
            output
            / "certification"
            / str(slot["slot_id"])
            / f"candidate_{candidate_index:04d}"
        )
        try:
            rejection_path = candidate_dir / "rejected.json"
            if rejection_path.exists():
                rejection = _read_json(rejection_path)
                expected_identity = {
                    "seed": spec.seed,
                    "spec_hash": spec.spec_hash,
                    "candidate_index": candidate_index,
                    "runtime_fingerprint": fingerprint,
                }
                assert_identical(
                    expected_identity,
                    {key: rejection.get(key) for key in expected_identity},
                    path="已拒绝候选身份",
                )
                print(
                    f"复用已拒绝候选：{slot['slot_id']} candidate={candidate_index}",
                    flush=True,
                )
                continue
            geometry_report = {
                "scope": "initial_layout",
                "source": "native_collision_shapes",
            }
            paths = []
            for repeat in range(2):
                if stop.is_set():
                    raise RecordError("其他配额槽已出现阻断错误，停止认证")
                prefix = f"repeat_{repeat}_infra_"
                indices = [
                    int(path.stem.removeprefix(prefix))
                    for path in candidate_dir.glob(prefix + "*.h5")
                ]
                infra_attempt = [max(indices, default=-1) + 1]

                def run(candidate: Any) -> Path:
                    previous = _prior_complete(
                        list(candidate_dir.glob(prefix + "*.h5")),
                        candidate,
                        fingerprint=fingerprint,
                    )
                    if previous is not None:
                        print(f"复用完整认证记录：{previous[0]}", flush=True)
                        return previous[0]
                    path = (
                        candidate_dir / f"repeat_{repeat}_infra_{infra_attempt[0]}.h5"
                    )
                    infra_attempt[0] += 1
                    with job["gpu_limit"]:
                        if stop.is_set():
                            raise RecordError("其他配额槽已失败，停止启动后续物理进程")
                        return run_episode_process(
                            candidate,
                            path,
                            timeout_seconds=job["timeout_seconds"],
                            render_gpu=render_gpu,
                        )

                try:
                    paths.append(retry_same_spec(spec, run))
                except Exception as exc:
                    from ..errors import SceneRejected, TaskExecutionError

                    if repeat > 0 and isinstance(
                        exc, (SceneRejected, TaskExecutionError, CandidateRejected)
                    ):
                        raise ReproducibilityError(
                            "同一规格首次运行成功，重复运行失败，禁止换候选"
                        ) from exc
                    raise
            verify_started = time.monotonic()
            left, right = (read_episode(path) for path in paths)
            assert_records_identical(left, right)
            geometry_report = next(
                frame["info"]["geometry_report"]
                for frame in left.frames
                if frame["info"]["operation"] == "reset_complete"
            )
            from ..io.scene_metadata import scene_metadata
            from ..io.hdf5 import tree_hash

            initial = next(
                frame["info"]
                for frame in left.frames
                if frame["info"]["operation"] == "reset_complete"
            )
            if geometry_report.get("ok") is not True:
                raise CandidateRejected("真实原版初态几何未通过")
            assert_identical(
                fingerprint, left.runtime_fingerprint, path="runtime_fingerprint"
            )
            print(
                f"ICL_VERIFY seed={spec.seed} GPU={render_gpu} seconds={time.monotonic() - verify_started:.6f}",
                flush=True,
            )
            certification = {
                "passed": True,
                "repeat_equal": True,
                "fresh_process": True,
                "comparison": "dtype_shape_bytes_all_frames_including_rgb",
                "candidate_index": candidate_index,
                "render_gpu": render_gpu,
                "record_paths": [str(path) for path in paths],
                "content_hash": left.content_hash,
                "frame_count": len(left.frames),
                "geometry": geometry_report,
                "runtime_fingerprint": fingerprint,
                "source_commit": job["source_commit"],
                "initial_scene_hash": tree_hash(scene_metadata(initial)),
            }
            print(
                f"已认证 {slot['slot_id']}：seed={spec.seed} GPU={render_gpu}，帧数={len(left.frames)}",
                flush=True,
            )
            return spec.to_dict(), certification
        except Exception as exc:
            from ..errors import SceneRejected, TaskExecutionError

            if not isinstance(
                exc, (SceneRejected, TaskExecutionError, CandidateRejected)
            ):
                stop.set()
                raise
            _exclusive_json(
                candidate_dir / "rejected.json",
                {
                    "seed": spec.seed,
                    "spec_hash": spec.spec_hash,
                    "candidate_index": candidate_index,
                    "runtime_fingerprint": fingerprint,
                    "error": str(exc),
                },
            )
            print(
                f"候选不满足任务要求：{slot['slot_id']} candidate={candidate_index}：{exc}",
                flush=True,
            )
    stop.set()
    raise CandidateRejected(
        f"配额槽 {slot['slot_id']} 用尽 {limit} 个候选，未发布不完整套件"
    )


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
    from ..config import load_configs
    from ..sampling.tasks import plan_slots
    from ..io.suite import save_suite

    if workers < 1 or (max_candidates is not None and max_candidates < 1):
        raise ValueError("workers 和 max_candidates 必须大于零")
    if (
        not gpus
        or any(type(gpu) is not int or gpu < 0 for gpu in gpus)
        or len(set(gpus)) != len(gpus)
    ):
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
    _bind_context(
        output / "prepare_state.json",
        {
            "schema_version": 1,
            "configs": {"task": configs[0], "position": configs[1]},
            "slots": slots,
            "runtime_fingerprint": fingerprint,
            "gpus": gpus,
        },
    )
    with new_manager() as manager:
        stop = manager.Event()
        limits = gpu_limits(manager, gpus, workers)
        jobs = [
            {
                "slot": slot,
                "output": str(output),
                "stop": stop,
                "render_gpu": gpus[int(slot["seed"]) % len(gpus)],
                "gpu_limit": limits[gpus[int(slot["seed"]) % len(gpus)]],
                "fingerprint": gpu_fingerprints[gpus[int(slot["seed"]) % len(gpus)]],
                "max_candidates": max_candidates,
                "timeout_seconds": timeout_seconds,
                "source_commit": commit,
            }
            for slot in slots
        ]
        results = run_jobs(_certify_slot_job, jobs, workers, stop)
    specs = [EpisodeSpec.from_dict(item[0]) for item in results]
    certification = {spec.spec_hash: result[1] for spec, result in zip(specs, results)}
    assert_identical(fingerprint, runtime_fingerprint(), path="runtime_fingerprint")
    save_suite(manifest, specs, configs, certification)
    return manifest
