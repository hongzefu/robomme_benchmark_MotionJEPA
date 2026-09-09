"""对象动作冻结的后续实测：合并、隔离、重试、全任务和证据打包。

先完成 parity_runner 的完整矩阵，再调用本模块。所有生成仍走产品入口，
本工具只编排命令与比较产物；原始文件留在仓库 artifacts 内。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from tests._shared import native_sampling_parity as parity
from tests._shared import parity_runner as runner

ROOT = runner.REPO_ROOT
BASELINE = runner.BASELINE_WORKTREE
PAIRS = (("A1", "A2"), ("A1", "B"), ("A1", "C"), ("B", "C"))


def scalar(value):
    """解出观察器的小标量摘要，不改变原始证据。"""
    return value["values"][0] if isinstance(value, dict) and "values" in value else value


class Campaign:
    def __init__(self, run_id):
        if Path(run_id).name != run_id or run_id in (".", ".."):
            raise ValueError("运行编号必须为单个目录名")
        self.run_id = run_id
        self.run = ROOT / "artifacts/parity" / run_id
        self.evidence = ROOT / "artifacts/parity-evidence" / run_id
        self.output = ROOT / "artifacts/parity-pack" / run_id
        self.logs = ROOT / "artifacts/logs/parity" / run_id / "supplementary"
        self.output.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.cases = json.loads((ROOT / "docs/validation/newtask-v2/cases.json").read_text())["cases"]
        history = self.output / "supplementary_commands.json"
        self.commands = json.loads(history.read_text()) if history.is_file() else []

    def save(self, name, payload):
        (self.output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def execute(self, label, arguments, cwd=ROOT, env=None):
        command = ["uv", "run", "--no-sync", "--project", str(ROOT), "python", *map(str, arguments)]
        child_env = dict(os.environ) if env is None else env
        child_env["VIRTUAL_ENV"] = str(ROOT / ".venv")
        child_env["PYTHONUNBUFFERED"] = "1"
        start = time.monotonic()
        print(f"开始 {label}", flush=True)
        log = self.logs / f"{label}.log"
        with log.open("w") as sink:
            result = subprocess.run(command, cwd=cwd, env=child_env, stdout=sink, stderr=subprocess.STDOUT)
        record = {"label": label, "command": command, "cwd": str(cwd), "log": str(log),
                  "returncode": result.returncode, "elapsed_s": round(time.monotonic() - start, 2)}
        self.commands.append(record)
        self.save("supplementary_commands.json", self.commands)
        print(f"完成 {label}：退出码 {result.returncode}，{record['elapsed_s']} 秒", flush=True)
        if result.returncode:
            raise RuntimeError(f"{label} 失败，见 {log}")
        return record

    def pack(self):
        result = parity.pack_run(self.run, self.evidence, self.cases, self.output)
        print(f"完整对拍：{result['status_counts']}", flush=True)
        if not result["passed"]:
            raise RuntimeError("完整矩阵未全部通过，停止后续验证")

    def merges(self):
        reports = {}
        for case in self.cases:
            cell, task = case["cell"], case["task"]
            files = {}
            for label in runner.PATHS:
                source = parity._episode_dir(self.run, cell, label)
                target = source / "merged"
                if label.startswith("A"):
                    args = [BASELINE / "scripts/data-generation-newSeed/merge_episode_h5.py"]
                else:
                    args = [ROOT / runner.FLAT_ENTRY, "--merge-only"]
                self.execute(f"merge-{cell}-{label}", args + ["--input-dir", source, "--output-dir", target, "--env", task])
                files[label] = target / f"record_dataset_{task}.h5"
            comparisons = {f"{left}-{right}": parity.compare_h5(files[left], files[right]) for left, right in PAIRS}
            reports[cell] = {"files": {key: str(path) for key, path in files.items()}, "differences": comparisons,
                             "passed": not any(comparisons.values())}
            self.save("merged_comparison.json", reports)
            if not reports[cell]["passed"]:
                raise RuntimeError(f"合并产物不一致：{cell}")

    def isolation(self):
        reports = {}
        for label, independent in (("S-baseline", "A1"), ("S-default", "B"), ("S-config", "C")):
            env = runner._observer_env(self.evidence, label, True)
            if label == "S-baseline":
                env["PARITY_BASELINE"] = "1"
            args = ["-m", "tests._shared.parity_worker_isolation", "--run-id", self.run_id]
            if label == "S-config":
                args.append("--with-config")
            self.execute(label, args, env=env)
            run_report = json.loads((self.run / "worker-isolation" / f"{label}.json").read_text())
            continuous_root = (BASELINE / "artifacts/parity" / self.run_id if label == "S-baseline" else self.run) / "worker-isolation" / label
            slots = {}
            for slot, cell, task, seed, difficulty, occurrence in parity.ISOLATION_SLOTS:
                left = parity._single_h5(parity._episode_dir(self.run, cell, independent))
                right = parity._single_h5(continuous_root / slot)
                differences = parity.compare_h5(left, right)
                a = parity.load_evidence(self.evidence / independent / f"{task}_seed{seed}", difficulty)
                b = parity.load_evidence(self.evidence / label / f"{task}_seed{seed}", index=occurrence)
                comparison = parity.compare_evidence(a, b)
                caches = [record["spawn_cache_empty_on_entry"] for record in b["boundaries"] if "spawn_cache_empty_on_entry" in record]
                slots[slot] = {"h5_differences": differences, "evidence_passed": comparison["passed"],
                               "cache_empty": caches == [True], "passed": not differences and comparison["passed"] and caches == [True]}
            reports[label] = {"execution": run_report, "slots": slots,
                "passed": all(slot["passed"] for slot in slots.values()) and run_report["same_worker"]
                    and run_report["class_config_unchanged"] and run_report["parent_config_unchanged"]
                    and run_report["worker_class_config_unchanged"]}
            self.save("worker_isolation_complete.json", reports)
            if not reports[label]["passed"]:
                raise RuntimeError(f"连续 worker 对拍失败：{label}")

    def regressions(self):
        runs = {}
        for label in ("A1", "B", "C"):
            base = BASELINE if label == "A1" else ROOT
            target = base / "artifacts/parity" / self.run_id / "retry" / label
            entry = base / (runner.BASELINE_ENTRY if label == "A1" else runner.FLAT_ENTRY)
            args = [entry, "--output-dir", target, "--env", "BinFill", "--episodes", "1", "--episode-start", "0",
                    "--workers", "1", "--gpus", "0", "--layout", "train", "--difficulty", "010", "--max-attempts", "2"]
            if label == "C":
                args += ["--sampling-config", ROOT / runner.SAMPLING_CONFIG]
            self.execute(f"retry-{label}", args, cwd=base)
            attempts = [json.loads(line) for line in (target / "episode_results.jsonl").read_text().splitlines()]
            fields = ("task", "episode", "seed", "attempt", "ok", "failure_class", "error_type")
            runs[label] = {"path": str(target), "attempts": [{key: item.get(key) for key in fields} for item in attempts]}
        differences = {f"{a}-{b}": parity.compare_h5(parity._single_h5(Path(runs[a]["path"])), parity._single_h5(Path(runs[b]["path"])))
                       for a, b in (("A1", "B"), ("A1", "C"), ("B", "C"))}
        passed = runs["A1"]["attempts"] == runs["B"]["attempts"] == runs["C"]["attempts"] and not any(differences.values())
        self.save("retry_comparison.json", {"runs": runs, "differences": differences, "passed": passed})
        if not passed:
            raise RuntimeError("重试分支不一致")
        target = self.run / "all16"
        self.execute("all16", [ROOT / runner.FLAT_ENTRY, "--output-dir", target, "--env", "all", "--episodes", "1",
            "--workers", "1", "--gpus", "0", "--difficulty", "100", "--max-attempts", "1",
            "--sampling-config", ROOT / runner.SAMPLING_CONFIG])
        report = json.loads((target / "run_summary.json").read_text())
        self.save("all16_summary.json", report)
        if report["success_count"] != 16 or report["exhausted_count"]:
            raise RuntimeError("16 任务最小生成未全部成功")

    def actions(self):
        reports = {}
        for case in self.cases:
            paths = {}
            for label in runner.PATHS:
                evidence = parity.load_evidence(self.evidence / label / f"{case['task']}_seed{case['seed']}", case["difficulty"])
                boundaries = evidence["boundaries"]
                bindings = boundaries[-1]["task_state"]["action_bindings"]
                swaps = {}
                for event in evidence["events"]:
                    binding = event.get("swap_binding")
                    if not binding:
                        continue
                    current, start, end = (scalar(binding[key]) for key in ("cur_step", "start_step", "end_step"))
                    if start <= current < end:
                        swaps.setdefault(str(binding["swap_index"]), {"a": binding["a"], "b": binding["b"],
                            "resolved_at_step": current, "start_step": start, "end_step": end})
                paths[label] = {"pickup_targets": bindings["pickup_targets"], "route": bindings["route"], "actual_swaps": swaps}
                state = boundaries[-1]["task_state"]
                if case["task"] in ("VideoUnmaskSwap", "VideoRepick"):
                    if len(swaps) != scalar(state["swap_times"]):
                        raise RuntimeError(f"{case['cell']} {label}: 实际交换证据数量不完整")
                    if not bindings["pickup_targets"]:
                        raise RuntimeError(f"{case['cell']} {label}: 缺少实际抓取目标证据")
                if case["task"] == "RouteStick":
                    route = bindings["route"]
                    if len(route["nodes"]) != len(route["directions"]) + 1 or len(route["tasks"]) != 2 * len(route["directions"]):
                        raise RuntimeError(f"{case['cell']} {label}: 路线/演示/执行绑定数量不一致")
            reports[case["cell"]] = {"paths": paths, "passed": all(paths[a] == paths[b] for a, b in PAIRS)}
        self.save("action_bindings.json", reports)
        if not all(item["passed"] for item in reports.values()):
            raise RuntimeError("具体对象或动作绑定不一致")

    def frames(self):
        self.execute("keyframes", ["-m", "tests._shared.parity_keyframes", "--run-root", self.run,
            "--evidence-root", self.evidence,
            "--cases", ROOT / "docs/validation/newtask-v2/cases.json", "--result", self.output / "result.json",
            "--output", ROOT / "artifacts/keyframes" / self.run_id, "--index", self.output / "keyframe_index.json", "--limit", "0"])


def main():
    parser = argparse.ArgumentParser(description="对象动作冻结的后续完整验证")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", choices=("pack", "merges", "isolation", "regressions", "actions", "frames", "all"), default="all")
    args = parser.parse_args()
    campaign = Campaign(args.run_id)
    stages = ("pack", "actions", "merges", "isolation", "regressions", "frames") if args.phase == "all" else (args.phase,)
    for phase in stages:
        print(f"阶段 {phase}", flush=True)
        getattr(campaign, phase)()
    print("自动验证阶段全部完成；关键帧目视仍须逐图执行。", flush=True)


if __name__ == "__main__":
    main()
