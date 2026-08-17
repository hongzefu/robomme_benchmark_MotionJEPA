#!/usr/bin/env python3
"""把无 seed 生成的结果与 train metadata 逐条比对，出一致性报告。

比的是 ``(seed, difficulty)``。需要强调的是：seed 公式是纯函数
``f(env_code, episode, attempt)``，公式层面一致是必然的，**真正被检验的是 attempt 层面** ——
train 由 2025-12 的环境代码产出，若当前环境在某个 seed 上的成功/失败判定与当时不同，
就会演进出不同的 attempt，seed 随之不同。所以本报告的实质是
「当前环境代码与 2025-12 环境代码的行为等价性」，train 里 attempt≠0 的那几条探针最敏感。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
CONTRACT_DIR = SCRIPT_DIR.parent / "data-generation"
for _extra in (str(SCRIPT_DIR), str(CONTRACT_DIR)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from validate_generated_dataset_contract import METADATA_ROOT, parse_tasks  # noqa: E402
from write_generation_report import write_text_atomic  # noqa: E402

from seed_layout import DEFAULT_LAYOUT, LAYOUTS, get_layout  # noqa: E402


def _train_records(task: str) -> dict[int, dict[str, Any]]:
    path = METADATA_ROOT / f"record_dataset_{task}_metadata.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(item["episode"]): item for item in payload["records"]}


def _generated_records(output: Path, task: str) -> dict[int, dict[str, Any]]:
    path = output / f"record_dataset_{task}_metadata.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(item["episode"]): item for item in payload["records"]}


def _attempt_trace(output: Path) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """从 JSONL 还原每个 episode 走过的 attempt 轨迹。"""
    trace: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    path = output / "episode_results.jsonl"
    if not path.is_file():
        return trace
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            trace[(str(item.get("task")), int(item.get("episode", -1)))].append(item)
    for entries in trace.values():
        entries.sort(key=lambda item: int(item.get("attempt", 0)))
    return trace


def compare(output: Path, tasks: Sequence[str], layout_name: str) -> dict[str, Any]:
    layout = get_layout(layout_name)
    trace = _attempt_trace(output)
    per_task: dict[str, Any] = {}
    probes: list[dict[str, Any]] = []
    total = matched = missing = 0

    for task in tasks:
        train = _train_records(task)
        generated = _generated_records(output, task)
        rows: list[dict[str, Any]] = []
        for episode in sorted(train):
            total += 1
            expected = train[episode]
            expected_seed = int(expected["seed"])
            expected_attempt = expected_seed - layout.base_seed(task, episode)
            actual = generated.get(episode)
            entries = trace.get((task, episode), [])
            row: dict[str, Any] = {
                "episode": episode,
                "expected_seed": expected_seed,
                "expected_difficulty": str(expected["difficulty"]),
                "expected_attempt": expected_attempt,
                "attempt_trace": [
                    {
                        "attempt": int(item.get("attempt", 0)),
                        "seed": int(item.get("seed", 0)),
                        "ok": bool(item.get("ok")),
                        "error_type": item.get("error_type"),
                        "failure_class": item.get("failure_class"),
                    }
                    for item in entries
                ],
            }
            if actual is None:
                missing += 1
                row.update({"status": "missing", "actual_seed": None, "actual_difficulty": None})
            else:
                actual_seed = int(actual["seed"])
                actual_attempt = actual_seed - layout.base_seed(task, episode)
                same = actual_seed == expected_seed and str(actual["difficulty"]) == str(
                    expected["difficulty"]
                )
                matched += int(same)
                row.update(
                    {
                        "status": "match" if same else "mismatch",
                        "actual_seed": actual_seed,
                        "actual_difficulty": str(actual["difficulty"]),
                        "actual_attempt": actual_attempt,
                    }
                )
            rows.append(row)
            if expected_attempt != 0:
                probes.append({"task": task, **row})

        task_matched = sum(1 for row in rows if row["status"] == "match")
        per_task[task] = {
            "count": len(rows),
            "matched": task_matched,
            "mismatched": sum(1 for row in rows if row["status"] == "mismatch"),
            "missing": sum(1 for row in rows if row["status"] == "missing"),
            "rows": rows,
        }

    return {
        "output_dir": str(output),
        "seed_layout": layout_name,
        "tasks": list(tasks),
        "total": total,
        "matched": matched,
        "mismatched": total - matched - missing,
        "missing": missing,
        "match_rate": round(matched / total, 4) if total else None,
        "per_task": per_task,
        "probes": probes,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 无 seed 生成与 train metadata 的一致性报告\n")
    lines.append(
        f"- 输出目录：`{report['output_dir']}`\n"
        f"- seed 布局：`{report['seed_layout']}`\n"
        f"- 总计 {report['total']} 条，一致 {report['matched']} 条，"
        f"不一致 {report['mismatched']} 条，缺失 {report['missing']} 条\n"
        f"- 一致率：**{report['match_rate']}**\n"
    )
    lines.append(
        "\n> seed 公式是纯函数 `f(env_code, episode, attempt)`，公式层面一致是必然的。"
        "真正被检验的是 attempt 层面 —— 即当前环境代码与 2025-12 环境代码的行为等价性。"
        "下面的探针是 train 里 attempt≠0 的条目，最为敏感。\n"
    )

    lines.append("\n## 各环境汇总\n")
    lines.append("| env | 条数 | 一致 | 不一致 | 缺失 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for task, data in report["per_task"].items():
        lines.append(
            f"| {task} | {data['count']} | {data['matched']} | {data['mismatched']} | {data['missing']} |"
        )

    lines.append("\n## 关键探针（train 里 attempt≠0 的条目）\n")
    if not report["probes"]:
        lines.append("_无_")
    else:
        lines.append("| env | episode | 期望 seed | 期望 attempt | 实际 seed | 实际 attempt | 结论 | attempt 轨迹 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |")
        for probe in report["probes"]:
            trace = " → ".join(
                f"{item['seed']}{'✓' if item['ok'] else '✗' + (item['error_type'] or '')}"
                for item in probe["attempt_trace"]
            ) or "—"
            lines.append(
                f"| {probe['task']} | {probe['episode']} | {probe['expected_seed']} | "
                f"{probe['expected_attempt']} | {probe.get('actual_seed')} | "
                f"{probe.get('actual_attempt')} | {probe['status']} | {trace} |"
            )

    mismatches = [
        (task, row)
        for task, data in report["per_task"].items()
        for row in data["rows"]
        if row["status"] != "match"
    ]
    lines.append("\n## 不一致与缺失明细\n")
    if not mismatches:
        lines.append("_全部一致_")
    else:
        lines.append("| env | episode | 期望 seed | 实际 seed | 状态 | attempt 轨迹 |")
        lines.append("| --- | ---: | ---: | ---: | --- | --- |")
        for task, row in mismatches:
            trace = " → ".join(
                f"{item['seed']}{'✓' if item['ok'] else '✗' + (item['error_type'] or '')}"
                for item in row["attempt_trace"]
            ) or "—"
            lines.append(
                f"| {task} | {row['episode']} | {row['expected_seed']} | "
                f"{row.get('actual_seed')} | {row['status']} | {trace} |"
            )

    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="无 seed 生成结果与 train metadata 的一致性比对")
    parser.add_argument("--output-dir", required=True, help="generate_dataset_newseed.py 的输出目录")
    parser.add_argument("--env", "--environment", default="all", help="all 或逗号分隔的环境名")
    parser.add_argument("--layout", default=DEFAULT_LAYOUT, choices=sorted(LAYOUTS))
    args = parser.parse_args(argv)

    output = Path(args.output_dir).resolve()
    if not output.is_dir():
        print(f"ERROR: 输出目录不存在：{output}", file=sys.stderr)
        return 1

    report = compare(output, parse_tasks(args.env), args.layout)
    write_text_atomic(
        output / "consistency_report.json",
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    write_text_atomic(output / "consistency_report.md", _markdown(report))
    print(
        json.dumps(
            {
                "total": report["total"],
                "matched": report["matched"],
                "mismatched": report["mismatched"],
                "missing": report["missing"],
                "match_rate": report["match_rate"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["mismatched"] == 0 and report["missing"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
