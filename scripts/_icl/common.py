"""入口共用的参数、路径、运行记录与失败处理。"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[2]
TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def signed(value):
    body = {key: item for key, item in value.items() if key != "report_hash"}
    return {**body, "report_hash": hashlib.sha256(canonical(body).encode()).hexdigest()}


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("report_hash") != signed(value)["report_hash"]:
        raise ValueError(f"运行记录摘要不符，保留原文件：{path}")
    return value


def safe_output(path):
    """复用库的实体路径约束，并禁止将参考集或源码作为输出目录。"""
    from robomme_icl.io.paths import output_path, repository_root

    if repository_root().resolve() != ROOT:
        raise ValueError("导入的 robomme_icl 不属于当前脚本仓库")
    target = output_path(path)
    for protected in (ROOT / "data", ROOT / "src", ROOT / "scripts", ROOT / "tests", ROOT / ".git"):
        if target == protected or target.is_relative_to(protected):
            raise ValueError(f"输出不得写入参考数据、源码或脚本目录：{target}")
    return target


def atomic_json(path, value):
    path = safe_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".metadata-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(signed(value), stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def append_event(root, value):
    """文件锁保护多个工作进程的完整单行写入，正文不承载图像。"""
    target = safe_output(Path(root) / "episode_results.jsonl")
    with target.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(canonical(signed(value)) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def script_fingerprint():
    files = [ROOT / "scripts" / name for name in (
        "prepare_suite.py", "generate_dataset.py", "replay_dataset.py", "plot_distribution.py")]
    files += sorted((ROOT / "scripts" / "_icl").glob("*.py"))
    return hashlib.sha256(canonical([
        (path.relative_to(ROOT).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()) for path in files
    ]).encode()).hexdigest()


@contextmanager
def run_phase(output, stage, identity, execution):
    """相同数据身份允许改变并发重试，所有调用和阶段结果另行留档。"""
    from robomme_icl.io.fingerprint import source_commit

    identity = json.loads(canonical(identity))
    root = safe_output(output)
    path = root / "run_parameters.json"
    if path.exists():
        parameters = read_json(path)
        if parameters["scripts_hash"] != script_fingerprint():
            raise ValueError("入口或辅助实现已改变，请使用新输出目录")
        if stage in parameters["phases"] and parameters["phases"][stage] != identity:
            raise ValueError("已有阶段的数据来源或规格不符，禁止覆盖")
        existing_stages = set(parameters["phases"])
        if (stage == "replay" and existing_stages & {"prepare", "generate"}
                or stage in {"prepare", "generate"} and "replay" in existing_stages):
            raise ValueError("回放与准备／生成必须使用独立输出根，禁止混用同一批次目录")
    else:
        if root.exists() and any(item.name != "logs" for item in root.iterdir()):
            raise ValueError(f"输出目录已有内容但缺少运行身份记录：{root}")
        parameters = {"schema_version": 1, "scripts_hash": script_fingerprint(), "phases": {}, "invocations": []}
    root.mkdir(parents=True, exist_ok=True)
    parameters["phases"][stage] = identity
    invocation = {"stage": stage, "started_at": datetime.now(timezone.utc).isoformat(),
                  "source_commit": source_commit(), "argv": list(sys.argv), **execution}
    parameters["invocations"].append(invocation)
    atomic_json(path, parameters)
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    result = {"stage": stage, "status": "running", "invocation": invocation}
    try:
        yield root, result
        result["status"] = "passed"
    except BaseException:
        result.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        result["ended_at"] = datetime.now(timezone.utc).isoformat()
        summary_path = root / "run_summary.json"
        summary = read_json(summary_path) if summary_path.exists() else {"schema_version": 1, "phases": {}}
        summary["phases"][stage] = result
        statuses = {phase["status"] for phase in summary["phases"].values()}
        summary["status"] = "failed" if "failed" in statuses else ("passed" if statuses == {"passed"} else "running")
        atomic_json(summary_path, summary)
        atomic_json(logs / f"{stage}-{len(parameters['invocations']):04d}.json", result)


def task_list(text):
    values = [item.strip() for item in text.split(",")]
    if not values or len(set(values)) != len(values) or not set(values).issubset(TASKS):
        raise argparse.ArgumentTypeError("tasks 必须是四个 ICL 任务的无重复逗号分隔列表")
    return values


def gpu_list(text):
    try:
        values = [int(item) for item in text.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("gpus 必须是逗号分隔的物理 GPU 编号") from exc
    if not values or any(item < 0 for item in values) or len(set(values)) != len(values):
        raise argparse.ArgumentTypeError("gpus 必须是无重复的非负编号")
    return sorted(values)


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("数值必须大于零")
    return value


def add_execution_options(parser, *, video=False):
    parser.add_argument("--workers", type=positive_int, default=32)
    parser.add_argument("--timeout-seconds", type=positive_int, default=1200)
    parser.add_argument("--tasks", type=task_list)
    parser.add_argument("--episodes-per-task", type=positive_int)
    if video:
        parser.add_argument("--video-workers", type=positive_int, default=4)


def select_specs(suite, tasks=None, episodes_per_task=None):
    from robomme_icl.suite import EpisodeSpec

    specs = [EpisodeSpec.from_dict(item) for item in suite["episodes"]]
    if tasks is not None:
        missing = set(tasks) - {spec.task_kind for spec in specs}
        if missing:
            raise ValueError(f"清单缺少指定任务：{sorted(missing)}")
        specs = [spec for spec in specs if spec.task_kind in tasks]
    counts, result = {}, []
    for spec in specs:
        count = counts.get(spec.task_kind, 0)
        if episodes_per_task is None or count < episodes_per_task:
            result.append(spec)
            counts[spec.task_kind] = count + 1
    if not result:
        raise ValueError("没有选中任何环境")
    return result


def header(path):
    """完整帧校验由库完成，此处只读取调度及索引必需的标量。"""
    import h5py
    from robomme_icl.suite import EpisodeSpec
    from robomme_icl.io.paths import output_path

    path = output_path(path)
    with h5py.File(path, "r") as handle:
        if not bool(handle.attrs.get("complete", False)):
            raise ValueError(f"HDF5 尚未完整写入：{path}")
        spec = EpisodeSpec.from_dict(json.loads(handle["setup/episode_spec"][()].decode()))
        fingerprint = json.loads(handle["setup/runtime_fingerprint"][()].decode())
        return {"path": str(path), "task_kind": spec.task_kind, "seed": spec.seed,
                "episode": spec.to_dict()["episode"], "spec_hash": spec.spec_hash,
                "episode_spec": spec.to_dict(), "runtime_fingerprint": fingerprint,
                "render_gpu": fingerprint["render_gpu"], "frame_count": int(handle["steps"].attrs["length"]),
                "content_hash": str(handle.attrs["content_hash"])}
