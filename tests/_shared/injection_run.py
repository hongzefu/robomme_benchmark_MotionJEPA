"""步骤 2～5 的执行编排（NEW_VALUE_INJECTION_TEST_PLAN 第五节）。

* ``calibration``：先用 16 条固定样本建立串行参考（``S0a``／``S0b`` 两遍），
  再按每卡 worker 数一路向上探，用同一份 120 条清单测吞吐。
* ``feasibility``：用选出的档，一次调用传 11 组清单跑每组 episode 0～29 共 330 条。

**档位选择的口径（2026-09-10 用户决定）**：不设 RSS／``free``／swap 三条软守卫，
直接一路往上加 worker，**实测到 OOM 或超时为止**，用最后一个不 OOM 的档做全量。
资源数字照样采样、照样留档，但只作记录，不作中止条件。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 四个校准组：三个 hard 加 VideoRepick medium（VideoRepick 没有 hard）。
CALIBRATION_GROUPS: tuple[tuple[str, str], ...] = (
    ("BinFill", "hard"),
    ("RouteStick", "hard"),
    ("VideoUnmaskSwap", "hard"),
    ("VideoRepick", "medium"),
)
#: 串行参考的固定样本：四任务各 episode 0～3，共 16 条。
SERIAL_EPISODES = tuple(range(4))
#: 负载阶梯清单：四个校准组各 episode 0～29，共 120 条。
LOAD_EPISODES = tuple(range(30))
#: 实跑范围：每组 episode 0～29。
FEASIBILITY_EPISODES = tuple(range(30))
#: 每卡 worker 的档位阶梯，一路向上探到 OOM 或超时为止。
WORKER_TIERS = (12, 16, 20, 24, 28, 32)
#: 单档墙钟上限（秒）。超时按该档不可用处理，与 OOM 同等级。
TIER_TIMEOUT_S = 3600

#: 七类互斥的最终任务结果。
OUTCOME_PASS = "通过"
OUTCOME_SPEC_REJECT = "规格拒绝"
OUTCOME_COLLISION = "碰撞拒绝"
OUTCOME_BINDING = "实际对象/动作不符"
OUTCOME_PLAN = "规划失败"
OUTCOME_TIMEOUT = "超时"
OUTCOME_NOT_RUN = "未运行"


def classify_outcome(record: dict[str, Any]) -> str:
    """把 worker 返回的一条记录翻成七类互斥的任务结果。

    ⚠ 执行状态不是 ``completed``（代码错误、基础设施错误）时任务结果一律记「未运行」
    并注明原因——系统错误不能冒充物理不可行。
    """
    if record.get("ok"):
        return OUTCOME_PASS
    error_type = str(record.get("error_type") or "")
    failure_class = str(record.get("failure_class") or "")
    if error_type == "EpisodeSpecError":
        return OUTCOME_SPEC_REJECT
    if error_type == "BinCollisionError":
        return OUTCOME_COLLISION
    if error_type == "SpecBindingError":
        return OUTCOME_BINDING
    if error_type == "FailsafeTimeout":
        return OUTCOME_TIMEOUT
    if failure_class in ("code", "infra"):
        return OUTCOME_NOT_RUN
    # 余下的任务性失败（规划耗尽、螺旋规划失败、场景生成失败、环境报告失败）归规划失败；
    # 原始 error_type 在结果行里原样保留，便于事后细分。
    return OUTCOME_PLAN


def execution_state(record: dict[str, Any]) -> str:
    """执行状态四态：completed / code_error / infra_error / timeout。"""
    if record.get("ok"):
        return "completed"
    failure_class = str(record.get("failure_class") or "")
    if str(record.get("error_type") or "") == "FailsafeTimeout":
        return "timeout"
    if failure_class == "code":
        return "code_error"
    if failure_class == "infra":
        return "infra_error"
    return "completed"  # 任务性失败：确实跑完了，只是任务没成功


def write_manifest(path: Path, groups: Sequence[tuple[str, str]], episodes: Sequence[int], specs_root: Path, note: str) -> Path:
    """写一份混跑清单；``spec_path`` 相对清单文件所在目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_version": 1,
        "note": note,
        "groups": [
            {
                "task": task,
                "difficulty": difficulty,
                "spec_path": os.path.relpath(specs_root / task / f"{difficulty}.json", path.parent),
                "episodes": list(episodes),
            }
            for task, difficulty in groups
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _sample_resources() -> dict[str, Any]:
    """只读采样：可用内存、swap、磁盘余量。记录用，不作守卫。"""
    payload: dict[str, Any] = {}
    try:
        meminfo = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            meminfo[key] = int(rest.strip().split()[0])
        payload["mem_available_gb"] = round(meminfo.get("MemAvailable", 0) / 1024 / 1024, 1)
        payload["swap_used_gb"] = round((meminfo.get("SwapTotal", 0) - meminfo.get("SwapFree", 0)) / 1024 / 1024, 1)
    except OSError:
        pass
    try:
        usage = shutil.disk_usage(REPO_ROOT)
        payload["disk_free_gb"] = round(usage.free / 1024**3, 1)
    except OSError:
        pass
    return payload


def invoke_generator(
    *,
    output_dir: Path,
    manifest: Path,
    gpus: str,
    workers: int,
    log_path: Path,
    sampling_config: Path | None,
    timeout_s: int = TIER_TIMEOUT_S,
) -> dict[str, Any]:
    """调一次生产入口跑完整份清单，记录完整命令、退出码、墙钟与资源采样。

    走 subprocess 而不是同进程调用：命令可原样复现、退出码明确、进程池崩溃不会带塌编排。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "generate_dataset_newseed.py"),
        "--output-dir", str(output_dir),
        "--gpus", gpus,
        "--workers", str(workers),
        "--layout", "train",
        "--max-attempts", "1",
        "--max-tasks-per-child", "8",
        "--affinity", "per-gpu",
        "--episode-specs", str(manifest),
    ]
    if sampling_config is not None:
        command += ["--sampling-config", str(sampling_config)]

    before = _sample_resources()
    started = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8") as sink:
        try:
            completed = subprocess.run(
                command, stdout=sink, stderr=subprocess.STDOUT, timeout=timeout_s,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}, cwd=str(REPO_ROOT),
            )
            code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            code = -1
    elapsed = time.monotonic() - started
    after = _sample_resources()

    summary_path = output_dir / "run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    rows = read_result_rows(output_dir)
    return {
        "command": command,
        "exit_code": code,
        "timed_out": timed_out,
        "wall_s": round(elapsed, 1),
        "log": str(log_path),
        "output_dir": str(output_dir),
        "summary": summary,
        "rows": rows,
        "resources_before": before,
        "resources_after": after,
    }


def read_result_rows(output_dir: Path) -> list[dict[str, Any]]:
    """从 ``episode_results.jsonl`` 读**最后一次** attempt 的结果，逐条翻成三字段。

    三个字段互不覆盖：执行状态、任务结果、视频状态。视频判定失败不改变任务结果。
    """
    path = output_dir / "episode_results.jsonl"
    if not path.is_file():
        return []
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = (record["task"], int(record["episode"]))
        if key not in latest or record.get("attempt", 0) >= latest[key].get("attempt", 0):
            latest[key] = record
    rows = []
    for (task, episode), record in sorted(latest.items()):
        video = record.get("video") or {}
        checks = record.get("runtime_checks") or []
        rejections = [item["rejection"] for item in checks if item.get("rejection")]
        rows.append(
            {
                # 运行时检查的摘要：完整记录留在 episode_results.jsonl 里，这里只放可统计的部分
                "runtime_checks_total": len(checks),
                "runtime_check_kinds": sorted({str(item.get("kind")) for item in checks}),
                "runtime_rejections": rejections,
                "injection_bound": bool(record.get("injection_evidence")),
                "task": task,
                "difficulty": record.get("difficulty"),
                "episode": episode,
                "seed": record.get("seed"),
                "attempt": record.get("attempt"),
                "execution_state": execution_state(record),
                "outcome": classify_outcome(record),
                "error_type": record.get("error_type"),
                "error": (record.get("error") or "")[:400],
                "video_status": video.get("status", "unrecorded"),
                "video_frames": video.get("frames"),
                "video_frames_expected": video.get("frames_expected"),
                "video_path": video.get("path"),
                "video_sha256": video.get("sha256"),
                "video_reason": video.get("reason"),
                "wall_s": record.get("wall_s"),
                "peak_rss_mb": record.get("peak_rss_mb"),
            }
        )
    return rows


def tier_is_unusable(result: dict[str, Any]) -> tuple[bool, str]:
    """判断某一档是否不可用：只认 OOM／进程池崩溃／超时这三种硬失败。

    ⚠ 任务性失败（规划失败、碰撞拒绝等）**不算**该档不可用——那是样本本身的问题，
    与并发规模无关；把它们算进去会误伤档位。
    """
    if result["timed_out"]:
        return True, f"该档墙钟超过 {TIER_TIMEOUT_S} 秒上限"
    hits = [row for row in result["rows"] if _is_resource_failure(row)]
    if hits:
        kinds = sorted({row["error_type"] or "?" for row in hits})
        return True, f"{len(hits)} 条资源性失败（{kinds}），按 OOM／池崩溃处理"
    return False, ""


#: OOM 的三种露头方式，缺一不可：
#: * 主机内存被 OOM killer 杀掉 worker → 池崩溃 → ``infra_error``；
#: * 显式的 ``MemoryError``；
#: * **CUDA 显存不足** —— 它在 worker 里抛 ``torch.cuda.OutOfMemoryError``／``RuntimeError``，
#:   不在 ``retryable`` 名单里，于是被记成 ``code_error``。⚠ 只看 ``infra_error`` 会漏掉
#:   这一类，而档位阶梯恰恰就是靠显存 OOM 封顶的。
_OOM_ERROR_TYPES = ("BrokenProcessPool", "MemoryError", "OutOfMemoryError", "CudaError")
_OOM_TEXT_MARKERS = ("out of memory", "outofmemory", "cuda error", "cudaerrormemoryallocation",
                     "failed to allocate", "no kernel image", "cannot allocate memory")


def _is_resource_failure(row: dict[str, Any]) -> bool:
    """这一条是不是资源性失败（该档撑不住），而不是样本自身的任务性失败。"""
    if row.get("execution_state") == "infra_error":
        return True
    error_type = str(row.get("error_type") or "")
    if any(marker in error_type for marker in _OOM_ERROR_TYPES):
        return True
    text = str(row.get("error") or "").lower()
    return any(marker in text for marker in _OOM_TEXT_MARKERS)


def tier_throughput(result: dict[str, Any]) -> tuple[float, int, int]:
    """吞吐 = **成功且视频完整**的条数 ÷ 批次墙钟（分钟）。

    ⚠ 分子只数「成功且视频完整」，同时另报失败数——否则一档跑得快只是因为大量样本
    快速失败，会被误当成加速。
    """
    delivered = sum(1 for row in result["rows"] if row["outcome"] == OUTCOME_PASS and row["video_status"] == "complete")
    failed = sum(1 for row in result["rows"] if row["outcome"] != OUTCOME_PASS)
    minutes = max(result["wall_s"], 1e-9) / 60.0
    return delivered / minutes, delivered, failed


# ── 真实并发窗口（PARALLEL_OVERLAP）────────────────────────────────────────
def solve_windows(output_dir: Path) -> list[dict[str, Any]]:
    """每条样本真正在跑 step 的时间窗。

    ⚠ 用 ``solve`` 段而不是整条记录的起止：``make``（建环境、导入）、``reset`` 与
    ``close``（mp4 编码）都可能在多个 worker 之间重叠，但那只是排队与编码重叠，
    **不是真实并发执行**。计划第 5.7 节明确要求「只有排队／导入重叠不算」。
    """
    path = output_dir / "episode_results.jsonl"
    if not path.is_file():
        return []
    windows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        phases = record.get("phases") or {}
        bound = record.get("bound") or {}
        started, finished = record.get("started_at"), record.get("finished_at")
        if started is None or finished is None or "solve_s" not in phases:
            continue
        begin = started + float(phases.get("make_s", 0.0)) + float(phases.get("reset_s", 0.0))
        end = begin + float(phases["solve_s"])
        if end <= begin:
            continue
        windows.append(
            {
                "task": record["task"], "episode": record["episode"],
                "pid": bound.get("pid"), "gpu": str(bound.get("gpu")),
                "begin": begin, "end": end,
            }
        )
    return windows


def overlap_report(windows: list[dict[str, Any]], gpus: Sequence[str], workers_per_gpu: int) -> dict[str, Any]:
    """扫描时间线算并发峰值：总体不同 PID 峰值、每卡峰值、双卡共同窗口时长。"""
    events: list[tuple[float, int, dict[str, Any]]] = []
    for window in windows:
        events.append((window["begin"], 1, window))
        events.append((window["end"], -1, window))
    # ⚠ 同一时刻先处理结束（-1）再处理开始（+1）：两条首尾相接的窗口（[0,10] 与 [10,20]）
    # 是串行执行，不是并发。反过来排会在交界处凭空多出一个峰值，把串行误判成真并发。
    events.sort(key=lambda item: (item[0], item[1]))

    live: dict[int, dict[str, Any]] = {}
    peak_distinct_pids = 0
    peak_per_gpu = {gpu: 0 for gpu in gpus}
    both_busy_seconds = 0.0
    previous = None
    counter = 0
    for timestamp, delta, window in events:
        if previous is not None and timestamp > previous:
            by_gpu = {gpu: sum(1 for item in live.values() if item["gpu"] == gpu) for gpu in gpus}
            if len(gpus) > 1 and all(by_gpu.get(gpu, 0) > 0 for gpu in gpus):
                both_busy_seconds += timestamp - previous
        previous = timestamp
        if delta > 0:
            counter += 1
            live[counter] = window
            window["_key"] = counter
        else:
            live.pop(window.get("_key", -1), None)
        distinct = len({item["pid"] for item in live.values() if item["pid"] is not None})
        peak_distinct_pids = max(peak_distinct_pids, distinct)
        for gpu in gpus:
            count = len({item["pid"] for item in live.values() if item["gpu"] == gpu and item["pid"] is not None})
            peak_per_gpu[gpu] = max(peak_per_gpu[gpu], count)

    total_workers = workers_per_gpu * len(gpus)
    # 单卡时「双卡共同窗口 > 0」这条不适用，只验不同 PID 峰值达到 worker 数；
    # 多卡时才加上每卡峰值与双卡共同窗口两条。
    passed = (
        peak_distinct_pids >= total_workers
        and all(peak_per_gpu[gpu] >= workers_per_gpu for gpu in gpus)
        and (len(gpus) == 1 or both_busy_seconds > 0)
    )
    return {
        "peak_distinct_pids": peak_distinct_pids,
        "peak_per_gpu": peak_per_gpu,
        "both_busy_seconds": round(both_busy_seconds, 3),
        "workers_per_gpu": workers_per_gpu,
        "total_workers": total_workers,
        "samples": len(windows),
        "passed": passed,
    }
