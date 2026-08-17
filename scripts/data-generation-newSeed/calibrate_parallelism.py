#!/usr/bin/env python3
"""并行度标定：串行跑若干档配置，采资源指标，出吞吐对比表。

回答三个问题：
  (a) 瓶颈到底在 CPU、GPU 还是 IO
  (b) 把每个 worker 的 CPU 线程压到 1 能带来多少提升
  (c) 最优 workers 数是多少（含是否值得超订阅到物理核数以上）

吞吐用**稳态吞吐**而不是总耗时：进程池的行为是「填满 → 稳态 → 排空」，
前 W 条完成事件受启动预热污染、后 W 条受排空长尾污染，都要丢掉。
"""

from __future__ import annotations

import argparse
import json
import shutil
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
GENERATOR = SCRIPT_DIR / "generate_dataset_newseed.py"
REPO_ROOT = SCRIPT_DIR.parents[1]

# 默认三档：A 是历史基线（不限线程、单卡），B 加线程限制并打满物理核，
# C 与 B 的 CPU 负载完全相同、只把渲染摊到两张卡 —— C≈B 即证明 GPU 不是瓶颈。
DEFAULT_CELLS = "A:20:0:off;B:32:0:on;C:32:0,1:on"


@dataclass(frozen=True)
class Cell:
    name: str
    workers: int
    gpus: str
    limit_threads: bool


def parse_cells(text: str) -> list[Cell]:
    """档位之间用分号分隔 —— gpus 字段本身可能是 "0,1"，不能用逗号做分隔符。"""
    cells: list[Cell] = []
    for item in text.split(";"):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 4:
            raise ValueError(f"档位格式应为 name:workers:gpus:on|off，当前为 {item!r}")
        name, workers, gpus, limit = parts
        cells.append(
            Cell(
                name=name.strip(),
                workers=int(workers),
                gpus=gpus.strip(),
                limit_threads=limit.strip().lower() in ("on", "1", "true", "yes"),
            )
        )
    if not cells:
        raise ValueError("--cells 至少要有一个档位")
    return cells


class ResourceSampler:
    """后台按固定间隔采 CPU / 内存 / GPU 指标。"""

    def __init__(self, interval: float = 2.0) -> None:
        self.interval = interval
        self.rows: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _gpu(self) -> list[dict[str, float]]:
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,utilization.gpu,memory.used,power.draw",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except Exception:
            return []
        gpus = []
        for line in out.strip().splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) < 4:
                continue
            try:
                gpus.append(
                    {
                        "index": int(fields[0]),
                        "util": float(fields[1]),
                        "mem_mb": float(fields[2]),
                        "power_w": float(fields[3]),
                    }
                )
            except ValueError:
                continue
        return gpus

    def _loop(self) -> None:
        psutil.cpu_percent(interval=None)
        while not self._stop.wait(self.interval):
            memory = psutil.virtual_memory()
            try:
                load1 = psutil.getloadavg()[0]
            except OSError:
                load1 = float("nan")
            self.rows.append(
                {
                    "t": time.time(),
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "load1": load1,
                    "mem_used_gb": round((memory.total - memory.available) / 2**30, 2),
                    "gpus": self._gpu(),
                }
            )

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)


def _steady_window(results: Sequence[dict[str, Any]], workers: int) -> dict[str, Any]:
    """丢掉前 W 和后 W 条完成事件，用中间那段算稳态吞吐。"""
    done = sorted(
        (item for item in results if item.get("ok") and item.get("finished_at")),
        key=lambda item: float(item["finished_at"]),
    )
    if len(done) <= 2 * workers + 1:
        # 样本不足以剔除首尾，退化成全窗口
        window = done
        trimmed = False
    else:
        window = done[workers:-workers]
        trimmed = True
    if len(window) < 2:
        return {"episodes": len(window), "throughput_ep_per_min": None, "trimmed": trimmed}
    span = float(window[-1]["finished_at"]) - float(window[0]["finished_at"])
    return {
        "episodes": len(window),
        "span_s": round(span, 1),
        "throughput_ep_per_min": round(len(window) / span * 60, 2) if span > 0 else None,
        "mean_wall_s": round(statistics.mean(float(item["wall_s"]) for item in window), 1),
        "trimmed": trimmed,
        "t_start": float(window[0]["finished_at"]),
        "t_end": float(window[-1]["finished_at"]),
    }


