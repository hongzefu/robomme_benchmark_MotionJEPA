"""正式 v3 全部阶段结束后，独立核对控制证据并排他写出最终报告。"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_COMMIT = "e34474a6304b917b44cedae129ac621ddd52a430"
PHASES = (
    "certification96", "generate-reverse-w32", "generate-reverse-w16",
    "resume-forward-w4", "replay-forward-w32", "reset-reverse-w32", "plots",
)
ACCEPTANCE = {
    "generate-reverse-w32": ("primary_output", "generate", 32, True),
    "generate-reverse-w16": ("comparison_output", "generate", 16, True),
    "resume-forward-w4": ("primary_output", "resume", 4, False),
    "replay-forward-w32": ("primary_output", "replay", 32, False),
    "reset-reverse-w32": ("primary_output", "reset", 32, True),
}
TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")


class ValidationError(RuntimeError):
    """证据尚未完成或彼此不一致，禁止发布最终报告。"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def verify_signature(value: dict, label: str) -> dict:
    require(isinstance(value, dict), f"{label} 必须为对象")
    body = {key: item for key, item in value.items() if key != "report_hash"}
    require(value.get("report_hash") == digest(body), f"{label} 签名错误")
    return body


def safe_path(value: str | Path) -> Path:
    from robomme_icl.io.paths import output_path
    return output_path(value)


def read_json(path: Path, *, signed: bool = False) -> dict:
    path = safe_path(path)
    require(path.is_file(), f"缺少证据文件：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    return verify_signature(value, str(path)) if signed else value


def file_evidence(path: Path) -> dict:
    path = safe_path(path)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size}


def read_signed_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        raw = safe_path(path).read_bytes()
        require(not raw or raw.endswith(b"\n"), f"JSONL 存在未完成末行：{path}")
        for index, line in enumerate(raw.splitlines(), 1):
            require(bool(line.strip()), f"JSONL 存在空行：{path}:{index}")
            rows.append(verify_signature(json.loads(line), f"{path}:{index}"))
    return rows


def validate_acceptance(
    summary: dict, rows: list[dict], specs: list[dict], certification: dict,
    *, mode: str, workers: int, reverse: bool, suite_hash: str, common_fingerprint: dict,
    timeout_seconds: int = 1200,
) -> dict[str, dict]:
    """校验已验收的规格集合、逐条签名内容与对应认证，不执行仿真。"""
    expected = {spec["spec_hash"]: spec for spec in specs}
    expected_order = [spec["spec_hash"] for spec in (list(reversed(specs)) if reverse else specs)]
    require(summary.get("status") == "passed" and summary.get("failed") == 0, "验收总结未通过")
    require(summary.get("total") == len(specs) and summary.get("completed") == len(specs), "验收数量不完整")
    require(summary.get("mode") == mode and summary.get("workers") == workers and summary.get("reverse") is reverse, "验收模式或调度参数不同")
    require(summary.get("timeout_seconds") == timeout_seconds, "验收墙钟上限与正式配置不同")
    require(summary.get("suite_hash") == suite_hash and summary.get("spec_hashes") == expected_order, "验收套件或提交顺序不同")
    require(summary.get("runtime_fingerprint") == common_fingerprint, "总结公共运行指纹不同")
    require(summary.get("completed_spec_hashes") == sorted(expected), "完成规格集合不同")
    require(not summary.get("interrupted_tails"), "验收含未完成日志末行，不能直接发布完整汇总")
    require(summary.get("passes_per_spec") == (2 if mode == "reset" else 1), "验收比较次数不符")
    by_hash = {}
    for row in rows:
        key = row.get("spec_hash")
        require(key in expected and key not in by_hash, "验收记录出现未知或重复规格")
        spec, cert = expected[key], certification[key]
        require(row.get("passed") is True and row.get("mode") == mode and row.get("suite_hash") == suite_hash, "单条验收未通过或模式不同")
        require(row.get("task_kind") == spec["task_kind"] and row.get("seed") == spec["seed"], "单条任务或 seed 不同")
        require(row.get("render_gpu") == cert["render_gpu"] and row.get("runtime_fingerprint") == cert["runtime_fingerprint"], "单条 GPU 绑定或指纹不同")
        result = row["result"]
        require(result.get("passed") is True and result.get("content_hash") == cert["content_hash"], "单条内容摘要与认证不同")
        require(result.get("frame_count") == cert["frame_count"] and result.get("render_gpu") == cert["render_gpu"], "单条帧数或结果 GPU 不同")
        if mode == "generate":
            require(result.get("resumed") is False, "32/16 生成对照必须全部为新生成，禁止混入 resumed")
        elif mode == "resume":
            require(result.get("resumed") is True, "resume 阶段实际生成了新数据")
        elif mode == "reset":
            require(all(result.get(name) is True for name in ("first_equals_baseline", "second_equals_baseline", "repeat_equal")), "reset 缺少两次逐位相等证据")
        if mode != "reset":
            require(result.get("seed") == spec["seed"] and result.get("spec_hash") == key, "结果身份字段不同")
        by_hash[key] = row
    require(set(by_hash) == set(expected), "验收 JSONL 未覆盖全部规格")
    total_frames = sum(certification[key]["frame_count"] for key in expected)
    require(summary.get("total_frames_per_pass") == total_frames, "总结总帧数与逐条记录不同")
    return by_hash


