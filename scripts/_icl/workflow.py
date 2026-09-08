"""复用 ICL 物理与严格记录接口，编排逐条数据、回放和视频任务。"""

from __future__ import annotations

from pathlib import Path
import traceback

from .common import TASKS, append_event, header, safe_output


def validate_bindings(fingerprints):
    from robomme_icl.io.fingerprint import runtime_fingerprint
    from robomme_icl.io.hdf5 import assert_identical

    checked = {}
    for fingerprint in fingerprints:
        gpu = fingerprint.get("render_gpu")
        if type(gpu) is not int or gpu < 0:
            raise ValueError("记录没有有效的固定物理 GPU 绑定")
        if gpu not in checked:
            checked[gpu] = runtime_fingerprint(render_gpu=gpu)
        assert_identical(fingerprint, checked[gpu], path="运行指纹；旧版清单请先用 prepare_suite.py --source-suite 重新认证")
    return sorted(checked)


def _brief(row):
    return {key: value for key, value in row.items() if key not in ("episode_spec", "runtime_fingerprint")}


def _generate_job(job):
    from robomme_icl.workflows.generate import generate_spec_job

    try:
        result = generate_spec_job(job)
        result = {**_brief(header(result["path"])), **result}
        append_event(job["run_root"], {"stage": "generate", "passed": True, **result})
        return result
    except BaseException:
        append_event(job["run_root"], {"stage": "generate", "passed": False,
                                      "seed": job["episode_spec"]["seed"], "error": traceback.format_exc()})
        raise


def generate_records(suite, specs, output, *, workers, timeout_seconds):
    from robomme_icl.workflows.workers import gpu_limits, new_manager, run_jobs

    output = safe_output(output)
    certifications = suite["certification"]
    gpus = validate_bindings([certifications[spec.spec_hash]["runtime_fingerprint"] for spec in specs])
    with new_manager() as manager:
        stop = manager.Event()
        limits = gpu_limits(manager, gpus, workers)
        jobs = []
        for spec in specs:
            cert = certifications[spec.spec_hash]
            if cert["render_gpu"] != cert["runtime_fingerprint"]["render_gpu"]:
                raise ValueError("认证 GPU 与运行指纹不同")
            jobs.append({"episode_spec": spec.to_dict(), "certification": cert,
                         "output": str(output / "hdf5_files"), "run_root": str(output),
                         "timeout_seconds": timeout_seconds, "stop": stop,
                         "gpu_limit": limits[cert["render_gpu"]]})
        return run_jobs(_generate_job, jobs, workers, stop)


def check_generation_suite(suite, output):
    """批次已有清单时，数据必须消费同一份清单；任务筛选不改变清单身份。"""
    from robomme_icl.suite import load_suite

    local_manifest = safe_output(Path(output) / "suite" / "suite.json")
    if local_manifest.exists() and load_suite(local_manifest)["suite_hash"] != suite["suite_hash"]:
        raise ValueError("输出根中的环境清单与 --suite 不同，禁止混合两批场景")


def replay_scan_root(value):
    """明确真正递归扫描的目录；单文件输入不进行目录扫描。"""
    from robomme_icl.io.paths import output_path

    source = output_path(value)
    if source.is_file():
        return None
    if source.is_dir():
        return output_path(next((source / name for name in ("hdf5_files", "data") if (source / name).is_dir()), source))
    raise FileNotFoundError(f"回放输入不存在：{source}")