def _resource_summary(
    rows: Sequence[dict[str, Any]], start: float | None, end: float | None
) -> dict[str, Any]:
    inside = [
        row
        for row in rows
        if start is None or end is None or start <= row["t"] <= end
    ] or list(rows)
    if not inside:
        return {}

    def median(values: Sequence[float]) -> float | None:
        clean = [value for value in values if value == value]  # 去 nan
        return round(statistics.median(clean), 1) if clean else None

    per_gpu: dict[int, dict[str, Any]] = {}
    for row in inside:
        for gpu in row.get("gpus", []):
            bucket = per_gpu.setdefault(gpu["index"], {"util": [], "mem_mb": [], "power_w": []})
            bucket["util"].append(gpu["util"])
            bucket["mem_mb"].append(gpu["mem_mb"])
            bucket["power_w"].append(gpu["power_w"])
    return {
        "samples": len(inside),
        "cpu_percent_median": median([row["cpu_percent"] for row in inside]),
        "cpu_percent_max": median([max(row["cpu_percent"] for row in inside)]),
        "load1_median": median([row["load1"] for row in inside]),
        "mem_used_gb_max": max(row["mem_used_gb"] for row in inside),
        "gpus": {
            str(index): {
                "util_median": median(data["util"]),
                "util_max": max(data["util"]),
                "mem_mb_max": max(data["mem_mb"]),
                "power_w_median": median(data["power_w"]),
                "power_w_max": max(data["power_w"]),
            }
            for index, data in sorted(per_gpu.items())
        },
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    results = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results


def run_cell(
    cell: Cell,
    root: Path,
    env: str,
    episodes: int,
    difficulty: str,
    keep: bool,
) -> dict[str, Any]:
    output = root / cell.name
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    command = [
        sys.executable,
        str(GENERATOR),
        "--output-dir",
        str(output),
        "--env",
        env,
        "--episodes",
        str(episodes),
        "--difficulty",
        difficulty,
        "--gpus",
        cell.gpus,
        "--workers",
        str(cell.workers),
    ]
    if not cell.limit_threads:
        command.append("--no-limit-threads")

    print(f"\n=== 档 {cell.name}: workers={cell.workers} gpus={cell.gpus} "
          f"limit_threads={'on' if cell.limit_threads else 'off'} ===", flush=True)
    sampler = ResourceSampler()
    sampler.start()
    started = time.monotonic()
    process = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        stdout=(output / "generate.log").open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    elapsed = time.monotonic() - started
    sampler.stop()

    results = _read_jsonl(output / "episode_results.jsonl")
    steady = _steady_window(results, cell.workers)
    resources = _resource_summary(sampler.rows, steady.get("t_start"), steady.get("t_end"))
    success = sum(1 for item in results if item.get("ok"))
    summary = {
        "cell": cell.name,
        "workers": cell.workers,
        "gpus": cell.gpus,
        "limit_threads": cell.limit_threads,
        "returncode": process.returncode,
        "wall_s": round(elapsed, 1),
        "attempts": len(results),
        "success": success,
        "failed_attempts": len(results) - success,
        "gross_throughput_ep_per_min": round(success / (elapsed / 60), 2) if elapsed > 0 else None,
        "steady": steady,
        "resources": resources,
        "peak_worker_rss_mb": max(
            (item.get("peak_rss_mb") or 0 for item in results), default=0
        ),
    }
    (output / "cell_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "resource_samples.json").write_text(
        json.dumps(sampler.rows, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"档 {cell.name} 完成：wall={summary['wall_s']}s 成功={success} "
        f"稳态吞吐={steady.get('throughput_ep_per_min')} ep/min",
        flush=True,
    )
    if not keep:
        for name in ("hdf5_files", "videos"):
            shutil.rmtree(output / name, ignore_errors=True)
    return summary


def _markdown(summaries: Sequence[dict[str, Any]], context: dict[str, Any]) -> str:
    lines = ["# 并行度标定结果\n"]
    lines.append(
        f"- 标定集：`{context['env']}` 的前 {context['episodes']} 个 episode，难度比例 {context['difficulty']}\n"
        f"- 主机：{context['cpu_count']} 核 / {context['mem_gb']} GB 内存\n"
        f"- 吞吐口径：稳态吞吐（丢掉前 W 与后 W 条完成事件，剔除填充与排空的尾部效应）\n"
    )
    lines.append("\n## 吞吐对比\n")
    lines.append(
        "| 档 | workers | GPU | 限线程 | 总耗时(s) | 成功 | 失败 attempt | "
        "稳态吞吐(ep/min) | 稳态样本 | 单条均时(s) | worker 峰值 RSS(MB) |"
    )
    lines.append("| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in summaries:
        steady = item.get("steady", {})
        lines.append(
            f"| {item['cell']} | {item['workers']} | {item['gpus']} | "
            f"{'on' if item['limit_threads'] else 'off'} | {item['wall_s']} | {item['success']} | "
            f"{item['failed_attempts']} | {steady.get('throughput_ep_per_min')} | "
            f"{steady.get('episodes')} | {steady.get('mean_wall_s')} | {item['peak_worker_rss_mb']} |"
        )

    lines.append("\n## 资源占用（稳态窗口内）\n")
    lines.append("| 档 | CPU% 中位 | load1 中位 | 内存峰值(GB) | GPU util 中位 | GPU 功耗中位(W) | GPU 显存峰值(MB) |")
    lines.append("| --- | ---: | ---: | ---: | --- | --- | --- |")
    for item in summaries:
        resources = item.get("resources", {})
        gpus = resources.get("gpus", {})
        util = " / ".join(f"{index}:{data['util_median']}" for index, data in gpus.items()) or "—"
        power = " / ".join(f"{index}:{data['power_w_median']}" for index, data in gpus.items()) or "—"
        memory = " / ".join(f"{index}:{data['mem_mb_max']:.0f}" for index, data in gpus.items()) or "—"
        lines.append(
            f"| {item['cell']} | {resources.get('cpu_percent_median')} | "
            f"{resources.get('load1_median')} | {resources.get('mem_used_gb_max')} | "
            f"{util} | {power} | {memory} |"
        )

    lines.append(
        "\n## 判据\n\n"
        "- **CPU 瓶颈**：CPU% 接近 100、load1 明显高于核数，同时 GPU 功耗低（RTX 6000 Ada 空载约 22-28 W、"
        "TDP 300 W，稳态低于 90 W 就说明卡基本闲着）。注意 `utilization.gpu` 只表示"
        "「有任意 kernel 在跑的时间比例」，不代表占用率，所以功耗才是更可信的判据。\n"
        "- **GPU 瓶颈**：GPU 功耗持续偏高，且双卡档明显优于同 worker 数的单卡档。\n"
        "- **冠军选择**：在全部成功、内存与显存都安全的档里，取稳态吞吐达到最高值 97% 的**最小** workers —— "
        "更小的并发意味着更低的内存峰值、更短的收尾长尾、更小的崩溃爆炸半径。\n"
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="并行度标定：跑多档配置并出吞吐对比表")
    parser.add_argument("--root", required=True, help="标定输出根目录")
    parser.add_argument("--env", default="VideoUnmask", help="标定用的环境（单个或逗号分隔）")
    parser.add_argument("--episodes", type=int, default=64, help="每档跑多少个 episode")
    parser.add_argument("--difficulty", default="211")
    parser.add_argument("--cells", default=DEFAULT_CELLS, help="档位，格式 name:workers:gpus:on|off")
    parser.add_argument("--keep-artifacts", action="store_true", help="保留每档的 h5 与视频（默认删除）")
    args = parser.parse_args(argv)

    cells = parse_cells(args.cells)
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    summaries = [
        run_cell(cell, root, args.env, args.episodes, args.difficulty, args.keep_artifacts)
        for cell in cells
    ]
    context = {
        "env": args.env,
        "episodes": args.episodes,
        "difficulty": args.difficulty,
        "cpu_count": psutil.cpu_count(logical=False) or psutil.cpu_count(),
        "mem_gb": round(psutil.virtual_memory().total / 2**30),
    }
    (root / "calibration.json").write_text(
        json.dumps({"context": context, "cells": summaries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "calibration.md").write_text(_markdown(summaries, context), encoding="utf-8")
    print(f"\n标定完成，报告写入 {root / 'calibration.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
