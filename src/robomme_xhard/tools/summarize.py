"""实测汇总：读一个输出根，出逐条 (task, seed, difficulty) 实测表（markdown + json）。

每行字段：
- ``level``：所在档目录（mother / xhard12..xhard20）；``difficulty``：H5 ``setup/difficulty``。
- ``demo_timesteps`` / ``exec_timesteps`` / ``timesteps``：按 ``info/is_video_demo`` 分演示与执行两段。
- ``windows``：stride-16 窗口数，演示、执行两段分别按 w(L)=max(0,floor((L-33)/16)+1) 计后相加。
- ``ratio_timesteps`` / ``ratio_windows``：相对同 task、同 seed 母档的倍数。
- ``task_success`` / ``ok`` / ``failure_class``：权威来源依次为输出根下 ``run_summary.json`` 的
  ``cards[]``（role==mother→mother 档，role==xhard→difficulty 档）、根下 ``episode_results.jsonl``；
  都没有时才推断——RecordWrapper 只在 episode 成功时写 H5 的 episode 组，故有该组记 1，只有
  ``FAILED_`` 视频记 0，都没有记 None。失败卡即使既无 H5 也无视频也照样出行。

排序：TASK_ORDER → 母 seed（给 --seeds 时按清单 rank，否则 seed 升序）→ mother、xhard12..20。

判定行：
- ``DIFFICULTY_LABEL=PASS|FAIL files=<n>``：每个 H5 的 setup/difficulty 等于所在档目录名，母档等于来源难度。
- ``XHARD_RECORD_NONEMPTY=PASS|FAIL files=<n>``：每个 H5 timestep>0。
- ``GRADIENT_REVIEW=INFO ...``：长度梯度概况，交用户裁决（不判失败，R3、R24）。

用法::

    python -m robomme_xhard.tools.summarize --root <输出根> [--seeds <母 seed 清单.json>] \
        [--out-md <表.md>] [--out-json <表.json>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..configs import DIFFICULTIES, TARGET_RATIO, TASK_ORDER
from .layout import (
    MOTHER,
    expected_difficulty,
    level_rank,
    read_h5_summary,
    read_run_results,
    scan,
    task_rank,
    windows,
)


def _seed_order(manifest: dict | None) -> dict[tuple[str, int], int]:
    if not manifest:
        return {}
    order = {}
    for task, entries in manifest.get("tasks", {}).items():
        for entry in entries:
            order[(task, int(entry["seed"]))] = int(entry.get("rank", 0))
    return order


def sort_key(row: dict, seed_order: dict[tuple[str, int], int] | None = None):
    seed_order = seed_order or {}
    task, seed = row["task"], int(row["seed"])
    return (
        task_rank(task),
        seed_order.get((task, seed), 10**6),
        seed,
        level_rank(row["level"]),
    )


def collect(root: Path, manifest: dict | None = None) -> list[dict]:
    root = Path(root)
    artifacts = scan(root)
    # 权威来源：根下 run_summary.json cards[] → 根下 episode_results.jsonl → H5 / FAILED_ 视频推断
    results, result_source = read_run_results(root)
    keys = set(artifacts) | set(results)

    rows = []
    for task, seed, level in keys:
        art = artifacts.get((task, seed, level))
        rec = results.get((task, seed, level))
        row = {
            "task": task,
            "seed": seed,
            "level": level,
            "episode": art.episode if art and art.episode is not None else (rec or {}).get("episode"),
            "expected_difficulty": expected_difficulty(task, level),
            "difficulty": None,
            "h5_seed": None,
            "demo_timesteps": None,
            "exec_timesteps": None,
            "timesteps": None,
            "demo_windows": None,
            "exec_windows": None,
            "windows": None,
            "last_completed": None,
            "task_success": None,
            "failure_class": None,
            "h5": str(art.h5) if art and art.h5 else None,
            "video": str(art.video) if art and art.video else None,
            "failed_video": str(art.failed_video) if art and art.failed_video else None,
        }
        if art and art.h5:
            info = read_h5_summary(art.h5, art.episode)
            if info["has_episode"]:
                row.update(
                    difficulty=info["difficulty"],
                    h5_seed=info["h5_seed"],
                    demo_timesteps=info["demo_timesteps"],
                    exec_timesteps=info["exec_timesteps"],
                    timesteps=info["timesteps"],
                    last_completed=info["last_completed"],
                    task_success=1,
                )
                row["demo_windows"] = windows(info["demo_timesteps"])
                row["exec_windows"] = windows(info["exec_timesteps"])
                row["windows"] = row["demo_windows"] + row["exec_windows"]
        if rec is not None:
            # 生成器结果记录是 task_success / ok / failure_class 的权威来源
            row["ok"] = rec["ok"]
            if rec["task_success"] is not None:
                row["task_success"] = rec["task_success"]
            row["failure_class"] = rec["failure_class"]
            row["error"] = rec["error"]
            row["result_source"] = rec["source"]
        else:
            row["ok"] = None
            row["error"] = None
            row["result_source"] = "h5" if row["task_success"] == 1 else None
            if row["task_success"] is None and art and art.failed_video:
                row["task_success"] = 0
                row["result_source"] = "failed_video"
        rows.append(row)

    # 相对同 seed 母档的倍数
    mothers = {(r["task"], r["seed"]): r for r in rows if r["level"] == MOTHER}
    for row in rows:
        mother = mothers.get((row["task"], row["seed"]))
        row["ratio_timesteps"] = None
        row["ratio_windows"] = None
        row["target_ratio"] = TARGET_RATIO.get(row["level"], 1.0 if row["level"] == MOTHER else None)
        if mother and mother["timesteps"] and row["timesteps"] is not None:
            row["ratio_timesteps"] = round(row["timesteps"] / mother["timesteps"], 3)
        if mother and mother["windows"] and row["windows"] is not None:
            row["ratio_windows"] = round(row["windows"] / mother["windows"], 3)

    order = _seed_order(manifest)
    rows.sort(key=lambda r: sort_key(r, order))
    return rows


def judge(rows: list[dict]) -> dict[str, str]:
    h5_rows = [r for r in rows if r["h5"]]
    label_bad = [
        r for r in h5_rows if r["difficulty"] != r["expected_difficulty"]
    ]
    empty_bad = [r for r in h5_rows if not r["timesteps"]]
    n = len(h5_rows)

    # 梯度：每个 (task, seed) 内按 xhard12..20 已有成功档的 timestep 是否单调不减
    groups: dict[tuple[str, int], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["task"], r["seed"]), []).append(r)
    non_mono = []
    no_mother = 0
    for (task, seed), grp in groups.items():
        if not any(r["level"] == MOTHER and r["timesteps"] for r in grp):
            no_mother += 1
        seq = [
            r["timesteps"]
            for d in DIFFICULTIES
            for r in grp
            if r["level"] == d and r["timesteps"]
        ]
        if any(b < a for a, b in zip(seq, seq[1:])):
            non_mono.append(f"{task}/{seed}")
    failed = sum(1 for r in rows if r["task_success"] == 0)
    return {
        "DIFFICULTY_LABEL": f"DIFFICULTY_LABEL={'PASS' if n and not label_bad else 'FAIL'} files={n}"
        + (f" bad={len(label_bad)}" if label_bad else ""),
        "XHARD_RECORD_NONEMPTY": f"XHARD_RECORD_NONEMPTY={'PASS' if n and not empty_bad else 'FAIL'} files={n}"
        + (f" empty={len(empty_bad)}" if empty_bad else ""),
        "GRADIENT_REVIEW": (
            f"GRADIENT_REVIEW=INFO groups={len(groups)} rows={len(rows)} failed={failed} "
            f"missing_mother={no_mother} non_monotonic={len(non_mono)}"
            + (f" ({','.join(non_mono)})" if non_mono else "")
        ),
    }


def _fmt(value) -> str:
    return "—" if value is None else str(value)


def to_markdown(rows: list[dict], verdicts: dict[str, str]) -> str:
    head = (
        "| 任务 | seed | episode | 档 | setup/difficulty | 演示 timestep | 执行 timestep | 合计 timestep | "
        "演示窗 | 执行窗 | 合计窗 | 目标倍数 | timestep 倍数 | 窗口倍数 | task_success | 失败类 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    lines = [
        "| "
        + " | ".join(
            _fmt(v)
            for v in (
                r["task"],
                r["seed"],
                r["episode"],
                r["level"],
                r["difficulty"],
                r["demo_timesteps"],
                r["exec_timesteps"],
                r["timesteps"],
                r["demo_windows"],
                r["exec_windows"],
                r["windows"],
                r["target_ratio"],
                r["ratio_timesteps"],
                r["ratio_windows"],
                r["task_success"],
                r["failure_class"],
            )
        )
        + " |"
        for r in rows
    ]
    tail = "\n\n" + "\n".join(f"`{v}`" for v in verdicts.values()) + "\n"
    return "# xhard 逐条实测表\n\n" + head + "\n".join(lines) + tail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="汇总 xhard 输出根的逐条实测（只读）")
    parser.add_argument("--root", required=True, help="输出根，含 mother/ 与 xhard12..20/ 子目录")
    parser.add_argument("--seeds", default=None, help="母 seed 清单 JSON（决定 seed 排序）")
    parser.add_argument("--out-md", default=None)
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.seeds).read_text(encoding="utf-8")) if args.seeds else None
    rows = collect(Path(args.root), manifest)
    verdicts = judge(rows)
    md = to_markdown(rows, verdicts)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md, encoding="utf-8")
    else:
        print(md)
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(
            json.dumps({"rows": rows, "verdicts": verdicts}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    for line in verdicts.values():
        print(line)
    ok = all(verdicts[k].split("=", 1)[1].startswith("PASS") for k in ("DIFFICULTY_LABEL", "XHARD_RECORD_NONEMPTY"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
