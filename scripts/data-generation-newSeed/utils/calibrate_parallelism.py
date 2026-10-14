#!/usr/bin/env python3
"""并行度标定：先量最重档内存，再按准入预算跑多卡阶梯。

稳态吞吐剔除前后各 W 条完成事件，不退回全窗口。持久 GPU 采样的
开销仍须在正式起跑前同机验证；本脚本的单测只运行 CPU 假子进程。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import psutil


SCRIPT_DIR = Path(__file__).resolve().parent
NEWSEED_DIR = SCRIPT_DIR.parent
GENERATOR = NEWSEED_DIR / "generate_dataset_newseed.py"
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_CELLS = "L32:32:0,4,1,5:on;L64:64:0,1,4,5,2,3,6,7:on;L96:96:0,1,4,5,2,3,6,7:on"
MIXED_CYCLE = ("easy", "medium", "hard", "xhard12", "xhard14", "xhard16", "xhard18", "xhard20")
TASK_ORDER = ("BinFill", "PickXtimes", "SwingXtimes", "StopCube", "VideoUnmask", "ButtonUnmask",
              "VideoUnmaskSwap", "ButtonUnmaskSwap", "PickHighlight", "VideoRepick", "VideoPlaceButton",
              "VideoPlaceOrder", "MoveCube", "InsertPeg", "PatternLock", "RouteStick")
PROBE_ENV = "BinFill,PickXtimes,SwingXtimes,VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick,PatternLock,RouteStick"


@dataclass(frozen=True)
class Cell:
    name: str
    workers: int
    gpus: str
    limit_threads: bool

    @property
    def gpu_ids(self) -> tuple[str, ...]:
        return tuple(self.gpus.split(","))


def parse_cells(text: str) -> list[Cell]:
    """分号隔档位；worker 数必须能均分到唯一的非负 GPU 编号。"""
    cells = []
    for item in text.split(";"):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 4:
            raise ValueError(f"档位应为 name:workers:gpus:on|off，当前为 {item!r}")
        name, workers_text, gpu_text, limit = parts
        workers = int(workers_text)
        ids = tuple(part.strip() for part in gpu_text.split(","))
        if not name or Path(name).name != name or name in (".", ".."):
            raise ValueError("档名必须是单一目录名")
        if not all(part.isdigit() for part in ids):
            raise ValueError("GPU 编号必须是非负整数")
        ids = tuple(str(int(part)) for part in ids)
        if len(set(ids)) != len(ids) or workers <= 0 or workers % len(ids):
            raise ValueError("workers 必须为正数且能均分到不重复的 GPU")
        if limit.lower() not in ("on", "off", "1", "0", "true", "false", "yes", "no"):
            raise ValueError("限线程字段必须为 on 或 off")
        cells.append(Cell(name, workers, ",".join(ids), limit.lower() in ("on", "1", "true", "yes")))
    if not cells or len({cell.name for cell in cells}) != len(cells):
        raise ValueError("至少需要一个档位，档名不得重复")
    return cells


def _group_processes(pgid: int) -> list[psutil.Process]:
    """只核对本档会话的进程组；僵尸已不占资源、不再执行。"""
    found = []
    for proc in psutil.process_iter():
        try:
            if os.getpgid(proc.pid) == pgid and proc.status() != psutil.STATUS_ZOMBIE:
                found.append(proc)
        except (ProcessLookupError, psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def terminate_group(process: subprocess.Popen, grace_s: float = 30) -> dict[str, Any]:
    """先 TERM，最多等 30 秒；仍有组成员才 KILL，最后核验零残留。"""
    pgid = process.pid  # start_new_session=True，父进程退出后仍能处理其子进程。
    sent_kill = False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace_s
    while _group_processes(pgid) and time.monotonic() < deadline:
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    if _group_processes(pgid):
        sent_kill = True
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()
    # SIGKILL 到实际退出有调度延迟，此等待也只针对本档进程组。
    deadline = time.monotonic() + 5
    while _group_processes(pgid) and time.monotonic() < deadline:
        time.sleep(0.05)
    remaining = [proc.pid for proc in _group_processes(pgid)]
    result = {"pgid": pgid, "sigkill": sent_kill, "remaining_pids": remaining, "zero_residual": not remaining}
    if remaining:
        raise RuntimeError(f"本档进程组仍有残留：{result}")
    return result


class ResourceSampler:
    """CPU/内存由线程采样，相关 GPU 只用一个持久 nvidia-smi 进程。"""

    def __init__(self, gpus: str, interval: float = 0.5) -> None:
        self.gpus = gpus
        self.interval = interval
        self.rows: list[dict[str, Any]] = []
        self.gpu_rows: list[dict[str, Any]] = []
        self.peak_worker_rss_mb = 0.0
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._gpu_process: subprocess.Popen | None = None
        self.pid: int | None = None

    def _gpu_loop(self) -> None:
        assert self._gpu_process is not None and self._gpu_process.stdout is not None
        for line in self._gpu_process.stdout:
            fields = [field.strip() for field in line.split(",")]
            if len(fields) != 4:
                continue
            try:
                index, util, used, total = map(float, fields)
            except ValueError:
                continue
            self.gpu_rows.append({"t": time.time(), "index": int(index), "util": util,
                                  "mem_mb": used, "total_mb": total})

    def _loop(self) -> None:
        psutil.cpu_percent(interval=None)
        while not self._stop.is_set():
            memory = psutil.virtual_memory()
            try:
                load1 = psutil.getloadavg()[0]
                children = psutil.Process(self.pid).children(recursive=True) if self.pid else []
                rss = [proc.memory_info().rss / 2**20 for proc in children]
                self.peak_worker_rss_mb = max([self.peak_worker_rss_mb, *rss])
            except (OSError, psutil.NoSuchProcess, psutil.AccessDenied):
                load1 = float("nan")
            self.rows.append({"t": time.time(), "cpu_percent": psutil.cpu_percent(interval=None),
                              "load1": load1, "mem_avail_gb": memory.available / 2**30,
                              "mem_used_gb": (memory.total - memory.available) / 2**30})
            self._stop.wait(self.interval)

    def start(self, pid: int) -> None:
        self.pid = pid
        self._gpu_process = subprocess.Popen(
            ["nvidia-smi", "-i", self.gpus,
             "--query-gpu=index,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits", "-lms", str(round(self.interval * 1000))],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self._threads = [threading.Thread(target=self._gpu_loop, daemon=True),
                         threading.Thread(target=self._loop, daemon=True)]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._gpu_process is not None:
            self._gpu_process.terminate()
            try:
                self._gpu_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._gpu_process.kill()
                self._gpu_process.wait()
        for thread in self._threads:
            thread.join(timeout=5)


def _steady_window(results: Sequence[dict[str, Any]], workers: int) -> dict[str, Any]:
    """仅真正剔除首尾后的窗口有效；样本不足时不退回全窗口。"""
    done = sorted((item for item in results if item.get("ok") and item.get("finished_at")),
                  key=lambda item: float(item["finished_at"]))
    window = done[workers:-workers] if len(done) > 2 * workers + 1 else []
    if len(window) < 2:
        return {"episodes": len(window), "throughput_ep_per_min": None, "trimmed": False}
    span = float(window[-1]["finished_at"]) - float(window[0]["finished_at"])
    return {"episodes": len(window), "span_s": span,
            "throughput_ep_per_min": len(window) / span * 60 if span > 0 else None,
            "mean_wall_s": statistics.mean(float(item["wall_s"]) for item in window),
            "trimmed": True, "t_start": float(window[0]["finished_at"]),
            "t_end": float(window[-1]["finished_at"])}


def _resource_summary(rows: Sequence[dict[str, Any]], start: float | None, end: float | None,
                      gpu_rows: Sequence[dict[str, Any]] = (),
                      results: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    """稳态均值与零利用占比；慢步指 wall_s 高于窗口内完成项均值。"""
    if start is None or end is None:
        return {}
    inside = [row for row in rows if start <= row["t"] <= end]
    done = [item for item in results if item.get("ok") and start <= item.get("finished_at", 0) <= end]
    mean_wall = statistics.mean(item["wall_s"] for item in done) if done else None
    slow_intervals = [(item["finished_at"] - item["wall_s"], item["finished_at"])
                      for item in done if item["wall_s"] > mean_wall]
    per_gpu: dict[int, list[dict[str, Any]]] = {}
    for row in gpu_rows:
        if start <= row["t"] <= end:
            per_gpu.setdefault(row["index"], []).append(row)

    def mean(values: Sequence[float]) -> float | None:
        clean = [value for value in values if value == value]
        return statistics.mean(clean) if clean else None

    def gpu_summary(data: list[dict[str, Any]]) -> dict[str, Any]:
        slow = [row for row in data if any(left <= row["t"] <= right for left, right in slow_intervals)]
        normal = [row for row in data if not any(left <= row["t"] <= right for left, right in slow_intervals)]
        return {"samples": len(data), "util_mean": mean([row["util"] for row in data]),
                "util_zero_fraction": sum(row["util"] == 0 for row in data) / len(data),
                "slow_util_mean": mean([row["util"] for row in slow]), "slow_samples": len(slow),
                "non_slow_util_mean": mean([row["util"] for row in normal]), "non_slow_samples": len(normal),
                "mem_mb_max": max(row["mem_mb"] for row in data)}

    return {"samples": len(inside), "cpu_percent_mean": mean([row["cpu_percent"] for row in inside]),
            "load1_mean": mean([row["load1"] for row in inside]),
            "mem_used_gb_max": max((row["mem_used_gb"] for row in inside), default=None),
            "slow_wall_threshold_s": mean_wall,
            "slow_definition": "稳态完成项 wall_s 高于其均值，采样时刻落在该项运行区间",
            "gpus": {str(index): gpu_summary(data) for index, data in sorted(per_gpu.items())}}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _tasks(env: str) -> tuple[str, ...]:
    names = set(env.split(",")) if env != "all" else set(TASK_ORDER)
    if not names or not names <= set(TASK_ORDER):
        raise ValueError(f"未知任务：{env}")
    return tuple(task for task in TASK_ORDER if task in names)


def _command(cell: Cell, output: Path, env: str, episodes: int, difficulty: str,
             difficulty_cycle: str | None, episode_start: int, max_attempts: int,
             affinity: str) -> list[str]:
    command = [sys.executable, str(GENERATOR), "--output-dir", str(output), "--env", env,
               "--episodes", str(episodes), "--episode-start", str(episode_start),
               "--gpus", cell.gpus, "--workers", str(cell.workers),
               "--max-attempts", str(max_attempts), "--affinity", affinity, "--stop-on-pool-crash"]
    command.extend(["--difficulty-cycle", difficulty_cycle] if difficulty_cycle else ["--difficulty", difficulty])
    if not cell.limit_threads:
        command.append("--no-limit-threads")
    return command


def run_cell(cell: Cell, root: Path, env: str, episodes: int, difficulty: str, keep: bool,
             *, difficulty_cycle: str | None = None, episode_start: int = 0,
             max_attempts: int = 100, affinity: str = "per-gpu", mem_guard_gb: float = 40,
             timeout_s: float = 5400) -> dict[str, Any]:
    output = root / cell.name
    # exclusive mkdir 保留已有证据，绝不删除已有整档目录。
    output.mkdir(parents=True, exist_ok=False)
    command = _command(cell, output, env, episodes, difficulty, difficulty_cycle,
                       episode_start, max_attempts, affinity)
    print(f"档 {cell.name} 起跑 workers={cell.workers} gpus={cell.gpus}", flush=True)
    sampler = ResourceSampler(cell.gpus)
    started = time.monotonic()
    aborted_by = None
    termination = None
    def interrupt(signum: int, _frame: Any) -> None:
        nonlocal aborted_by
        aborted_by = f"signal:{signal.Signals(signum).name}"

    previous_handlers = {}
    try:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            previous_handlers[signum] = signal.signal(signum, interrupt)
        process = subprocess.Popen(command, cwd=str(REPO_ROOT), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1,
                                   start_new_session=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})

        def tee() -> None:
            assert process.stdout is not None
            with (output / "generate.log").open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end="", flush=True)

        log_thread = threading.Thread(target=tee, daemon=True)
        log_thread.start()
        try:
            sampler.start(process.pid)
            while process.poll() is None:
                if not aborted_by and time.monotonic() - started >= timeout_s:
                    aborted_by = "timeout"
                elif not aborted_by and psutil.virtual_memory().available / 2**30 < mem_guard_gb:
                    aborted_by = "mem_guard"
                if aborted_by:
                    print(f"档 {cell.name} aborted_by={aborted_by}", flush=True)
                    termination = terminate_group(process)
                    break
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode == 3 and not aborted_by:
                aborted_by = "pool_crash"
            # 父进程先退出也须收掉进程组里尚存的 worker。
            if termination is None:
                termination = terminate_group(process)
        finally:
            if process.poll() is None or _group_processes(process.pid):
                terminate_group(process)
            sampler.stop()
            log_thread.join(timeout=5)
        elapsed = time.monotonic() - started
        parse_error = None
        try:
            results = _read_jsonl(output / "episode_results.jsonl")
        except json.JSONDecodeError as exc:
            if not aborted_by:
                raise
            # 中止后的坏尾行仍保留原字节；整份记录不再用于计数或测速。
            results = []
            parse_error = {"file": str(output / "episode_results.jsonl"),
                           "message": str(exc), "line": exc.lineno, "column": exc.colno,
                           "position": exc.pos}
            print(f"档 {cell.name} 结果解析失败 aborted_by={aborted_by} parse_error={parse_error}", flush=True)
        generated = json.loads((output / "run_summary.json").read_text(encoding="utf-8")) if (output / "run_summary.json").exists() else {}
        if generated.get("stopped_by") and not aborted_by:
            aborted_by = generated["stopped_by"]
        success = sum(bool(item.get("ok")) for item in results)
        requested = len(_tasks(env)) * episodes
        complete = (process.returncode == 0 and not aborted_by and not parse_error and success == requested
                    and generated.get("requested_count") == requested
                    and generated.get("success_count") == requested
                    and generated.get("exhausted_count") == 0)
        steady = _steady_window(results, cell.workers)
        summary = {"cell": cell.name, "workers": cell.workers, "gpus": cell.gpus,
                   "limit_threads": cell.limit_threads, "returncode": process.returncode,
                   "wall_s": elapsed, "attempts": len(results) if not parse_error else None,
                   "success": success if not parse_error else None, "parse_error": parse_error,
                   "requested": requested, "complete": complete, "aborted_by": aborted_by,
                   "stopped_by": generated.get("stopped_by"), "termination": termination,
                   "failed_attempts": len(results) - success if not parse_error else None,
                   "gross_throughput_ep_per_min": success / elapsed * 60 if elapsed > 0 and not parse_error else None,
                   "steady": steady,
                   "tiers_completed": sorted({item.get("difficulty") for item in results if item.get("ok") and item.get("difficulty")}),
                   "resources": _resource_summary(sampler.rows, steady.get("t_start"), steady.get("t_end"), sampler.gpu_rows, results),
                   "peak_worker_rss_mb": max([sampler.peak_worker_rss_mb, generated.get("peak_rss_mb") or 0,
                                              *(item.get("peak_rss_mb") or 0 for item in results)]),
                   "gpu_peaks": {gpu: {"mem_mb": max((row["mem_mb"] for row in sampler.gpu_rows if str(row["index"]) == gpu), default=0),
                                       "total_mb": min((row["total_mb"] for row in sampler.gpu_rows if str(row["index"]) == gpu), default=0)}
                                 for gpu in cell.gpu_ids}}
        _write_json(output / "resource_samples.json", {"cpu_memory": sampler.rows, "gpus": sampler.gpu_rows})
        if not keep:
            for name in ("hdf5_files", "videos"):
                target = output / name
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
    # 尾部写资源或清理产物时也可能叫停；恢复原信号语义后再锁定最终结果。
    summary["aborted_by"] = aborted_by
    summary["complete"] = summary["complete"] and not aborted_by
    _write_json(output / "cell_summary.json", summary)
    print(f"档 {cell.name} 完成 complete={summary['complete']} aborted_by={aborted_by} 稳态吞吐={steady.get('throughput_ep_per_min')}", flush=True)
    return summary


def memory_admitted(cell: Cell, probe: dict[str, Any], available_gb: float,
                    margin: float = 1.2, guard_gb: float = 40) -> bool:
    return (cell.workers * probe["rss_gb"] * margin + guard_gb <= available_gb
            and cell.workers / len(cell.gpu_ids) * probe["vram_gb"] * margin <= probe["gpu_gb"])


def choose_best(summaries: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [item for item in summaries if item.get("complete")
                and item["requested"] >= 3 * item["workers"]
                and set(MIXED_CYCLE) <= set(item.get("tiers_completed", []))
                and item.get("steady", {}).get("trimmed")
                and (item["steady"].get("throughput_ep_per_min") or 0) > 0]
    if not eligible:
        return None
    peak = max(item["steady"]["throughput_ep_per_min"] for item in eligible)
    return min((item for item in eligible if item["steady"]["throughput_ep_per_min"] >= peak * 0.97),
               key=lambda item: item["workers"])


def run_ladder(cells: Sequence[Cell], root: Path, probe: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
    summaries = []
    for cell in cells:
        if cell.workers == 48:
            summaries.append({"cell": cell.name, "workers": cell.workers, "gpus": cell.gpus, "skipped_by": "user_skip_48"})
            continue
        available = psutil.virtual_memory().available / 2**30
        if not memory_admitted(cell, probe, available, kwargs["mem_margin"], kwargs["mem_guard_gb"]):
            summaries.append({"cell": cell.name, "workers": cell.workers, "gpus": cell.gpus, "skipped_by": "mem_budget"})
            print(f"档 {cell.name} skipped_by=mem_budget mem_avail_gb={available}", flush=True)
            continue
        call_args = {key: value for key, value in kwargs.items() if key != "mem_margin"}
        summary = run_cell(cell, root, **call_args)
        summaries.append(summary)
        if summary.get("aborted_by") or not summary["complete"] or not summary["steady"].get("throughput_ep_per_min"):
            break
    return summaries


def _markdown(summaries: Sequence[dict[str, Any]], context: dict[str, Any]) -> str:
    lines = ["# 并行度标定结果", "", f"- 主机：{context['cpu_count']} 核；可用内存 {context['mem_avail_gb']:.2f} GB",
             "- 吞吐剔除首尾各 W 条完成事件；无有效窗口不选冠军。",
             "- GPU 每 500 毫秒由一个持久进程采相关卡；正式起跑前须验证监控开销。",
             "- 慢步为稳态完成项 wall_s 高于均值；慢步采样覆盖其运行区间，并发区间可以重叠。", "",
             "| 档 | workers | GPU | 状态 | 稳态吞吐(ep/min) | CPU 均值 | GPU 均值／零占比／慢步均值／非慢步均值 |",
             "| --- | ---: | --- | --- | ---: | ---: | --- |"]
    for item in summaries:
        resources = item.get("resources", {})
        gpu_text = "；".join(f"{index}: {gpu['util_mean']}／{gpu['util_zero_fraction']}／{gpu['slow_util_mean']}／{gpu['non_slow_util_mean']}"
                            for index, gpu in resources.get("gpus", {}).items()) or "无稳态采样"
        status = item.get("skipped_by") or item.get("aborted_by") or ("完成" if item.get("complete") else "未完成")
        lines.append(f"| {item['cell']} | {item['workers']} | {item['gpus']} | {status} | {item.get('steady', {}).get('throughput_ep_per_min')} | {resources.get('cpu_percent_mean')} | {gpu_text} |")
    lines.extend(["", context["mem_probe_line"], "", context["calib_line"], ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="最重档探针与多卡并行度阶梯")
    parser.add_argument("--root", required=True)
    parser.add_argument("--env", default="all")
    parser.add_argument("--episodes", type=int, default=24)
    parser.add_argument("--episode-start", type=int, default=0)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--difficulty", default=None)
    modes.add_argument("--difficulty-cycle", default=None)
    parser.add_argument("--max-attempts", type=int, default=100)
    parser.add_argument("--affinity", choices=("none", "per-gpu"), default="per-gpu")
    parser.add_argument("--cells", default=DEFAULT_CELLS)
    parser.add_argument("--probe", default="P8:8:0:on")
    parser.add_argument("--probe-env", default=PROBE_ENV)
    parser.add_argument("--probe-episode-start", type=int, default=6)
    parser.add_argument("--probe-episodes", type=int, default=2)
    parser.add_argument("--mem-guard-gb", type=float, default=40)
    parser.add_argument("--mem-margin", type=float, default=1.2)
    parser.add_argument("--cell-timeout-min", type=float, default=90)
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args(argv)
    cells = parse_cells(args.cells)
    probes = parse_cells(args.probe)
    if len(probes) != 1 or len(probes[0].gpu_ids) != 1 or probes[0].workers != 8:
        parser.error("探针必须是单卡 8 worker")
    if args.episodes <= 0 or args.episode_start < 0 or args.probe_episode_start < 0 or args.probe_episodes <= 0:
        parser.error("episode 数必须为正数，起点不得为负数")
    if args.max_attempts != 100:
        parser.error("本轮测速按已批口径 max-attempts=100")
    if args.mem_guard_gb <= 0 or args.mem_margin <= 0 or args.cell_timeout_min <= 0:
        parser.error("内存参数与单档时间必须为正数")
    requested = len(_tasks(args.env)) * args.episodes
    if any(requested < 3 * cell.workers for cell in cells if cell.workers != 48):
        parser.error("测速每档作业数必须不少于 3×workers")
    root = Path(args.root).resolve()
    if any((root / cell.name).exists() for cell in [*probes, *cells]):
        parser.error("档目录已存在，保留原有证据并拒绝起跑")
    root.mkdir(parents=True, exist_ok=True)
    context = {"env": args.env, "episodes": args.episodes, "difficulty_cycle": args.difficulty_cycle,
               "cpu_count": psutil.cpu_count(), "mem_avail_gb": psutil.virtual_memory().available / 2**30}
    common = {"difficulty": args.difficulty or "211", "keep": args.keep_artifacts,
              "difficulty_cycle": args.difficulty_cycle, "max_attempts": args.max_attempts,
              "affinity": args.affinity, "mem_guard_gb": args.mem_guard_gb}
    measured = run_cell(probes[0], root, args.probe_env, args.probe_episodes,
                        episode_start=args.probe_episode_start, timeout_s=1800, **common)
    gpu = measured["gpu_peaks"][probes[0].gpu_ids[0]]
    probe = {"rss_gb": measured["peak_worker_rss_mb"] / 1024,
             "vram_gb": gpu["mem_mb"] / 1024 / probes[0].workers,
             "gpu_gb": gpu["total_mb"] / 1024, "mem_avail_gb": context["mem_avail_gb"]}
    expected_probe = len(_tasks(args.probe_env)) * args.probe_episodes
    probe_ok = (measured["complete"] and expected_probe == 16 and probe["rss_gb"] > 0
                and probe["vram_gb"] > 0 and probe["gpu_gb"] > 0
                and set(measured["tiers_completed"]) == {"xhard18", "xhard20"})
    context["mem_probe_line"] = (f"MEM_PROBE={'PASS' if probe_ok else 'FAIL'} peak_rss_gb={probe['rss_gb']} "
                                 f"peak_vram_gb={probe['vram_gb']} mem_avail_gb={probe['mem_avail_gb']}")
    print(context["mem_probe_line"], flush=True)
    summaries = run_ladder(cells, root, probe, env=args.env, episodes=args.episodes,
                           episode_start=args.episode_start, timeout_s=args.cell_timeout_min * 60,
                           mem_margin=args.mem_margin, **common) if probe_ok else []
    best = choose_best(summaries)
    l32 = next((item for item in summaries if item["workers"] == 32), None)
    passed = bool(probe_ok and best and l32 and choose_best([l32])
                  and not any(item.get("parse_error") or str(item.get("aborted_by", "")).startswith("signal:")
                              for item in summaries))
    skipped = ",".join(item["cell"] for item in summaries if item.get("skipped_by")) or "none"
    crashed = next((item["workers"] for item in summaries if item.get("aborted_by") == "pool_crash"), "none")
    context["calib_line"] = (f"CALIB={'PASS' if passed else 'FAIL'} probe_rss_gb={probe['rss_gb']} probe_vram_gb={probe['vram_gb']} "
                              f"cells_run={sum('returncode' in item for item in summaries)} skipped={skipped} "
                              f"best_workers={best['workers'] if best else 'none'} crashed_at={crashed}")
    context["best_gpus"] = best["gpus"] if best else None
    _write_json(root / "calibration.json", {"context": context, "probe": measured, "probe_budget": probe, "cells": summaries})
    (root / "calibration.md").write_text(_markdown(summaries, context), encoding="utf-8")
    print(context["calib_line"], flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
