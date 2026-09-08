"""正式套件验收驱动：跨调度生成、断点、动作回放及同环境连续重置。"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import traceback
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _signed(value: dict) -> dict:
    payload = {key: item for key, item in value.items() if key != "report_hash"}
    return {**payload, "report_hash": hashlib.sha256(_json(payload).encode()).hexdigest()}


def _verify(value: Any, label: str) -> dict:
    if not isinstance(value, dict) or value.get("report_hash") != _signed(value)["report_hash"]:
        raise ValueError(f"控制报告摘要错误，保留原文件：{label}")
    return value


def _read_json(path: Path) -> dict:
    from robomme_icl.io.paths import output_path
    path = output_path(path)
    try:
        return _verify(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"控制报告损坏，保留原文件：{path}") from exc


def _create_json(path: Path, value: dict) -> None:
    """排他创建控制记录，禁止覆盖未知或损坏的既有文件。"""
    from robomme_icl.io.paths import output_path

    target = output_path(path, create_parent=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(_json(_signed(value)) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_journals(directory: Path) -> tuple[list[dict], list[dict]]:
    """完整行必须可验证；中断留下的不完整末行保留，由新分段接续。"""
    from robomme_icl.io.paths import output_path

    rows, interrupted_tails = [], []
    for path in sorted(directory.glob("results_*.jsonl")):
        path = output_path(path)
        lines = path.read_bytes().splitlines(keepends=True)
        offset = 0
        for index, raw in enumerate(lines):
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                if index == len(lines) - 1 and not raw.endswith(b"\n"):
                    interrupted_tails.append({"path": str(path), "byte_offset": offset})
                    print(f"保留未完成的 JSONL 末行：{path} offset={offset}", flush=True)
                    break
                raise ValueError(f"JSONL 完整行损坏，保留原文件：{path} 第 {index + 1} 行") from exc
            rows.append(_verify(payload, f"{path}:{index + 1}"))
            offset += len(raw)
    return rows, interrupted_tails


def _check_record(path: Path, spec: Any, certification: dict) -> Any:
    from robomme_icl.io.hdf5 import assert_identical, read_episode

    record = read_episode(path)
    assert_identical(spec.to_dict(), record.episode_spec, path="episode_spec")
    assert_identical(certification["runtime_fingerprint"], record.runtime_fingerprint, path="runtime_fingerprint")
    if record.spec_hash != spec.spec_hash or record.content_hash != certification["content_hash"]:
        raise ValueError(f"记录不符合认证基线：{path}")
    if record.frames[-1]["info"].get("success") is not True or record.frames[-1]["info"].get("fail") is not False:
        raise ValueError(f"记录终态不是严格成功：{path}")
    return record


def _paths(output: Path, spec: Any) -> tuple[Path, Path]:
    return (output / "data" / spec.task_kind / f"seed_{spec.seed}.h5",
            output / "replay" / spec.task_kind / f"seed_{spec.seed}.h5")


def _run_reset(job: dict) -> dict:
    """只回传摘要；同一个新建环境连续 reset 两次，帧留在 worker 内。"""
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.api import make_env_from_spec
    from robomme_icl.io.fingerprint import runtime_fingerprint, source_commit
    from robomme_icl.io.hdf5 import assert_identical, tree_hash
    from robomme_icl.oracle import run_episode
    from robomme_icl.suite import EpisodeSpec

    spec = EpisodeSpec.from_dict(job["episode_spec"])
    certification = job["certification"]
    render_gpu = certification["render_gpu"]
    if certification["runtime_fingerprint"].get("render_gpu") != render_gpu:
        raise ValueError("认证 GPU 绑定与指纹不同")
    assert_identical(certification["runtime_fingerprint"], runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
    baseline = _check_record(Path(certification["record_paths"][0]), spec, certification)
    env = make_env_from_spec(spec, record_demonstration=True, render_gpu=render_gpu)
    try:
        first = run_episode(env)
        second = run_episode(env)
        assert_identical(baseline.frames, first, path="first_vs_certification")
        assert_identical(baseline.frames, second, path="second_vs_certification")
        assert_identical(first, second, path="first_vs_second")
        digest = tree_hash({"episode_spec": spec.to_dict(), "frames": first,
                            "runtime_fingerprint": certification["runtime_fingerprint"]})
        if digest != certification["content_hash"]:
            raise ValueError("连续 reset 的内容摘要与认证不符")
    finally:
        env.close()
    assert_identical(certification["runtime_fingerprint"], runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
    return {"passed": True, "frame_count": len(first), "content_hash": digest,
            "first_equals_baseline": True, "second_equals_baseline": True, "repeat_equal": True,
            "source_commit": source_commit(), "render_gpu": render_gpu}


def _run_item(job: dict) -> dict:
    """生成与回放沿用正式 I/O，resume 缺文件时禁止偷偷补生成。"""
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.io.fingerprint import runtime_fingerprint
    from robomme_icl.io.hdf5 import assert_identical, assert_records_identical
    from robomme_icl.io.pipeline import generate_one, replay_episode
    from robomme_icl.suite import EpisodeSpec

    spec = EpisodeSpec.from_dict(job["episode_spec"])
    certification, mode = job["certification"], job["mode"]
    render_gpu = certification["render_gpu"]
    if certification["runtime_fingerprint"].get("render_gpu") != render_gpu:
        raise ValueError("认证 GPU 绑定与指纹不同")
    assert_identical(certification["runtime_fingerprint"], runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
    data_path, replay_path = _paths(Path(job["output"]), spec)
    if mode in {"generate", "resume"}:
        if mode == "resume" and not data_path.is_file():
            raise ValueError(f"resume 验收要求所有原记录已经存在：{data_path}")
        result = generate_one(spec, data_path, expected_content_hash=certification["content_hash"],
                              expected_runtime_fingerprint=certification["runtime_fingerprint"],
                              timeout_seconds=job["timeout_seconds"])
        if mode == "resume" and result["resumed"] is not True:
            raise ValueError("resume 验收不得实际生成新记录")
        record = _check_record(data_path, spec, certification)
    elif mode == "replay":
        data = _check_record(data_path, spec, certification)
        result = replay_episode(data_path, replay_path, timeout_seconds=job["timeout_seconds"])
        record = _check_record(replay_path, spec, certification)
        assert_records_identical(data, record)
    else:
        raise ValueError(f"不支持的模式：{mode}")
    return {**result, "passed": True, "frame_count": len(record.frames), "content_hash": record.content_hash, "render_gpu": render_gpu}


def _validate_completed(row: dict, job: dict, context: dict) -> None:
    from robomme_icl.io.hdf5 import assert_identical, assert_records_identical
    from robomme_icl.suite import EpisodeSpec

    spec = EpisodeSpec.from_dict(job["episode_spec"])
    for key, expected in (("mode", context["mode"]), ("suite_hash", context["suite_hash"]),
                          ("spec_hash", spec.spec_hash), ("seed", spec.seed), ("task_kind", spec.task_kind)):
        if row.get(key) != expected:
            raise ValueError(f"完成记录的 {key} 不匹配")
    assert_identical(job["certification"]["runtime_fingerprint"], row.get("runtime_fingerprint"), path="runtime_fingerprint")
    if row.get("render_gpu") != job["certification"]["render_gpu"]:
        raise ValueError("完成记录的固定 GPU 绑定不符")
    if row.get("passed") is not True:
        raise ValueError("既有运行已记录失败，禁止通过重复尝试掩盖失败")
    result, certification = row["result"], job["certification"]
    if result.get("content_hash") != certification["content_hash"] or result.get("frame_count") != certification["frame_count"]:
        raise ValueError("完成记录的内容摘要或帧数与认证不符")
    if context["mode"] == "reset":
        if any(result.get(key) is not True for key in ("first_equals_baseline", "second_equals_baseline", "repeat_equal")):
            raise ValueError("reset 完成记录缺少逐帧比较证据")
        _check_record(Path(certification["record_paths"][0]), spec, certification)
    else:
        data_path, replay_path = _paths(Path(job["output"]), spec)
        data = _check_record(data_path, spec, certification)
        if context["mode"] == "resume" and result.get("resumed") is not True:
            raise ValueError("resume 记录没有证明原数据被直接复用")
        if context["mode"] == "replay":
            assert_records_identical(data, _check_record(replay_path, spec, certification))


def _validate_completed_job(payload: dict) -> str:
    """中断恢复时的大型 HDF5 核对同样放入独立进程。"""
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    _validate_completed(payload["row"], payload["job"], payload["context"])
    return payload["row"]["spec_hash"]


def _execute_acceptance_job(job: dict) -> dict:
    """按固定绑定限制每卡并发，不能因为某张卡空闲就迁移 seed。"""
    if job["stop"].is_set():
        raise RuntimeError("其他验收任务已失败，停止后续执行")
    with job["gpu_guard"]:
        if job["stop"].is_set():
            raise RuntimeError("等待 GPU 期间其他验收任务失败，停止启动物理进程")
        try:
            return _run_reset(job) if job["mode"] == "reset" else _run_item(job)
        except BaseException:
            job["stop"].set()
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="robomme-ICL 正式套件验收驱动，不重新编译候选或更换 seed")
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("generate", "resume", "replay", "reset"), required=True)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--timeout-seconds", type=float, default=240,
                        help="generate/replay 物理子进程墙钟上限，不改变任务控制步或规划预算")
    parser.add_argument("--reverse", action="store_true", help="反转套件顺序，验证结果不依赖任务调度")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.workers < 1:
        raise ValueError("workers 必须大于零")
    if args.timeout_seconds <= 0:
        raise ValueError("timeout-seconds 必须大于零")
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.io.fingerprint import runtime_fingerprint, source_commit
    from robomme_icl.io.hdf5 import assert_identical
    from robomme_icl.io.paths import output_path
    from robomme_icl.suite import EpisodeSpec, load_suite

    suite = load_suite(args.suite)
    fingerprint, commit = runtime_fingerprint(), source_commit()
    specs = [EpisodeSpec.from_dict(row) for row in suite["episodes"]]
    if args.reverse:
        specs.reverse()
    output = output_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    run_name = f"{args.mode}-{'reverse' if args.reverse else 'forward'}-w{args.workers}"
    report = output_path(output / "acceptance" / run_name)
    report.mkdir(parents=True, exist_ok=True)
    context = {"schema_version": 1, "mode": args.mode, "workers": args.workers,
               "reverse": args.reverse, "timeout_seconds": args.timeout_seconds, "suite_hash": suite["suite_hash"],
               "spec_hashes": [spec.spec_hash for spec in specs], "runtime_fingerprint": fingerprint}
    jobs = {}
    gpu_fingerprints = {}
    for spec in specs:
        certification = suite["certification"][spec.spec_hash]
        render_gpu = certification["render_gpu"]
        if certification["runtime_fingerprint"].get("render_gpu") != render_gpu:
            raise ValueError("认证 GPU 绑定与指纹不同")
        if render_gpu not in gpu_fingerprints:
            gpu_fingerprints[render_gpu] = runtime_fingerprint(render_gpu=render_gpu)
        assert_identical(gpu_fingerprints[render_gpu], certification["runtime_fingerprint"], path="runtime_fingerprint")
        if not certification.get("content_hash") or not certification.get("frame_count"):
            raise ValueError("套件认证缺少完整帧内容摘要")
        jobs[spec.spec_hash] = {"episode_spec": spec.to_dict(), "certification": certification,
                               "mode": args.mode, "output": str(output), "timeout_seconds": args.timeout_seconds}
    context_path = report / "context.json"
    if context_path.exists():
        previous = _read_json(context_path)
        identity = {key: previous.get(key) for key in context}
        assert_identical(context, identity, path="acceptance_context")
    else:
        if any(report.iterdir()):
            raise ValueError(f"已有报告缺少恢复上下文，保留原目录：{report}")
        _create_json(context_path, {**context, "source_commit": commit})
    allowed = {"context.json", "summary.json"}
    if any(path.name not in allowed and not (path.name.startswith("results_") and path.suffix == ".jsonl") for path in report.iterdir()):
        raise ValueError(f"报告目录含未知文件，拒绝继续：{report}")
    rows, interrupted_tails = _read_journals(report)
    completed = {}
    for row in rows:
        key = row.get("spec_hash")
        if key not in jobs:
            raise ValueError("完成记录包含当前清单外的规格")
        if key in completed and row["result"] != completed[key]["result"]:
            raise ValueError("相同规格的重复完成记录不一致")
        completed[key] = row
    if completed:
        payloads = [{"row": row, "job": jobs[key], "context": context} for key, row in completed.items()]
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn"), max_tasks_per_child=1) as validation_pool:
            list(validation_pool.map(_validate_completed_job, payloads))
    summary_path = report / "summary.json"
    if summary_path.exists():
        summary = _read_json(summary_path)
        if summary.get("status") != "passed" or summary.get("suite_hash") != suite["suite_hash"] or summary.get("completed") != len(specs) or len(completed) != len(specs):
            raise ValueError("既有总结不完整或失败，保留原文件")
        assert_identical(fingerprint, summary.get("runtime_fingerprint"), path="runtime_fingerprint")
        assert_identical(fingerprint, runtime_fingerprint(), path="runtime_fingerprint")
        print(f"验收已经完成并复核：{summary_path}", flush=True)
        return 0
    pending = [jobs[spec.spec_hash] for spec in specs if spec.spec_hash not in completed]
    print(f"验收 {run_name}：共 {len(specs)} 条，复用 {len(completed)} 条，待执行 {len(pending)} 条", flush=True)
    segment_indices = [int(path.stem.split("_")[-1]) for path in report.glob("results_*.jsonl")]
    segment = report / f"results_{max(segment_indices, default=-1) + 1:04d}.jsonl"
    failures = []
    manager = mp.get_context("spawn").Manager()
    stop = manager.Event()
    gpu_ids = sorted(gpu_fingerprints)
    guards = {gpu: manager.BoundedSemaphore(max(1, args.workers // len(gpu_ids) + (index < args.workers % len(gpu_ids))))
              for index, gpu in enumerate(gpu_ids)}
    for job in pending:
        job["gpu_guard"] = guards[job["certification"]["render_gpu"]]
        job["stop"] = stop
    executor = ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn"), max_tasks_per_child=1)
    try:
        with segment.open("x", encoding="utf-8", buffering=1) as stream:
            futures = {executor.submit(_execute_acceptance_job, job): job for job in pending}
            for future in as_completed(futures):
                job = futures[future]
                spec = EpisodeSpec.from_dict(job["episode_spec"])
                row = {"mode": args.mode, "suite_hash": suite["suite_hash"], "task_kind": spec.task_kind,
                       "seed": spec.seed, "spec_hash": spec.spec_hash, "source_commit": commit,
                       "runtime_fingerprint": job["certification"]["runtime_fingerprint"],
                       "render_gpu": job["certification"]["render_gpu"]}
                try:
                    result = future.result()
                    row.update(passed=True, result=result)
                except Exception as exc:
                    stop.set()
                    row.update(passed=False, error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
                    failures.append(row)
                stream.write(_json(_signed(row)) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                if row["passed"]:
                    completed[spec.spec_hash] = row
                    print(f"[{len(completed)}/{len(specs)}] {args.mode} {spec.task_kind} seed={spec.seed} GPU={row['render_gpu']} 帧数={result['frame_count']} resumed={result.get('resumed', False)}", flush=True)
                else:
                    print(f"验收失败：{spec.task_kind} seed={spec.seed}：{row['error']}", flush=True)
                    for other in futures:
                        other.cancel()
                    break
    finally:
        # 异常或用户中断时也阻断正在等待卡锁的任务。
        stop.set()
        executor.shutdown(wait=True, cancel_futures=True)
        manager.shutdown()
    assert_identical(fingerprint, runtime_fingerprint(), path="runtime_fingerprint")
    summary = {**context, "source_commit": commit, "status": "failed" if failures else "passed",
               "total": len(specs), "completed": len(completed), "failed": len(failures),
               "total_frames_per_pass": sum(row["result"]["frame_count"] for row in completed.values()),
               "passes_per_spec": 2 if args.mode == "reset" else 1,
               "interrupted_tails": interrupted_tails, "jsonl_segments": [str(path) for path in sorted(report.glob("results_*.jsonl"))],
               "completed_spec_hashes": sorted(completed)}
    _create_json(summary_path, summary)
    print(f"最终总结：{summary_path} status={summary['status']} completed={len(completed)}/{len(specs)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
