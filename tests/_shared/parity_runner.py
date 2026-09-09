#!/usr/bin/env python3
"""newtask-v2 三路对拍的实测驱动（测试侧，产品代码不导入）。

按 ``cases.json`` 逐格跑真实生成，每格四次独立进程运行：

* ``A1`` / ``A2``：固定原版，来自 ``artifacts/native-baseline`` 的 detached worktree，
  入口是原路径脚本。跑两次用于 4.0 的原版重复性校准与 ``rrt_fallback_count`` 登记
* ``B``：平铺入口不传 ``--sampling-config``
* ``C``：平铺入口显式传入冻结的原值配置

四路共用同一 ``.venv``（基线与当前 ``uv.lock`` 相同），固定
``--workers 1 --gpus 0 --max-attempts 1 --max-tasks-per-child 8``，
每格固定任务、难度、episode、seed、attempt=0，独立进程串行执行。

观察器由 ``PYTHONPATH`` 里的 sitecustomize 装入每个进程（含 spawn 出来的 worker），
证据落 ``--evidence-root``；生成产物落各自的输出目录，互不复用。

已经成功跑完的运行默认跳过（看输出目录里的 ``run_summary.json``），因此可以中断续跑。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_WORKTREE = REPO_ROOT / "artifacts" / "native-baseline"
# A 路入口是**基线 worktree 内**的原路径（该 worktree 固定在 94449db）；
# 当前工作树的同名目录已在第五步清理中退出，这里的路径不受影响。
BASELINE_ENTRY = "scripts/data-generation-newSeed/generate_dataset_newseed.py"
FLAT_ENTRY = "scripts/generate_dataset_newseed.py"
SAMPLING_CONFIG = "scripts/configs/newtask-v2/native_sampling.json"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

PATHS = ("A1", "A2", "B", "C")


def _observer_env(evidence_root: Path, label: str, record_steps: bool) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["VIRTUAL_ENV"] = str(REPO_ROOT / ".venv")
    env["PYTHONPATH"] = str(REPO_ROOT / "tests" / "_shared" / "parity_sitecustomize")
    env["PARITY_OBSERVER_DIR"] = str(REPO_ROOT / "tests" / "_shared")
    env["PARITY_EVIDENCE_DIR"] = str(evidence_root)
    env["PARITY_LABEL"] = label
    env["PARITY_STEPS"] = "1" if record_steps else "0"
    return env


def _run_one(
    case: dict[str, Any],
    label: str,
    output_root: Path,
    evidence_root: Path,
    record_steps: bool,
    log_dir: Path,
    observer_enabled: bool = True,
) -> dict[str, Any]:
    cell = case["cell"]
    is_baseline = label.startswith("A")
    workdir = BASELINE_WORKTREE if is_baseline else REPO_ROOT
    entry = BASELINE_ENTRY if is_baseline else FLAT_ENTRY
    # 输出目录必须落在各自 REPO_ROOT 之内（生成器的硬约束）
    relative_output = Path("artifacts") / "parity" / output_root.name / cell / label
    absolute_output = workdir / relative_output

    command: list[str] = [
        "uv", "run", "--no-sync", "--project", str(REPO_ROOT), "python",
        str(workdir / entry),
        "--output-dir",
        str(relative_output),
        "--env",
        case["task"],
        "--episodes",
        "1",
        "--episode-start",
        str(case["episode"]),
        "--workers",
        "1",
        "--gpus",
        "0",
        "--layout",
        "train",
        "--difficulty",
        case["difficulty_ratio"],
        "--max-attempts",
        "1",
        "--max-tasks-per-child",
        "8",
    ]
    if label == "C":
        command += ["--sampling-config", SAMPLING_CONFIG]

    summary_path = absolute_output / "run_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("success_count") == 1 and summary.get("exhausted_count") == 0:
            return {
                "cell": cell,
                "label": label,
                "skipped": True,
                "output_dir": str(absolute_output),
                "elapsed_s": summary.get("elapsed_s"),
            }

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{cell}.{label}.log"
    started = time.monotonic()
    child_env = _observer_env(evidence_root, label, record_steps)
    if not observer_enabled:
        child_env = {key: value for key, value in child_env.items() if not key.startswith("PARITY_")}
        child_env.pop("PYTHONPATH", None)
    with log_path.open("w", encoding="utf-8") as sink:
        completed = subprocess.run(
            command,
            cwd=str(workdir),
            env=child_env,
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
    elapsed = round(time.monotonic() - started, 1)

    result: dict[str, Any] = {
        "cell": cell,
        "label": label,
        "skipped": False,
        "returncode": completed.returncode,
        "elapsed_s": elapsed,
        "command": " ".join(command),
        "cwd": str(workdir),
        "output_dir": str(absolute_output),
        "log": str(log_path),
    }
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        result["success_count"] = summary.get("success_count")
        result["exhausted_count"] = summary.get("exhausted_count")
    result["ok"] = completed.returncode == 0 and result.get("success_count") == 1
    return result


def run_matrix(
    cases_path: str | Path,
    output_root: str | Path,
    evidence_root: str | Path,
    log_dir: str | Path,
    only_cells: Sequence[str] | None = None,
    only_paths: Sequence[str] | None = None,
    record_steps: bool = True,
) -> dict[str, Any]:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))["cases"]
    if only_cells:
        cases = [case for case in cases if case["cell"] in set(only_cells)]
    labels = tuple(only_paths) if only_paths else PATHS

    output_root = Path(output_root)
    evidence_root = Path(evidence_root)
    log_dir = Path(log_dir)
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    for case in cases:
        for label in labels:
            result = _run_one(case, label, output_root, evidence_root, record_steps, log_dir)
            results.append(result)
            state = "跳过" if result.get("skipped") else ("成功" if result.get("ok") else "失败")
            print(
                f"[{len(results)}/{len(cases) * len(labels)}] {case['cell']} {label} {state} "
                f"{result.get('elapsed_s')}s",
                flush=True,
            )
    return {
        "cases": [case["cell"] for case in cases],
        "labels": list(labels),
        "results": results,
        "elapsed_s": round(time.monotonic() - started, 1),
        "failed": [item for item in results if not item.get("skipped") and not item.get("ok")],
    }


ENV_CODE = {"BinFill": 4, "VideoUnmaskSwap": 5, "VideoRepick": 9, "RouteStick": 16}


def _binfill_dynamic(seed: int) -> bool:
    """离线预判 BinFill 的 dynamic 分支，不需要仿真（难度不进入 seed）。"""
    import torch

    generator = torch.Generator()
    generator.manual_seed(seed)
    return bool(torch.randint(0, 2, (1,), generator=generator).item())


def scan_replacement(
    case: dict[str, Any],
    candidates: Sequence[int],
    output_root: Path,
    evidence_root: Path,
    log_dir: Path,
) -> dict[str, Any]:
    """原版在该格首次尝试就失败时，按计划另选同格其他 episode 补足。

    只换 episode、不自动换 seed 顶替：seed 仍由原公式按新 episode 号算出，
    attempt 固定 0。受阻的原用例保留记录、不删除。
    """
    tried: list[dict[str, Any]] = []
    for episode in candidates:
        if episode == case["episode"]:
            continue
        seed = ENV_CODE[case["task"]] * 1000 + episode * 100
        if case["task"] == "BinFill":
            expected = case["branch"] == "dynamic=True"
            if _binfill_dynamic(seed) is not expected:
                tried.append({"episode": episode, "seed": seed, "skipped": "dynamic 分支不符"})
                continue
        probe = dict(case)
        probe["episode"] = episode
        probe["seed"] = seed
        probe["cell"] = f"{case['cell']}__ep{episode}"
        result = _run_one(probe, "A1", output_root, evidence_root, True, log_dir)
        tried.append({"episode": episode, "seed": seed, "ok": bool(result.get("ok")), "elapsed_s": result.get("elapsed_s")})
        if result.get("ok"):
            return {"cell": case["cell"], "replacement": probe, "tried": tried}
    return {"cell": case["cell"], "replacement": None, "tried": tried}


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="newtask-v2 三路对拍实测驱动")
    parser.add_argument("--cases", default="docs/validation/newtask-v2/cases.json")
    parser.add_argument("--run-id", required=True, help="本次运行编号，用于输出与证据目录")
    parser.add_argument("--cell", action="append", default=None, help="只跑指定格，可重复")
    parser.add_argument("--path", action="append", default=None, choices=list(PATHS))
    parser.add_argument("--no-steps", action="store_true", help="不采集逐步状态（②.2 降级）")
    parser.add_argument(
        "--scan-replacement",
        action="append",
        default=None,
        help="对指定格扫描替补 episode（原版首次尝试即失败时用），可重复",
    )
    parser.add_argument("--scan-episodes", default="0-9", help="替补候选 episode 范围，如 0-9")
    args = parser.parse_args(argv)

    output_root = REPO_ROOT / "artifacts" / "parity" / args.run_id
    evidence_root = REPO_ROOT / "artifacts" / "parity-evidence" / args.run_id
    log_dir = REPO_ROOT / "artifacts" / "logs" / "parity" / args.run_id
    output_root.mkdir(parents=True, exist_ok=True)

    if args.scan_replacement:
        low, _, high = args.scan_episodes.partition("-")
        candidates = list(range(int(low), int(high) + 1))
        cases = json.loads((REPO_ROOT / args.cases).read_text(encoding="utf-8"))["cases"]
        by_cell = {case["cell"]: case for case in cases}
        found = []
        for cell in args.scan_replacement:
            if cell not in by_cell:
                print(f"ERROR: 用例表里没有这一格：{cell}", file=sys.stderr)
                return 1
            found.append(
                scan_replacement(by_cell[cell], candidates, output_root, evidence_root, log_dir)
            )
        target = log_dir / "replacement_scan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(found, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0 if all(item["replacement"] for item in found) else 1

    report = run_matrix(
        cases_path=REPO_ROOT / args.cases,
        output_root=output_root,
        evidence_root=evidence_root,
        log_dir=log_dir,
        only_cells=args.cell,
        only_paths=args.path,
        record_steps=not args.no_steps,
    )
    target = log_dir / "runner_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