def read_phases(report: Path) -> dict[str, dict]:
    main = safe_path(report / "main.log").read_text(encoding="utf-8")
    require(main.rstrip().endswith("EXIT_CODE=0"), "主脚本尚未成功结束，暂不发布 FINAL")
    with safe_path(report / "phase_timings.tsv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    require([row["phase"] for row in rows] == list(PHASES), "阶段列表不完整、重复或顺序不同")
    phases, previous_end = {}, -1
    for row in rows:
        name = row["phase"]
        for field in ("start_epoch_ns", "end_epoch_ns", "elapsed_ns", "command_exit", "tee_exit", "phase_exit"):
            row[field] = int(row[field])
        require(all(row[field] == 0 for field in ("command_exit", "tee_exit", "phase_exit")), f"阶段未完整成功：{name}")
        require(row["end_epoch_ns"] > row["start_epoch_ns"] >= previous_end, f"阶段时间非法：{name}")
        require(row["elapsed_ns"] == row["end_epoch_ns"] - row["start_epoch_ns"], f"阶段 elapsed 不一致：{name}")
        require(f"START {name} {row['start_utc']}" in main, f"缺少 START 记录：{name}")
        require(f"FINISH {name} EXIT_CODE=0 {row['end_utc']}" in main, f"缺少 FINISH 记录：{name}")
        require(safe_path(report / f"{name}.log").read_text().rstrip().endswith("EXIT_CODE=0"), f"阶段日志末尾没有成功记录：{name}")
        row["elapsed_seconds"] = row["elapsed_ns"] / 1_000_000_000
        phases[name] = row
        previous_end = row["end_epoch_ns"]
    return phases


def parse_timings(text: str) -> list[dict]:
    """直接解码每个 ICL_TIMING 后的 JSON，允许并发 stdout 把两条日志连在一行。"""
    decoder, rows = json.JSONDecoder(), []
    pattern = r"ICL_TIMING seed=(\d+) GPU=(\d+) frames=(\d+) "
    for match in re.finditer(pattern, text):
        timings, length = decoder.raw_decode(text[match.end():])
        require(all(name in timings and math.isfinite(timings[name]) and timings[name] >= 0
                    for name in ("build_seconds", "run_seconds", "write_seconds")), "ICL_TIMING 数值非法")
        rows.append({"seed": int(match[1]), "gpu": int(match[2]), "frames": int(match[3]),
                     **timings, "raw": text[match.start():match.end() + length]})
    return rows


def summary_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {"count": len(values), "mean": statistics.mean(values), "sum": sum(values),
            "minimum": ordered[0], "maximum": ordered[-1],
            "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * .95) - 1)]}


def grouped_statistics(specs: list[dict], certs: dict, timings: list[dict]) -> dict:
    timing_by_seed = defaultdict(list)
    for timing in timings:
        timing_by_seed[timing["seed"]].append(timing)
    groups = {}
    dimensions = {
        "task": lambda spec: spec["task_kind"],
        "difficulty": lambda spec: spec["difficulty"],
        "gpu": lambda spec: str(certs[spec["spec_hash"]]["render_gpu"]),
        "task_difficulty_gpu": lambda spec: f"{spec['task_kind']}/{spec['difficulty']}/gpu{certs[spec['spec_hash']]['render_gpu']}",
    }
    for dimension, key_fn in dimensions.items():
        buckets = defaultdict(list)
        for spec in specs:
            buckets[key_fn(spec)].append(spec)
        groups[dimension] = {}
        for key, members in sorted(buckets.items()):
            events = [event for spec in members for event in timing_by_seed[spec["seed"]]]
            groups[dimension][key] = {
                "episodes": len(members), "frames_per_pass": sum(certs[spec["spec_hash"]]["frame_count"] for spec in members),
                "timed_physical_runs": len(events),
                "build_seconds": summary_stats([event["build_seconds"] for event in events]),
                "run_seconds": summary_stats([event["run_seconds"] for event in events]),
                "write_seconds": summary_stats([event["write_seconds"] for event in events]),
            }
    return groups


def gpu_phase_statistics(path: Path, phases: dict, host_timezone: str) -> dict:
    aliases = {"UTC": 0, "GMT": 0, "EDT": -4, "EST": -5}
    zone = timezone(timedelta(hours=aliases[host_timezone])) if host_timezone in aliases else ZoneInfo(host_timezone)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    values = defaultdict(list)
    raw_text = safe_path(path).read_text()
    raw_lines = raw_text.splitlines()
    ignored_tail = False
    for index, line in enumerate(raw_lines):
        row = next(csv.reader([line]))
        if len(row) != 4 and index == len(raw_lines) - 1 and not raw_text.endswith("\n"):
            ignored_tail = True
            continue
        require(len(row) == 4, "GPU CSV 存在损坏行")
        moment = datetime.strptime(row[0].strip(), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=zone)
        delta = moment.astimezone(timezone.utc) - epoch
        nanoseconds = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000
        gpu = int(row[1])
        utilization, memory = float(row[2].split()[0]), float(row[3].split()[0])
        require(gpu in (0, 1) and 0 <= utilization <= 100 and math.isfinite(memory) and memory >= 0, "GPU CSV 数值非法")
        values[gpu].append((nanoseconds, utilization, memory))
    result = {"timestamp_timezone": host_timezone, "ignored_incomplete_tail": ignored_tail, "phases": {}}
    for phase, window in phases.items():
        result["phases"][phase] = {}
        for gpu in (0, 1):
            rows = [row for row in values[gpu] if window["start_epoch_ns"] <= row[0] <= window["end_epoch_ns"]]
            require(bool(rows), f"阶段 {phase} GPU {gpu} 没有采样证据")
            intervals = [(right[0] - left[0]) / 1e9 for left, right in zip(rows, rows[1:])]
            result["phases"][phase][str(gpu)] = {
                "samples": len(rows), "utilization_mean_percent": statistics.mean(row[1] for row in rows),
                "utilization_zero_fraction": sum(row[1] == 0 for row in rows) / len(rows),
                "utilization_peak_percent": max(row[1] for row in rows),
                "peak_memory_mib": max(row[2] for row in rows), "actual_interval_seconds": summary_stats(intervals),
            }
    return result


def validate_h5_header(path: Path, spec: dict, cert: dict, cache: dict) -> None:
    """仅核记录头；全帧逐位比较的证据由已签名验收记录提供。"""
    import h5py

    path = safe_path(path)
    if str(path) in cache:
        require(cache[str(path)]["spec_hash"] == spec["spec_hash"], "同一路径引用了不同规格")
        return
    def text(value):
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)
    with h5py.File(path, "r") as handle:
        require(handle.attrs.get("schema_version") == 1 and bool(handle.attrs.get("complete", False)), f"HDF5 不完整：{path}")
        require(text(handle.attrs["content_hash"]) == cert["content_hash"], f"HDF5 内容摘要头不同：{path}")
        require(json.loads(text(handle["setup/episode_spec"][()])) == spec, f"HDF5 spec 不同：{path}")
        require(text(handle["setup/spec_hash"][()]) == spec["spec_hash"] and int(handle["setup/seed"][()]) == spec["seed"], f"HDF5 身份不同：{path}")
        require(text(handle["setup/env_id"][()]) == spec["env_id"], f"HDF5 env_id 不同：{path}")
        require(json.loads(text(handle["setup/runtime_fingerprint"][()])) == cert["runtime_fingerprint"], f"HDF5 GPU/运行指纹不同：{path}")
        count = int(handle["steps"].attrs["length"])
        require(count == cert["frame_count"], f"HDF5 帧数不同：{path}")
        last = handle[f"steps/{count - 1:08d}/info"]
        require(json.loads(text(last["success"][()])) is True and json.loads(text(last["fail"][()])) is False, f"HDF5 终态不是严格成功：{path}")
    cache[str(path)] = {"path": str(path), "spec_hash": spec["spec_hash"], "content_hash": cert["content_hash"],
                        "frame_count": count, "render_gpu": cert["render_gpu"], "size_bytes": path.stat().st_size}


def validate_figures(report: Path, suite_path: Path, suite: dict) -> dict:
    path = report / "figures/figure_sources.json"
    sources = read_json(path)
    require(sources.get("schema_version") == 1 and sources.get("source_status") == "certified", "图表来源状态非法")
    require(safe_path(sources["source_suite"]) == suite_path and sources.get("suite_hash") == suite["suite_hash"], "图表引用的套件不同")
    require(sources.get("episodes_total") == 96, "图表未包含96条规格")
    figures = sources["figures"]
    require(len(figures) == 4 and {figure["task_kind"] for figure in figures} == set(TASKS), "图表任务覆盖不完整")
    for figure in figures:
        specs = [spec for spec in suite["episodes"] if spec["task_kind"] == figure["task_kind"]]
        require(figure["episodes"] == len(specs) and figure["episode_spec_hashes"] == [spec["spec_hash"] for spec in specs], "图表规格集合不同")
        examples = [spec for spec in specs if spec["spec_hash"] == figure["single_example_spec_hash"] and spec["seed"] == figure["single_example_seed"]]
        require(len(examples) == 1, "图表单例来源不明")
        actual_points = Counter(actor["kind"] for spec in specs for actor in spec["actors"] if "parent_id" not in actor)
        require(dict(actual_points) == figure["scatter_point_counts"], "图表散点数量不符合真实 actor")
        image = safe_path(figure["path"])
        require(image.is_relative_to(report / "figures") and image.is_file(), "图表文件路径非法或缺失")
        figure["file_evidence"] = file_evidence(image)
    return {"source_record": file_evidence(path), "provenance": sources}


def render_markdown(result: dict) -> str:
    lines = ["# robomme-ICL v3 全量结果", "",
             f"基线 `{result['source_commit']}` 下的96条规格已完成双进程严格认证、32/16 worker 两套新生成、断点复用、动作回放和同环境连续 reset 验收。所有正式阶段退出码均为0。", "",
             "本工具核对已签名验收证据、套件及 HDF5 记录头，没有重新执行仿真或再次解码全部 RGB；逐帧字节一致的结论来自已通过的严格验收链。", "",
             f"每遍共 {result['frames_per_pass']} 帧；两轮生成均覆盖相同96个 spec，使用相同逆序与原 GPU 绑定，所有生成记录均为 `resumed=false`。", "",
             "## 阶段结果", "", "| 阶段 | 条数 | 墙钟秒数 | episode/秒 |", "| --- | ---: | ---: | ---: |"]
    for phase, value in result["phases"].items():
        count = 96 if phase != "plots" else 4
        lines.append(f"| {phase} | {count} | {value['elapsed_seconds']:.6f} | {count/value['elapsed_seconds']:.6f} |")
    comparison = result["generation_comparison"]
    lines += ["", "## 32 与16 worker 匹配批次对照", "",
              f"32 worker：{comparison['workers32_seconds']:.6f} 秒，{comparison['workers32_frames_per_second']:.6f} 帧/秒；16 worker：{comparison['workers16_seconds']:.6f} 秒，{comparison['workers16_frames_per_second']:.6f} 帧/秒。", "",
              f"本批次的16/32吞吐比为 **{comparison['throughput16_over32']:.6f}**。这是先32、后16的一次顺序实验，没有独立预热或稳态分段，可能受缓存和主机负载影响，不能据此宣称全局最优并发。", "",
              "## 实际规格与帧数", "", "| 任务/难度/GPU | 条数 | 每遍帧数 |", "| --- | ---: | ---: |"]
    for key, group in result["suite_groups"]["task_difficulty_gpu"].items():
        lines.append(f"| {key} | {group['episodes']} | {group['frames_per_pass']} |")
    lines += ["", "## 按阶段对齐的 GPU 采样", "",
              "| 阶段 | GPU | 采样数 | 利用率均值 | 0%占比 | 峰值显存 MiB |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for phase, values in result["gpu_statistics"]["phases"].items():
        for gpu, row in values.items():
            lines.append(f"| {phase} | {gpu} | {row['samples']} | {row['utilization_mean_percent']:.3f}% | {100*row['utilization_zero_fraction']:.3f}% | {row['peak_memory_mib']:.0f} |")
    lines += ["", "采样窗口按 UTC 阶段时间与 GPU 日志的主机时区对齐。利用率为样本均值；原始间隔统计保存在 FINAL.json，不把名义500ms当作硬件计数器分辨率。", "",
              "没有逐控制步起止时间戳，不能进行慢步/非慢步 GPU 利用率分层。逐条 build/run/write 及按任务、难度、GPU 的耗时统计保存在 FINAL.json；并行进程耗时之和不是阶段墙钟时间。reset/resume没有逐条 ICL_TIMING，不能为它们补造任务级耗时。", "",
              "## 原版边界与图表来源", "",
              f"原版 Git tree `{result['legacy_tree']}` 与2.23基线及当前 HEAD 相同；当前源码、依赖、GPU/PCI指纹与运行记录一致。", "",
              "图表规格集合、样例seed和真实actor散点数均已核对：[figure_sources.json](figures/figure_sources.json)。"]
    for figure in result["figures"]["provenance"]["figures"]:
        lines += ["", f"![{figure['task_kind']} 实际配额与位置](figures/{Path(figure['path']).name})"]
    lines += ["", "原始证据：[run_context.json](run_context.json)、[phase_timings.tsv](phase_timings.tsv)、[main.log](main.log)、[gpu_samples.csv](gpu_samples.csv)。FINAL.json保留原始纳秒时间、ICL_TIMING原文和所有控制文件摘要。", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "artifacts/reports/robomme-icl/formal-v3")
    parser.add_argument("--expected-commit", default=EXPECTED_COMMIT)
    args = parser.parse_args(argv)
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.io.fingerprint import runtime_fingerprint
    from robomme_icl.suite import load_suite

    report = safe_path(args.report_dir)
    require(not (report / "FINAL.json").exists() and not (report / "FINAL.md").exists(), "FINAL已存在，拒绝覆盖")
    phases = read_phases(report)
    context = read_json(report / "run_context.json")
    require(context["source_commit"] == args.expected_commit and context["start_status"] == "", "正式基线与干净启动记录不符")
    require(hashlib.sha256(context["script"].encode()).hexdigest() == context["script_sha256"], "留档脚本摘要不符")
    baseline_tree = subprocess.check_output(["git", "rev-parse", f"{args.expected_commit}:src/robomme"], cwd=ROOT, text=True).strip()
    current_tree = subprocess.check_output(["git", "rev-parse", "HEAD:src/robomme"], cwd=ROOT, text=True).strip()
    require(baseline_tree == current_tree == context["legacy_tree"], "原版 src/robomme Git tree 已改变")
    fingerprints = {str(gpu): runtime_fingerprint(render_gpu=gpu) for gpu in (0, 1)}
    require(fingerprints == context["runtime_fingerprints"], "当前源码/依赖/设备与2.23运行指纹不同")
    common = runtime_fingerprint()
    suite_path = safe_path(context["suite"])
    suite_path = suite_path / "suite.json" if suite_path.is_dir() else suite_path
    suite = load_suite(suite_path)
    specs, certs = suite["episodes"], suite["certification"]
    require(len(specs) == 96 and Counter(spec["task_kind"] for spec in specs) == {task: 24 for task in TASKS}, "套件必须是四任务各24条")
    require(Counter((spec["task_kind"], spec["difficulty"]) for spec in specs) == {(task, level): 8 for task in TASKS for level in ("easy", "medium", "hard")}, "难度配额不是各8条")
    require(suite["configs"]["task"] == context["task_config"] and suite["configs"]["position"] == context["position_config"], "套件配置与运行配置不同")
    by_seed = {spec["seed"]: spec for spec in specs}
    headers, evidence = {}, {}
    for spec in specs:
        cert = certs[spec["spec_hash"]]
        gpu = cert["render_gpu"]
        require(type(gpu) is int and gpu == spec["seed"] % 2, "认证未遵循固定 seed GPU 绑定")
        require(cert["runtime_fingerprint"] == fingerprints[str(gpu)] and cert.get("fresh_process") is True and cert["geometry"]["ok"] is True, "认证指纹、独立进程或碰撞证明不符")
        require(type(cert["frame_count"]) is int and cert["frame_count"] > 0 and len(cert["record_paths"]) == 2, "认证帧数或重复记录数量不符")
        for path in cert["record_paths"]:
            validate_h5_header(Path(path), spec, cert, headers)
    acceptance, physical_timings = {}, {}
    for phase, (output_key, mode, workers, reverse) in ACCEPTANCE.items():
        output = safe_path(context[output_key])
        directory = output / "acceptance" / f"{mode}-{'reverse' if reverse else 'forward'}-w{workers}"
        summary_path, context_path = directory / "summary.json", directory / "context.json"
        summary, accepted_context = read_json(summary_path, signed=True), read_json(context_path, signed=True)
        for key in ("mode", "workers", "reverse", "suite_hash", "spec_hashes", "runtime_fingerprint", "timeout_seconds"):
            require(accepted_context.get(key) == summary.get(key), f"{phase} 的context与summary不同：{key}")
        journals = sorted(directory.glob("results_*.jsonl"))
        require([str(safe_path(path)) for path in journals] == summary["jsonl_segments"], f"{phase} JSONL文件清单不同")
        rows = read_signed_rows(journals)
        checked = validate_acceptance(summary, rows, specs, certs, mode=mode, workers=workers, reverse=reverse,
                                      suite_hash=suite["suite_hash"], common_fingerprint=common, timeout_seconds=context["timeout_seconds"])
        for spec in specs:
            result = checked[spec["spec_hash"]]["result"]
            if mode != "reset":
                expected_path = output / ("replay" if mode == "replay" else "data") / spec["task_kind"] / f"seed_{spec['seed']}.h5"
                require(safe_path(result["path"]) == expected_path, "验收结果引用了错误输出目录")
                validate_h5_header(expected_path, spec, certs[spec["spec_hash"]], headers)
        acceptance[phase] = {"summary": summary, "validated_rows": len(rows), "evidence": [file_evidence(path) for path in (summary_path, context_path, *journals)]}
    for phase in PHASES:
        events = parse_timings(safe_path(report / f"{phase}.log").read_text())
        for event in events:
            require(event["seed"] in by_seed, f"{phase} timing包含未知seed")
            cert = certs[by_seed[event["seed"]]["spec_hash"]]
            require(event["gpu"] == cert["render_gpu"] and event["frames"] == cert["frame_count"], f"{phase} timing绑定或帧数不同")
        expected_repeats = 2 if phase == "certification96" else 1 if phase in ("generate-reverse-w32", "generate-reverse-w16", "replay-forward-w32") else 0
        require(Counter(event["seed"] for event in events) == ({seed: expected_repeats for seed in by_seed} if expected_repeats else {}), f"{phase} ICL_TIMING覆盖不完整或重复")
        physical_timings[phase] = {"events": events, "groups": grouped_statistics(specs, certs, events)}
    total_frames = sum(cert["frame_count"] for cert in certs.values())
    seconds32, seconds16 = (phases[f"generate-reverse-w{workers}"]["elapsed_seconds"] for workers in (32, 16))
    for path in (report / "run_context.json", report / "phase_timings.tsv", report / "main.log", report / "gpu_samples.csv", report / "iostat.log", suite_path, *(report / f"{phase}.log" for phase in PHASES)):
        evidence[str(path)] = file_evidence(path)
    result = {
        "schema_version": 1, "status": "passed", "source_commit": context["source_commit"],
        "legacy_tree": baseline_tree, "runtime_fingerprints": fingerprints, "suite_hash": suite["suite_hash"],
        "episodes": 96, "frames_per_pass": total_frames, "phases": phases,
        "suite_groups": grouped_statistics(specs, certs, []), "acceptance": acceptance,
        "physical_timings": physical_timings, "gpu_statistics": gpu_phase_statistics(report / "gpu_samples.csv", phases, context["host_timezone"]),
        "hdf5_headers_verified": list(headers.values()), "figures": validate_figures(report, suite_path, suite),
        "generation_comparison": {"workers32_seconds": seconds32, "workers16_seconds": seconds16,
                                  "workers32_episodes_per_second": 96/seconds32, "workers16_episodes_per_second": 96/seconds16,
                                  "workers32_frames_per_second": total_frames/seconds32, "workers16_frames_per_second": total_frames/seconds16,
                                  "throughput16_over32": seconds32/seconds16, "same_specs_gpu_order": True,
                                  "resumed_records": 0, "execution_order": [32, 16], "global_optimum_claimed": False},
        "limitations": ["仅汇总签名验收链并核HDF5记录头，不重新解码全批RGB", "没有逐控制步时间戳，不能做慢步/非慢步GPU分层", "一次32后16顺序实验，无独立预热/稳态分段，不能宣称全局最优", "并行进程耗时总和不等于phase墙钟；reset/resume无逐条ICL_TIMING"],
        "evidence": evidence, "report_tool": file_evidence(Path(__file__)),
    }
    require(fingerprints == {str(gpu): runtime_fingerprint(render_gpu=gpu) for gpu in (0, 1)}, "汇总过程中源码或运行环境改变")
    markdown = render_markdown(result)
    result["report_hash"] = digest(result)
    with (report / "FINAL.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    with (report / "FINAL.md").open("x", encoding="utf-8") as stream:
        stream.write(markdown)
    print(f"最终汇总已完成：{report / 'FINAL.json'}；{report / 'FINAL.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
