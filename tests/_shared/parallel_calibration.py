"""schema 3 原值并行校准；所有生成仍通过原生产入口执行。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "scripts/configs/newtask-v2/native_sampling.json"
TASKS = (("BinFill", "hard"), ("RouteStick", "hard"),
         ("VideoUnmaskSwap", "hard"), ("VideoRepick", "medium"))
MODES = {"S0a": (["0"], 1), "S0b": (["0"], 1), "S1": (["1"], 1),
         "P0": (["0"], 2), "P01": (["0", "1"], 4)}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cases() -> list[dict[str, Any]]:
    from scripts.seed_layout import get_layout
    return [{"task": task, "difficulty": difficulty, "episode": episode,
             "seed": get_layout("train").seed(task, episode, 0), "attempt": 0}
            for task, difficulty in TASKS for episode in range(4)]


def key(item: dict[str, Any]) -> tuple:
    return tuple(item[name] for name in ("task", "difficulty", "episode", "seed", "attempt"))


def associate(records: list[dict], expected: list[dict]) -> tuple[dict, list[str]]:
    """只按输入身份配对；重复、额外或缺失结果均保留为错误。"""
    grouped: dict[tuple, list[dict]] = {}
    errors = []
    wanted = {key(item) for item in expected}
    for record in records:
        try:
            identity = key(record)
            if identity not in wanted:
                errors.append(f"额外结果：{identity}")
            grouped.setdefault(identity, []).append(record)
        except (KeyError, TypeError) as exc:
            errors.append(f"结果身份缺失：{exc}")
    result = {}
    for identity in wanted:
        found = grouped.get(identity, [])
        if len(found) != 1:
            errors.append(f"{identity} 的结果数量为 {len(found)}，应为 1")
        else:
            result[identity] = found[0]
    return result, errors


def pci_key(value: str) -> str:
    return ":".join(str(value).lower().split(":")[-2:])


def concurrency(mode: str, rows: list[dict], gpu_map: dict[str, str]) -> dict:
    """只比较实际 step 窗口；并发模式要求不同 PID。"""
    errors = []
    windows = []
    for row in rows:
        try:
            timing, bound = row["timing"], row["bound"]
            values = [timing[name] for name in ("reset_ns", "first_step_ns", "last_step_ns", "close_ns")]
            if not all(type(value) is int and value > 0 for value in values):
                raise ValueError("时间字段缺失或类型错误")
            if not values[0] <= values[1] < values[2] <= values[3]:
                raise ValueError("reset、step、close 时间顺序错误")
            gpu = str(bound["gpu"])
            if gpu not in MODES[mode][0] or pci_key(bound["pci"]) != pci_key(gpu_map[gpu]):
                raise ValueError("实际 GPU 或 PCI 绑定错误")
            if bound.get("error") or bound.get("can_render") is not True:
                raise ValueError("GPU 初始化或渲染能力检查失败")
            if type(bound["pid"]) is not int or bound["pid"] != timing["pid"]:
                raise ValueError("时间证据与 worker PID 不匹配")
            windows.append({"gpu": gpu, "pid": bound["pid"], "start": values[1], "end": values[2],
                            "episode": row["episode"]})
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    if len(rows) != 4 or len(windows) != 4:
        errors.append("必须有四条完整执行窗口")
    overlaps = []
    if mode.startswith("S"):
        for left, right in itertools.combinations(windows, 2):
            if min(left["end"], right["end"]) > max(left["start"], right["start"]):
                errors.append("串行模式出现执行窗口重叠")
    else:
        required = 2 if mode == "P0" else 4
        for group in itertools.combinations(windows, required):
            duration = min(row["end"] for row in group) - max(row["start"] for row in group)
            gpu_counts = {gpu: sum(row["gpu"] == gpu for row in group) for gpu in MODES[mode][0]}
            if len({row["pid"] for row in group}) == required and all(n == 2 for n in gpu_counts.values()) and duration > 0:
                overlaps.append(duration / 1e9)
        if not overlaps:
            errors.append("并发证据不足：未观察到规定的不同 PID 共同执行窗口")
    return {"passed": not errors, "errors": errors, "windows": windows,
            "max_common_overlap_s": max(overlaps, default=0)}


def sources() -> dict[str, str]:
    tracked = subprocess.check_output(["git", "ls-files", "src", "scripts", "tests/_shared", "tests/lightweight/test_parallel_calibration.py", "pyproject.toml", "uv.lock"], cwd=REPO, text=True).splitlines()
    tracked += ["tests/_shared/parallel_calibration.py", "tests/lightweight/test_parallel_calibration.py"]
    return {name: sha(REPO / name) for name in sorted(set(tracked)) if (REPO / name).is_file()}


def gpu_inventory() -> list[dict[str, str]]:
    fields = ["index", "pci.bus_id", "uuid", "name", "driver_version", "memory.total"]
    output = subprocess.check_output(["nvidia-smi", "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits"], text=True, timeout=10)
    return [dict(zip(fields, (part.strip() for part in line.split(",")))) for line in output.splitlines()]


def resource_sample(pgid: int) -> dict:
    sample: dict[str, Any] = {"monotonic_ns": time.monotonic_ns(), "processes": []}
    for directory in Path("/proc").glob("[0-9]*"):
        try:
            stat = (directory / "stat").read_text().rsplit(")", 1)[1].split()
            if int(stat[2]) != pgid:
                continue
            status = (directory / "status").read_text()
            match = re.search(r"^VmRSS:\s+(\d+)", status, re.M)
            sample["processes"].append({"pid": int(directory.name), "rss_kib": int(match[1]) if match else 0})
        except (OSError, ValueError, IndexError):
            continue
    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True, timeout=3)
        sample["gpus"] = [dict(zip(("gpu", "used_mib", "utilization_percent"), (p.strip() for p in line.split(",")))) for line in output.splitlines()]
    except (OSError, subprocess.SubprocessError) as exc:
        sample["error"] = str(exc)
    return sample


def resource_summary(path: Path) -> dict:
    """显存是整卡采样值，RSS 是本批进程组总和；不伪称精确峰值。"""
    result: dict[str, Any] = {"sample_count": 0, "max_gpu_used_mib": {},
                              "max_process_group_rss_kib": 0, "errors": []}
    try:
        for line in path.read_text().splitlines():
            sample = json.loads(line)
            result["sample_count"] += 1
            result["max_process_group_rss_kib"] = max(result["max_process_group_rss_kib"], sum(row["rss_kib"] for row in sample["processes"]))
            for gpu in sample.get("gpus", []):
                value = float(gpu["used_mib"])
                result["max_gpu_used_mib"][gpu["gpu"]] = max(result["max_gpu_used_mib"].get(gpu["gpu"], 0), value)
            if sample.get("error"):
                result["errors"].append(sample["error"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["errors"].append(str(exc))
    return result


def execute(command: list[str], env: dict[str, str], directory: Path, timeout: float) -> dict:
    """实时转发原始输出；独立进程组保证超时能清理 worker 与编码子进程。"""
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    timed_out = False
    terminate_at = None
    result: dict[str, Any] = {"command": command, "timeout_s": timeout, "started_at": time.time()}
    with (directory / "stdout.log").open("wb") as log, (directory / "resources.jsonl").open("w") as resources:
        process = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        result["pgid"] = process.pid
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        sampled = 0.0
        while selector.get_map() or process.poll() is None:
            now = time.monotonic()
            if now - started >= timeout and not timed_out:
                timed_out, terminate_at = True, now
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if terminate_at is not None and now - terminate_at >= 5:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if now - sampled >= 1:
                resources.write(json.dumps(resource_sample(process.pid)) + "\n")
                resources.flush()
                sampled = time.monotonic()
            for event, _ in selector.select(0.2):
                data = os.read(event.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(event.fileobj)
                else:
                    log.write(data)
                    log.flush()
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
        process.wait()
        selector.close()
        process.stdout.close()
    result.update(returncode=process.returncode, timed_out=timed_out,
                  elapsed_s=time.monotonic() - started, finished_at=time.time())
    write_json(directory / "execution.json", result)
    return result


def command_for(root: Path, mode: str, task: str, difficulty: str, count: int = 4) -> list[str]:
    gpus, workers = MODES.get(mode, MODES["S0a"])
    return ["uv", "run", "--no-sync", "python", "scripts/generate_dataset_newseed.py",
            "--output-dir", str(root / "runs" / mode / task), "--env", task,
            "--episodes", str(count), "--episode-start", "0", "--workers", str(workers),
            "--gpus", ",".join(gpus), "--layout", "train", "--difficulty", "001" if difficulty == "hard" else "010",
            "--max-attempts", "1", "--max-tasks-per-child", "8", "--affinity", "none",
            "--sampling-config", str(CONFIG)]


def batch(root: Path, mode: str, task: str, difficulty: str, timeout: float, count: int = 4, observer: bool = True) -> dict:
    from tests._shared.parity_runner import _observer_env
    env = _observer_env(root / "evidence" / task, mode, True)
    # 排除调用者残留的观察器或外部绑卡设置，绑定仅由生产池负责。
    for name in list(env):
        if name.startswith("PARITY_") and name not in {"PARITY_OBSERVER_DIR", "PARITY_EVIDENCE_DIR", "PARITY_LABEL", "PARITY_STEPS"}:
            env.pop(name)
    env.pop("CUDA_VISIBLE_DEVICES", None)
    env["PARITY_TIMING"] = "1"
    if not observer:
        env = {name: value for name, value in env.items() if not name.startswith("PARITY_")}
        env.pop("PYTHONPATH", None)
    print(f"开始 {mode}/{task}，{count} 条，观察器={observer}", flush=True)
    return execute(command_for(root, mode, task, difficulty, count), env, root / "logs" / mode / task, timeout)


def validate_evidence(payload: dict, case: dict) -> list[str]:
    errors = []
    for name in ("task", "seed", "difficulty"):
        if payload.get(name) != case[name]:
            errors.append(f"观察器身份不符：{name}")
    for name in ("rng", "events", "boundaries", "steps", "recordings"):
        if not isinstance(payload.get(name), list) or not payload[name]:
            errors.append(f"观察器缺少非空字段：{name}")
    if payload.get("evidence_version") != 3:
        errors.append("观察器版本必须为 3")
    if payload.get("rng_total") != len(payload.get("rng") or []) or payload.get("rng_recorded") != payload.get("rng_total"):
        errors.append("随机流不完整")
    for count, name in (("event_count", "events"), ("step_count", "steps")):
        if payload.get(count) != len(payload.get(name) or []):
            errors.append(f"观察器计数不符：{count}")
    if type(payload.get("rrt_fallback_count")) is not int or payload["rrt_fallback_count"] < 0:
        errors.append("规划回退计数缺失")
    initial = payload.get("initial_obs")
    if not isinstance(initial, dict) or not initial.get("value") or set(initial.get("rgb", {})) != {"front_rgb", "wrist_rgb"}:
        errors.append("缺少完整 reset 观测")
    return errors


def collect_batch(root: Path, mode: str, task: str, gpu_map: dict, snapshot: dict) -> dict:
    from tests._shared.native_sampling_parity import load_evidence
    from scripts.generate_dataset_newseed import inspect_episode_terminal
    import h5py
    expected = [case for case in cases() if case["task"] == task]
    directory = root / "runs" / mode / task
    errors: list[str] = []
    input_errors: list[str] = []
    rows = []
    try:
        execution = read_json(root / "logs" / mode / task / "execution.json")
        if execution["timed_out"] or execution["returncode"] != 0:
            errors.append(f"批次失败：退出码={execution['returncode']}，超时={execution['timed_out']}")
        records = [json.loads(line) for line in (directory / "episode_results.jsonl").read_text().splitlines() if line]
        indexed, identity_errors = associate(records, expected)
        errors.extend(identity_errors)
        params = read_json(directory / "run_parameters.json")
        gpus, workers = MODES[mode]
        required = {"tasks": [task], "episodes": 4, "episode_start": 0, "workers": workers,
                    "gpus": gpus, "seed_layout": "train", "difficulty_ratio": "001" if expected[0]["difficulty"] == "hard" else "010",
                    "max_attempts": 1, "max_tasks_per_child": 8, "limit_threads": True, "affinity": "none"}
        for name, value in required.items():
            if params.get(name) != value:
                input_errors.append(f"运行参数不符：{name}")
        used = read_json(directory / "sampling_config_used.json")
        want = {name: {block: snapshot[block][name] for block in ("parameters", "positions")} for name, _ in TASKS}
        if used != want:
            input_errors.append("实际采样配置与冻结副本不一致")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"批次记录不可读：{exc}")
        input_errors.append("批次输入无法核验")
        indexed, execution = {}, {}
    errors.extend(input_errors)
    for case in expected:
        row = {**case, "errors": []}
        record = indexed.get(key(case))
        if record is None:
            row["errors"].append("缺少唯一结果")
        else:
            row.update({name: record.get(name) for name in ("ok", "bound", "failure_class", "error_type", "error", "started_at", "finished_at", "wall_s", "peak_rss_mb")})
            if record.get("ok") is not True:
                row["errors"].append("生成未成功")
            if record.get("ok") is True:
                try:
                    h5 = directory / "hdf5_files" / f"{task}_ep{case['episode']}_seed{case['seed']}.h5"
                    if Path(record.get("h5_path", "")).resolve() != h5.resolve():
                        raise ValueError("HDF5 路径与用例不匹配")
                    with h5py.File(h5, "r") as handle:
                        _, done, contract_errors = inspect_episode_terminal(handle[f"episode_{case['episode']}"], str(h5))
                        if done is not True or contract_errors:
                            raise ValueError(f"HDF5 终态契约失败：{contract_errors}")
                    row["h5_path"] = str(h5)
                    row["h5_sha256"] = sha(h5)
                except Exception as exc:
                    row["errors"].append(f"HDF5 验证失败：{type(exc).__name__}: {exc}")
            # 原 wrapper 失败时不保留成功 HDF5，但观察器和执行窗口仍须独立读取。
            try:
                evidence_dir = root / "evidence" / task / mode / f"{task}_seed{case['seed']}"
                payload = load_evidence(evidence_dir, difficulty=case["difficulty"])
                row["errors"].extend(validate_evidence(payload, case))
                row["evidence_path"] = payload["_path"]
                row["evidence_sha256"] = sha(Path(payload["_path"]))
                row["rrt_fallback_count"] = payload.get("rrt_fallback_count")
                timing_files = list(evidence_dir.glob("*.timing.json"))
                if len(timing_files) != 1:
                    raise ValueError(f"时间证据应恰好一份，实际 {len(timing_files)}")
                timing = read_json(timing_files[0])
                if any(timing.get(name) != case[name] for name in ("task", "seed", "difficulty")) or timing.get("pid") != payload.get("pid"):
                    raise ValueError("时间、观察器或用例身份不一致")
                row["timing"] = timing
                row["timing_path"] = str(timing_files[0])
                row["timing_sha256"] = sha(timing_files[0])
            except Exception as exc:
                row["errors"].append(f"观察器或时间证据验证失败：{type(exc).__name__}: {exc}")
        # 生产入口在单条失败时也返回非零；其余完整成功条仍可独立比较。
        row["valid"] = not row["errors"] and not input_errors and not execution.get("timed_out", False)
        rows.append(row)
    concurrency_result = concurrency(mode, rows, gpu_map)
    resources = resource_summary(root / "logs" / mode / task / "resources.jsonl")
    if resources["errors"] or not resources["sample_count"]:
        errors.append("资源采样缺失或不完整，详见 resources.errors")
    return {"mode": mode, "task": task, "execution": execution, "errors": errors,
            "resources": resources,
            "rows": rows, "concurrency": concurrency_result,
            "passed": not errors and all(row["valid"] for row in rows) and concurrency_result["passed"]}


def compare_pair(left: dict, right: dict) -> dict:
    from tests._shared.native_sampling_parity import compare_h5, compare_evidence, load_evidence
    if not left.get("valid") or not right.get("valid"):
        return {"passed": False, "reason": "一侧生成或证据不合格"}
    try:
        h5_differences = compare_h5(left["h5_path"], right["h5_path"])
        evidence = compare_evidence(load_evidence(left["evidence_path"]), load_evidence(right["evidence_path"]))
        no_fallback = left.get("rrt_fallback_count") == 0 and right.get("rrt_fallback_count") == 0
        return {"passed": not h5_differences and evidence["passed"] and no_fallback,
                "h5_difference_count": len(h5_differences), "h5_differences": h5_differences,
                "evidence": evidence, "no_planner_fallback": no_fallback}
    except Exception as exc:
        return {"passed": False, "reason": f"比较异常：{type(exc).__name__}: {exc}"}


def decide(reference: dict, comparisons: dict, batches: dict) -> dict:
    """缺一格也不能授予模式通过；各模式独立给出结论。"""
    return {mode: {"passed": len(reference) == 16 and all(value["passed"] for value in reference.values())
                  and len(comparisons.get(mode, {})) == 16 and all(value["passed"] for value in comparisons.get(mode, {}).values())
                  and len(batches.get(mode, {})) == 4 and all(value["passed"] for value in batches.get(mode, {}).values())}
            for mode in ("S1", "P0", "P01")}


def failure_diagnostics(indexed: dict) -> dict:
    """失败签名单独对照，不将重复失败转为参考合格或数值一致。"""
    result = {}
    for case in cases():
        identity = key(case)
        rows = {mode: indexed[mode][identity] for mode in MODES}
        if not any(row.get("ok") is False for row in rows.values()):
            continue
        signatures = {mode: {name: row.get(name) for name in ("ok", "failure_class", "error_type", "error", "rrt_fallback_count")}
                      for mode, row in rows.items()}
        same = all(row.get("ok") is False for row in rows.values()) and all(value == signatures["S0a"] for value in signatures.values())
        result[f"{case['task']}/{case['difficulty']}/episode_{case['episode']}"] = {
            "same_failure_signature": same, "signatures": signatures,
            "note": "仅对照错误签名，不构成成功参考或完整失败轨迹逐位一致结论"}
    return result


def timeline(report: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(5, 1, figsize=(12, 17))
    for ax, (mode, tasks) in zip(axes, report["batches"].items()):
        windows = [(task, row) for task, batch_result in tasks.items() for row in batch_result["concurrency"]["windows"]]
        origin = min((row["start"] for _, row in windows), default=0)
        for index, (task, row) in enumerate(windows):
            ax.barh(index, (row["end"] - row["start"]) / 1e9, left=(row["start"] - origin) / 1e9,
                    color="#2878b5" if row["gpu"] == "0" else "#e07b39")
        ax.set_yticks(range(len(windows)), [f"{task}/ep{row['episode']} GPU{row['gpu']} PID{row['pid']}" for task, row in windows], fontsize=7)
        ax.set_title(mode)
        ax.set_xlabel("s")
        ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def compare(root: Path) -> dict:
    context = read_json(root / "context.json")
    snapshot = read_json(root / "native_sampling.json")
    integrity_errors = []
    try:
        frozen = read_json(root / "frozen_manifest.json")
        for name in ("context.json", "cases.json", "native_sampling.json"):
            if frozen[name] != sha(root / name):
                integrity_errors.append(f"冻结文件散列不符：{name}")
        if read_json(root / "finished.json").get("sources_unchanged") is not True:
            integrity_errors.append("运行期间源码发生变化")
        smoke = read_json(root / "smoke.json")
        from tests._shared.native_sampling_parity import compare_h5
        smoke_h5 = [root / "runs" / label / "BinFill/hdf5_files/BinFill_ep0_seed4000.h5" for label in ("smoke-off", "smoke-on")]
        if not smoke.get("passed") or compare_h5(*smoke_h5):
            integrity_errors.append("冒烟开关产物复核失败")
    except (OSError, ValueError, KeyError) as exc:
        integrity_errors.append(f"冻结输入、冒烟或完整运行记录缺失：{exc}")
    if sha(root / "native_sampling.json") != context["config_sha256"] or read_json(root / "cases.json") != cases():
        integrity_errors.append("冻结配置或用例清单不一致")
    gpu_map = {row["index"]: row["pci.bus_id"] for row in context["gpus"]}
    batches = {mode: {task: collect_batch(root, mode, task, gpu_map, snapshot) for task, _ in TASKS} for mode in MODES}
    indexed = {mode: {key(row): row for entry in tasks.values() for row in entry["rows"]} for mode, tasks in batches.items()}
    reference, comparisons = {}, {mode: {} for mode in ("S1", "P0", "P01")}
    for case in cases():
        identity = key(case)
        name = f"{case['task']}/{case['difficulty']}/episode_{case['episode']}"
        left = indexed["S0a"][identity]
        reference[name] = compare_pair(left, indexed["S0b"][identity])
        for mode in comparisons:
            comparisons[mode][name] = compare_pair(left, indexed[mode][identity]) if reference[name]["passed"] else {"passed": False, "reason": "串行参考未建立"}
        print(f"已比较 {name}：参考={reference[name]['passed']}，" + "，".join(f"{mode}={comparisons[mode][name]['passed']}" for mode in comparisons), flush=True)
    modes = decide(reference, comparisons, batches)
    # 两轮参考的绑定和串行窗口本身也必须有效。
    baseline_batches_ok = all(entry["passed"] for mode in ("S0a", "S0b") for entry in batches[mode].values())
    for result in modes.values():
        result["passed"] = result["passed"] and baseline_batches_ok and not integrity_errors
    report = {"scope": "当前源码、依赖、硬件、schema 3 原值；不含 VideoRepick hard 或新值注入",
              "context": context, "integrity_errors": integrity_errors, "batches": batches,
              "reference": reference, "comparisons": comparisons, "modes": modes,
              "failure_diagnostics": failure_diagnostics(indexed),
              "comparison_context": {"created_at": time.time(),
                  "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                  "tool_sha256": {name: sha(REPO / name) for name in (
                      "tests/_shared/parallel_calibration.py", "tests/_shared/native_sampling_parity.py",
                      "tests/_shared/parity_observer.py")}},
              "passed": all(value["passed"] for value in modes.values())}
    write_json(root / "comparison.json", report)
    docs = REPO / "docs/validation/newtask-v2" / root.name
    docs.mkdir(parents=True, exist_ok=True)
    # result.json 是既有 A/B/C 对拍包的发现约定，不能混入不同报告结构。
    write_json(docs / "parallel_result.json", report)
    write_json(docs / "cases.json", cases())
    write_json(docs / "context.json", context)
    timeline(report, docs / "timeline.svg")
    lines = ["# schema 3 原值多 GPU、多 worker 校准实测", "", report["scope"], "",
             "本报告由 compare 从原始产物重新计算；时间图只表示 step 执行阶段重叠，不表示 CUDA 内核并发。", "",
             "| 轮次 | 成功生成 | 完整有效产物 | 并发／串行窗口通过批次 | 批次总耗时（秒） |", "|---|---:|---:|---:|---:|"]
    for mode, entries in batches.items():
        rows = [row for entry in entries.values() for row in entry["rows"]]
        elapsed = sum(entry["execution"].get("elapsed_s", 0) for entry in entries.values())
        lines.append(f"| {mode} | {sum(row.get('ok') is True for row in rows)}/16 | {sum(row['valid'] for row in rows)}/16 | {sum(entry['concurrency']['passed'] for entry in entries.values())}/4 | {elapsed:.2f} |")
    lines += ["", f"串行参考合格：{sum(value['passed'] for value in reference.values())}/16。", "",
              "| 模式 | 严格比较通过 | 校准结论 |", "|---|---:|---|"]
    for mode, result in modes.items():
        lines.append(f"| {mode} | {sum(value['passed'] for value in comparisons[mode].values())}/16 | {'通过' if result['passed'] else '未通过'} |")
    lines += ["", "![GPU 与 PID 执行时间图](timeline.svg)", "", "## 逐条结果与首个分歧", "",
              "详细记录见 [parallel_result.json](parallel_result.json)，输入见 [cases.json](cases.json)，环境和来源散列见 [context.json](context.json)。", ""]
    lines.extend(f"- 输入完整性：{error}" for error in integrity_errors)
    for name, failure in report["failure_diagnostics"].items():
        lines.append(f"- {name}：五轮错误签名相同={failure['same_failure_signature']}；重复失败不计为参考通过。")
    for mode, entries in batches.items():
        for task, entry in entries.items():
            for error in entry["errors"] + entry["concurrency"]["errors"]:
                lines.append(f"- {mode}/{task}：{error}")
            for row in entry["rows"]:
                for error in row["errors"]:
                    lines.append(f"- {mode}/{task}/episode_{row['episode']}：{error}；{row.get('error_type') or ''} {row.get('error') or ''}")
    for label, entries in [("S0a↔S0b", reference), *comparisons.items()]:
        for name, result in entries.items():
            if not result["passed"]:
                detail = result.get("reason") or (result.get("h5_differences") or [""])[0]
                if not detail and result.get("no_planner_fallback") is False:
                    detail = "存在规划回退"
                if not detail:
                    detail = "观察器内容分歧，详见逐段 first_divergence"
                lines.append(f"- {label}/{name}：{detail}")
    lines += ["", "## 复现", "", "以下 run 必须更换为未使用编号；长任务须用 detached tmux、pipefail、tee 和退出码留档。", "", "```bash", "command -v uv",
              "uv run --no-sync python -m tests._shared.parallel_calibration run --run-id <新编号>",
              f"uv run --no-sync python -m tests._shared.parallel_calibration compare --run-id {root.name}", "```", "",
              f"重产物与逐批命令、退出码和资源采样：`artifacts/parallel-calibration/{root.name}/`。", "",
              "资源值为每秒采样观察到的最大值；worker 的 peak_rss_mb 是进程生命周期高水位，不作为单局峰值。", "",
              "只有本轮全部比较及并发判据通过才允许判通过；失败不换 seed、不补样本、不放宽容差。", ""]
    lines += ["## 资源采样", "", "显存为整卡采样值，包含其他已有进程；RSS 为本批进程组总和。", "",
              "| 轮次／任务 | 采样次数 | GPU 0 最大显存 MiB | GPU 1 最大显存 MiB | 最大进程组 RSS MiB | 采样错误数 |",
              "|---|---:|---:|---:|---:|---:|"]
    for mode, entries in batches.items():
        for task, entry in entries.items():
            sample = entry["resources"]
            lines.append(f"| {mode}/{task} | {sample['sample_count']} | {sample['max_gpu_used_mib'].get('0', '未采到')} | {sample['max_gpu_used_mib'].get('1', '未采到')} | {sample['max_process_group_rss_kib'] / 1024:.1f} | {len(sample['errors'])} |")
    lines.append("")
    (docs / "README.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(docs / "manifest.json", {str(path.relative_to(REPO)): sha(path) for path in sorted(docs.iterdir()) if path.is_file() and path.name != "manifest.json"})
    print(json.dumps({"modes": modes, "report": str(docs / "README.md")}, ensure_ascii=False), flush=True)
    return report


def run(root: Path, timeout: float, smoke_only: bool = False) -> dict:
    if not shutil.which("uv"):
        raise RuntimeError("uv 不可用，禁止回退到裸 Python")
    from scripts.generate_dataset_newseed import load_sampling_config
    load_sampling_config(CONFIG, REPO)
    inventory = gpu_inventory()
    if not {"0", "1"} <= {row["index"] for row in inventory}:
        raise RuntimeError("校准需要 GPU 0 和 GPU 1")
    if root.exists() or (REPO / "docs/validation/newtask-v2" / root.name).exists():
        raise FileExistsError("运行编号已存在，禁止复用")
    root.mkdir(parents=True)
    shutil.copyfile(CONFIG, root / "native_sampling.json")
    context = {"run_id": root.name, "created_at": time.time(), "config_sha256": sha(CONFIG),
               "source_sha256": sources(), "gpus": inventory, "python": sys.version,
               "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
               "packages": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "sapien", "h5py", "matplotlib")},
               "timeout_s": timeout, "modes": MODES,
               "environment": {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "CUDA_VISIBLE_DEVICES", "DISPLAY", "VK_ICD_FILENAMES")}}
    write_json(root / "context.json", context)
    write_json(root / "cases.json", cases())
    write_json(root / "frozen_manifest.json", {name: sha(root / name) for name in ("context.json", "cases.json", "native_sampling.json")})
    smoke_started = time.monotonic()
    smoke_runs = {}
    for label, enabled in (("smoke-off", False), ("smoke-on", True)):
        smoke_runs[label] = batch(root, label, "BinFill", "hard", min(timeout, max(1, 290 - (time.monotonic() - smoke_started))), 1, enabled)
        if smoke_runs[label]["returncode"] or smoke_runs[label]["timed_out"]:
            write_json(root / "smoke.json", {"passed": False, "runs": smoke_runs})
            raise RuntimeError("单条冒烟失败，禁止启动正式矩阵")
    from tests._shared.native_sampling_parity import compare_h5, load_evidence
    filenames = [root / "runs" / label / "BinFill/hdf5_files/BinFill_ep0_seed4000.h5" for label in smoke_runs]
    differences = compare_h5(*filenames)
    evidence_dir = root / "evidence/BinFill/smoke-on/BinFill_seed4000"
    payload = load_evidence(evidence_dir)
    evidence_errors = validate_evidence(payload, cases()[0])
    timing_files = list(evidence_dir.glob("*.timing.json"))
    if len(timing_files) != 1 or read_json(timing_files[0]).get("close_ns") is None:
        evidence_errors.append("冒烟时间记录不完整")
    smoke = {"passed": not differences and not evidence_errors and payload.get("rrt_fallback_count") == 0,
             "h5_differences": differences, "evidence_errors": evidence_errors,
             "rrt_fallback_count": payload.get("rrt_fallback_count"), "runs": smoke_runs,
             "elapsed_s": time.monotonic() - smoke_started}
    write_json(root / "smoke.json", smoke)
    if not smoke["passed"]:
        raise RuntimeError("观察器开关校准失败，禁止启动正式矩阵")
    if smoke_only:
        return smoke
    for mode in MODES:
        for task, difficulty in TASKS:
            if sources() != context["source_sha256"]:
                raise RuntimeError("运行期间源码或输入发生变化，停止矩阵")
            batch(root, mode, task, difficulty, timeout)
    write_json(root / "finished.json", {"finished_at": time.time(), "sources_unchanged": sources() == context["source_sha256"]})
    return compare(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run", "compare"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--smoke-only", action="store_true", help="只做开关冒烟，不启动矩阵")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", args.run_id) or args.timeout <= 0:
        parser.error("运行编号格式错误或 timeout 非正数")
    root = REPO / "artifacts/parallel-calibration" / args.run_id
    result = run(root, args.timeout, args.smoke_only) if args.operation == "run" else compare(root)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