def discover_inputs(value, *, tasks=None, episodes_per_task=None):
    """只扫描正式 HDF5，排除暂存、认证副本和根目录里的回放副本。"""
    from robomme_icl.io.paths import output_path

    source = output_path(value)
    base = replay_scan_root(source)
    if base is None:
        paths = [source]
    else:
        paths = [path for path in base.rglob("*.h5")
                 if not any(part.startswith(".") or part in ("certification", "replay", "suite")
                            for part in path.relative_to(base).parts)]
    rows = [header(path) for path in sorted(paths)]
    if not rows:
        raise ValueError("输入中没有完整 ICL HDF5")
    identities = [(row["task_kind"], row["seed"]) for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("输入包含重复 task/seed，不能混合认证或回放副本")
    if tasks is not None:
        if not set(tasks).issubset({row["task_kind"] for row in rows}):
            raise ValueError("输入缺少指定任务")
        rows = [row for row in rows if row["task_kind"] in tasks]
    rows.sort(key=lambda row: (TASKS.index(row["task_kind"]), row["episode"], row["seed"]))
    counts, selected = {}, []
    for row in rows:
        count = counts.get(row["task_kind"], 0)
        if episodes_per_task is None or count < episodes_per_task:
            selected.append(row)
            counts[row["task_kind"]] = count + 1
    return selected


def check_replay_destinations(rows, output, *, scan_root=None):
    output = safe_output(output)
    if scan_root is not None and output.is_relative_to(Path(scan_root).resolve()):
        raise ValueError("回放输出不能位于实际 HDF5 扫描目录内，否则重试会混入回放副本")
    for row in rows:
        target = output / "hdf5_files" / row["task_kind"] / f"seed_{row['seed']}.h5"
        source = Path(row["path"])
        if target.resolve() == source or (target.exists() and target.samefile(source)):
            raise ValueError("回放输出与输入相同，不能把原文件当作已回放结果")


def _replay_job(job):
    from robomme_icl.workflows.replay import replay_episode

    row = job["input"]
    try:
        with job["gpu_limit"]:
            if job["stop"].is_set():
                raise RuntimeError("其他回放任务已失败，停止启动后续物理进程")
            target = Path(job["output"]) / "hdf5_files" / row["task_kind"] / f"seed_{row['seed']}.h5"
            result = replay_episode(row["path"], target, timeout_seconds=job["timeout_seconds"])
        result = {**_brief(header(result["path"])), **result, "source_path": row["path"]}
        append_event(job["output"], {"stage": "replay", **result})
        print(f"已回放 {row['task_kind']} seed={row['seed']} GPU={row['render_gpu']}", flush=True)
        return result
    except BaseException:
        job["stop"].set()
        append_event(job["output"], {"stage": "replay", "passed": False,
                                    "seed": row["seed"], "error": traceback.format_exc()})
        raise


def replay_records(rows, output, *, workers, timeout_seconds, scan_root=None):
    from robomme_icl.workflows.workers import gpu_limits, new_manager, run_jobs

    check_replay_destinations(rows, output, scan_root=scan_root)
    gpus = validate_bindings([row["runtime_fingerprint"] for row in rows])
    with new_manager() as manager:
        stop = manager.Event()
        limits = gpu_limits(manager, gpus, workers)
        jobs = [{"input": row, "output": str(output), "stop": stop,
                 "gpu_limit": limits[row["render_gpu"]], "timeout_seconds": timeout_seconds} for row in rows]
        return run_jobs(_replay_job, jobs, workers, stop)


def _video_job(job):
    from .video import export_video

    if job["stop"].is_set():
        raise RuntimeError("其他视频导出失败，停止后续编码")
    row = job["record"]
    try:
        path = Path(job["output"]) / "videos" / row["task_kind"] / f"seed_{row['seed']}.mp4"
        result = export_video(row["path"], path)
        if (result["spec_hash"] != row["spec_hash"] or result["source_content_hash"] != row["content_hash"]
                or result["source_operation_count"] != row["frame_count"]):
            raise ValueError("视频来源或帧数与本条已核对 HDF5 不一致")
        result.update(task_kind=row["task_kind"], seed=row["seed"], render_gpu=row["render_gpu"])
        append_event(job["output"], {"stage": "video", "passed": True, **result})
        print(f"已保存视频 {row['task_kind']} seed={row['seed']}：{path}", flush=True)
        return result
    except BaseException:
        job["stop"].set()
        append_event(job["output"], {"stage": "video", "passed": False,
                                    "seed": row["seed"], "error": traceback.format_exc()})
        raise


def export_videos(records, output, *, workers):
    from robomme_icl.workflows.workers import new_manager, run_jobs

    with new_manager() as manager:
        stop = manager.Event()
        jobs = [{"record": row, "output": str(output), "stop": stop} for row in records]
        return run_jobs(_video_job, jobs, workers, stop)
