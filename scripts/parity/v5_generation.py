#!/usr/bin/env python3
"""V5 一次多 worker 生成：一条命令串起抽签 → 冻结 → 实跑 → 报告（NEWTASK_RELEASE_V5_PLAN 3.1、3.2「生成报告」、3.3 S6）。

两个子命令：

* ``pipeline``：按 ``--release``／``--run-id`` 推导全部落点，依次以子进程调用
  ``v4_specs draw``（``--workers``）→ ``v4_specs freeze`` → ``v4_rollout run``（``--workers``，H4 递补，只跑一遍）
  → 本文件 ``report``。任一步非零退出即停，不做任何中间比对。``--resume`` 时已有产物的步骤跳过
  （drafts／specs 本来就禁止覆盖，freeze 与 run 会重新核验上游来源，陈旧产物会被拒而不是被悄悄沿用）。
* ``report``：只读 drafts.jsonl、specs.jsonl、rollout 的 results.jsonl、各局 h5 与 rng_trace.json，输出判定行
  ``V5_GENERATION=REPORT tasks=… draft_ok=… rollout_ok=… backfilled=… selected_shortfall=…
  demo_frames_out_of_band=… outer_swap_mismatch=… bin_collision=… vr_min_participants=…``，
  外加逐环境表的 markdown 与 JSON。报告不设门槛（N10），取不到的量一律记 ``N/A`` 而不是崩溃。

落点（``<R>`` = ``--release``，``<id>`` = ``--run-id``）：

    快照      scripts/configs/<R>/sampling_config.json          （S4 用 train_split_config extract --release 生成）
    抽签      artifacts/<R>/<id>/draft/drafts.jsonl
    冻结      scripts/configs/<R>/<id>/specs.jsonl
    实跑      artifacts/<R>/<id>/rollout/<label>/               （results.jsonl、summary.json、episodes/）
    报告      artifacts/<R>/<id>/report/generation_report.{md,json}

    uv run --no-sync python -m scripts.parity.v5_generation pipeline --run-id v5-01 --draw-workers 8 --workers 8 \\
        --official-root artifacts/train-parity/local-smoke-01/official-src
    uv run --no-sync python -m scripts.parity.v5_generation report \\
        --drafts artifacts/newtask-v5/v5-01/draft/drafts.jsonl --specs scripts/configs/newtask-v5/v5-01/specs.jsonl \\
        --rollout artifacts/newtask-v5/v5-01/rollout/run1 --out artifacts/newtask-v5/v5-01/report

规格字段名（外环交换、VideoRepick 搭档）由环境侧实现决定，本文件把路径集中在下面的常量里；
字段缺失或形状认不出时对应项记 ``N/A`` 并在 ``warnings`` 里写明原因。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

DEFAULT_RELEASE = "newtask-v5"
DEFAULT_LABEL = "run1"
DEFAULT_SELECT = (0, 3, 6)
NA = "N/A"

# 口径 9：演示时长 25～35 s × 30 fps ⇒ is_video_demo 为真的帧数落在 [750, 1050]
DEMO_TASKS = ("PatternLock", "RouteStick")
DEMO_BAND = (750, 1050)
# 口径 4：Swap 两环境每一次内环交换配恰好一次外环交换
SWAP_TASKS = ("VideoUnmaskSwap", "ButtonUnmaskSwap")
N_SWAPS_PATHS = ("objects.n_swaps",)
# 外环交换在 reset 时规划（计划 2.5：actions.distractor_swap_pairs，record 写入）
OUTER_PAIRS_PATHS = ("actions.distractor_swap_pairs",)
# 运行时若另有逐窗口记录（名字以环境侧实现为准），从 rng_trace.json 里按前缀数窗口
OUTER_TRACE_PREFIXES = ("actions.distractor_swap_windows.", "actions.distractor_swaps.")
# 口径 10：VideoRepick 全部方块都参与交换（规格 actions.swap_pairs.<k>；V4 只在运行时 record，见 rng_trace）
VR_TASK = "VideoRepick"
VR_PAIRS_PATHS = ("actions.swap_pairs",)
VR_TRACE_PREFIX = "actions.swap_pairs."
BIN_COLLISION = "BinCollisionError"
# 认得出的「一对交换」键名（按优先级）；*_choice 是候选下标而不是方块身份，不认
PAIR_KEYS = (("initiator", "partner"), ("first", "second"), ("idx1", "idx2"), ("a", "b"), ("i", "j"),
             ("src", "dst"), ("u", "v"))


# ── 通用读取 ─────────────────────────────────────────────────────────────


def read_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).is_file():
        return []
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def get_path(tree: Any, dotted: str) -> Any:
    """按点分路径取值；任一层缺失返回 None（列表允许用数字下标）。"""
    node = tree
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return node


def first_path(tree: Any, paths: tuple[str, ...]) -> tuple[str | None, Any]:
    for dotted in paths:
        value = get_path(tree, dotted)
        if value is not None:
            return dotted, value
    return None, None


def indexed_items(value: Any) -> list[Any] | None:
    """规格里按事件序号存的容器（``{"0": …, "1": …}`` 或列表）→ 按序号排好的条目；认不出返回 None。"""
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict) and value and all(str(key).isdigit() for key in value):
        return [value[key] for key in sorted(value, key=lambda k: int(k))]
    return None


def _as_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        match = re.search(r"(\d+)$", value)
        return int(match.group(1)) if match else None
    return None


def parse_pair(item: Any) -> tuple[int, int] | None:
    """一次交换 → (方块甲, 方块乙) 的身份号；认不出返回 None。

    认得：长度 2 的列表／元组；含 ``pair`` 键的字典；含 ``PAIR_KEYS`` 任一组键的字典。
    身份号可以是整数或 ``bin_3`` 这类带数字后缀的名字。
    """
    if isinstance(item, (list, tuple)) and len(item) == 2:
        ids = (_as_id(item[0]), _as_id(item[1]))
        return ids if None not in ids else None  # type: ignore[return-value]
    if isinstance(item, dict):
        if "pair" in item:
            return parse_pair(item["pair"])
        for left, right in PAIR_KEYS:
            if left in item and right in item:
                ids = (_as_id(item[left]), _as_id(item[right]))
                return ids if None not in ids else None  # type: ignore[return-value]
    return None


def participants(pairs: list[Any]) -> int | None:
    """参与交换的不同方块数；任一对认不出则整体返回 None。"""
    seen: set[int] = set()
    for item in pairs:
        parsed = parse_pair(item)
        if parsed is None:
            return None
        seen.update(parsed)
    return len(seen)


def read_trace(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("calls")
    except (OSError, ValueError, AttributeError):
        return None


def trace_indexed(calls: list[dict[str, Any]] | None, prefix: str) -> dict[int, Any]:
    """rng_trace 里 ``<prefix><k>`` 这一层的记录（同一序号取最后一次）；更深的子路径忽略。"""
    out: dict[int, Any] = {}
    for call in calls or []:
        path = str(call.get("path", ""))
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix):]
        if rest.isdigit():
            out[int(rest)] = call.get("drawn", call.get("value"))
    return out


def count_demo_frames(h5_path: Path) -> int:
    """h5 里 ``<episode>/timestep_*/info/is_video_demo`` 为真的帧数（全部 episode 组求和）。"""
    import h5py
    import numpy as np

    total = 0
    with h5py.File(h5_path, "r") as handle:
        for episode in handle.values():
            if not hasattr(episode, "keys"):
                continue
            for name, step in episode.items():
                if not name.startswith("timestep_") or "info" not in step or "is_video_demo" not in step["info"]:
                    continue
                total += int(bool(np.reshape(np.asarray(step["info"]["is_video_demo"][()]), -1)[0]))
    return total


# ── 报告主体 ─────────────────────────────────────────────────────────────


def _episode_dir(rollout_dir: Path, row: dict[str, Any]) -> Path:
    return rollout_dir / "episodes" / f"{row['task']}_episode_{row['episode']}"


def _resolve_h5(rollout_dir: Path, row: dict[str, Any]) -> Path | None:
    """results.jsonl 里记的是绝对路径；目录被挪过时退回 ``episodes/<task>_episode_<n>/hdf5_files/*.h5``。"""
    recorded = row.get("h5")
    if recorded and Path(recorded).is_file():
        return Path(recorded)
    files = sorted((_episode_dir(rollout_dir, row) / "hdf5_files").glob("*.h5"))
    return files[0] if len(files) == 1 else None


def _resolve_trace(rollout_dir: Path, row: dict[str, Any], h5: Path | None) -> Path | None:
    candidates = [_episode_dir(rollout_dir, row) / "rng_trace.json"]
    if h5 is not None:
        candidates.insert(0, h5.parent.parent / "rng_trace.json")
    for path in candidates:
        if path.is_file():
            return path
    return None


def build_report(drafts_path: str | Path, specs_path: str | Path | None, rollout_dir: str | Path,
                 candidates_per_env: int = 10, band: tuple[int, int] = DEMO_BAND,
                 frame_counter=count_demo_frames) -> dict[str, Any]:
    """读三份产物，返回报告字典（``line``、``totals``、``per_env``、三类逐局明细、``warnings``）。

    ``frame_counter`` 只供单测注入（避免在测试里造大 h5）。
    """
    warnings: list[str] = []
    rollout_dir = Path(rollout_dir)
    drafts = read_jsonl(drafts_path)
    if not drafts:
        raise SystemExit(f"drafts 不存在或为空：{drafts_path}")
    draft_header = drafts[0] if drafts[0].get("record") == "header" else {}
    draft_rows = [r for r in drafts if r.get("record") == "draft"]
    specs = read_jsonl(specs_path)
    specs_header = specs[0] if specs and specs[0].get("record") == "header" else {}
    spec_rows = [r for r in specs if r.get("record") == "spec"]
    if specs_path and not specs:
        warnings.append(f"specs 不存在或为空：{specs_path}；正式局目标数按 index {list(DEFAULT_SELECT)} 推算")
    results = read_jsonl(rollout_dir / "results.jsonl")
    if not results:
        warnings.append(f"rollout 结果不存在或为空：{rollout_dir / 'results.jsonl'}")

    tasks = list(draft_header.get("tasks") or specs_header.get("tasks") or
                 sorted({r["task"] for r in draft_rows} | {r["task"] for r in results}))
    # 规格来源：优先 specs.jsonl（冻结值），缺失时退回 drafts 的成功行（episode 编号相同）
    spec_of: dict[tuple[str, int], dict[str, Any]] = {}
    for row in draft_rows:
        if row.get("reset_ok") and row.get("spec") is not None:
            spec_of[(row["task"], int(row["episode"]))] = row["spec"]
    for row in spec_rows:
        spec_of[(row["task"], int(row["episode"]))] = row["spec"]
    select_indices = tuple(specs_header.get("select_indices") or DEFAULT_SELECT)

    per_env: dict[str, dict[str, Any]] = {}
    demo_rows: list[dict[str, Any]] = []
    swap_rows: list[dict[str, Any]] = []
    vr_rows: list[dict[str, Any]] = []
    for task in tasks:
        mine_d = [r for r in draft_rows if r["task"] == task]
        draft_ok = sum(1 for r in mine_d if r.get("reset_ok"))
        if spec_rows:
            target = sum(1 for r in spec_rows if r["task"] == task and r.get("selected"))
        else:
            target = sum(1 for idx in select_indices if idx < draft_ok)
        mine_r = sorted((r for r in results if r["task"] == task), key=lambda r: int(r["episode"]))
        rollout_ok = sum(1 for r in mine_r if r.get("ok"))
        by_class = Counter(str(r.get("error_type") or "Unknown") for r in mine_r if not r.get("ok"))
        per_env[task] = {
            "draft_attempted": len(mine_d),
            "draft_ok": draft_ok,
            "candidate_shortfall": max(0, candidates_per_env - draft_ok),
            "draft_fail_classes": dict(sorted(Counter(str(r.get("fail_class") or "Unknown")
                                                      for r in mine_d if not r.get("reset_ok")).items())),
            "selected_target": target,
            "rollout_attempted": len(mine_r),
            "rollout_ok": rollout_ok,
            "backfilled": sum(1 for r in mine_r if r.get("role") == "backfill" and r.get("ok")),
            "selected_shortfall": max(0, target - rollout_ok),
            "by_class": dict(sorted(by_class.items())),
        }
        for row in mine_r:
            episode = int(row["episode"])
            spec = spec_of.get((task, episode))
            h5 = _resolve_h5(rollout_dir, row) if row.get("ok") else None
            ident = {"task": task, "episode": episode, "seed": row.get("seed"), "role": row.get("role"),
                     "ok": bool(row.get("ok"))}
            if task in DEMO_TASKS and row.get("ok"):
                entry = dict(ident, h5=str(h5) if h5 else None, demo_frames=None, in_band=None)
                if h5 is None:
                    warnings.append(f"{task}/{episode} 成功但找不到 h5，演示帧数记 N/A")
                else:
                    try:
                        entry["demo_frames"] = frame_counter(h5)
                        entry["in_band"] = band[0] <= entry["demo_frames"] <= band[1]
                    except Exception as exc:  # noqa: BLE001 坏文件如实记 N/A
                        warnings.append(f"{task}/{episode} 读 h5 失败：{type(exc).__name__}: {exc}")
                demo_rows.append(entry)
            if task in SWAP_TASKS:
                swap_rows.append(_outer_swap_entry(ident, spec, read_trace(_resolve_trace(rollout_dir, row, h5))))
            if task == VR_TASK:
                vr_rows.append(_vr_entry(ident, spec, read_trace(_resolve_trace(rollout_dir, row, h5))))

    # 汇总
    def total(key: str) -> int:
        return sum(int(v[key]) for v in per_env.values())

    measured_demo = [r for r in demo_rows if r["demo_frames"] is not None]
    demo_out = sum(1 for r in measured_demo if not r["in_band"]) if measured_demo else NA
    checked_swap = [r for r in swap_rows if r["equal"] is not None]
    outer_mismatch = sum(1 for r in checked_swap if not r["equal"]) if checked_swap else NA
    measured_vr = [r["participants"] for r in vr_rows if r["participants"] is not None]
    vr_min = min(measured_vr) if measured_vr else NA
    bin_collision = sum(1 for r in results if not r.get("ok") and r.get("error_type") == BIN_COLLISION)
    for label, rows, key in (("PatternLock/RouteStick 演示帧数", demo_rows, "demo_frames"),
                             ("Swap 外环窗口数", swap_rows, "equal"),
                             ("VideoRepick 参与方块数", vr_rows, "participants")):
        if rows and all(r[key] is None for r in rows):
            warnings.append(f"{label}：{len(rows)} 局全部取不到（字段缺失或形状认不出），记 N/A")
    totals = {
        "tasks": len(tasks),
        "draft_attempted": total("draft_attempted"),
        "draft_ok": total("draft_ok"),
        "candidate_shortfall": total("candidate_shortfall"),
        "rollout_attempted": total("rollout_attempted"),
        "rollout_ok": total("rollout_ok"),
        "backfilled": total("backfilled"),
        "selected_shortfall": total("selected_shortfall"),
        "demo_frames_checked": len(measured_demo),
        "demo_frames_out_of_band": demo_out,
        "outer_swap_checked": len(checked_swap),
        "outer_swap_mismatch": outer_mismatch,
        "bin_collision": bin_collision,
        "draft_bin_collision": sum(1 for r in draft_rows if r.get("fail_class") == BIN_COLLISION),
        "vr_checked": len(measured_vr),
        "vr_min_participants": vr_min,
    }
    line = ("V5_GENERATION=REPORT "
            + " ".join(f"{key}={totals[key]}" for key in (
                "tasks", "draft_ok", "rollout_ok", "backfilled", "selected_shortfall", "demo_frames_out_of_band",
                "outer_swap_mismatch", "bin_collision", "vr_min_participants")))
    return {
        "line": line,
        "sources": {"drafts": str(drafts_path), "specs": str(specs_path) if specs_path else None,
                    "rollout": str(rollout_dir), "run_id": draft_header.get("run_id"),
                    "identity_sha256": specs_header.get("identity_sha256")},
        "params": {"candidates_per_env": candidates_per_env, "demo_band": list(band),
                   "select_indices": list(select_indices)},
        "totals": totals,
        "per_env": per_env,
        "demo_frames": demo_rows,
        "outer_swap": swap_rows,
        "vr_participants": vr_rows,
        "warnings": warnings,
    }


def _outer_swap_entry(ident: dict[str, Any], spec: dict[str, Any] | None,
                      calls: list[dict[str, Any]] | None) -> dict[str, Any]:
    """外环窗口数（规格里 reset 规划的对数；另有运行时逐窗记录时一并比）与 n_swaps 是否相等。"""
    entry = dict(ident, n_swaps=None, planned_windows=None, executed_windows=None, equal=None, note=None)
    if spec is None:
        entry["note"] = "无规格"
        return entry
    _, n_swaps = first_path(spec, N_SWAPS_PATHS)
    entry["n_swaps"] = n_swaps if isinstance(n_swaps, int) and not isinstance(n_swaps, bool) else None
    path, pairs = first_path(spec, OUTER_PAIRS_PATHS)
    items = indexed_items(pairs) if pairs is not None else None
    if items is not None:
        entry["planned_windows"] = sum(1 for item in items if item is not None)
    executed = {}
    for prefix in OUTER_TRACE_PREFIXES:
        executed = trace_indexed(calls, prefix)
        if executed:
            break
    if executed:
        entry["executed_windows"] = len(executed)
    counts = [c for c in (entry["planned_windows"], entry["executed_windows"]) if c is not None]
    if entry["n_swaps"] is None or not counts:
        entry["note"] = ("规格缺 " + "/".join(OUTER_PAIRS_PATHS) if not counts else "规格缺 n_swaps")
        return entry
    entry["equal"] = all(c == entry["n_swaps"] for c in counts)
    return entry


def _vr_entry(ident: dict[str, Any], spec: dict[str, Any] | None,
              calls: list[dict[str, Any]] | None) -> dict[str, Any]:
    """参与交换的方块数：优先规格（V5 reset 规划写入），否则 rng_trace 的运行时记录（V4 形态）。"""
    entry = dict(ident, participants=None, n_pairs=None, source=None, note=None)
    _, pairs = first_path(spec or {}, VR_PAIRS_PATHS)
    items = indexed_items(pairs) if pairs is not None else None
    if items:
        count = participants(items)
        if count is not None:
            entry.update(participants=count, n_pairs=len(items), source="spec")
            return entry
        entry["note"] = "规格 swap_pairs 形状认不出"
    traced = trace_indexed(calls, VR_TRACE_PREFIX)
    if traced:
        items = [traced[k] for k in sorted(traced)]
        count = participants(items)
        if count is not None:
            entry.update(participants=count, n_pairs=len(items), source="rng_trace", note=None)
            return entry
        entry["note"] = "rng_trace swap_pairs 形状认不出"
    if entry["note"] is None:
        entry["note"] = "规格与 rng_trace 都没有 swap_pairs"
    return entry


def render_markdown(report: dict[str, Any]) -> str:
    totals, params = report["totals"], report["params"]
    lines = [
        "# V5 生成报告",
        "",
        f"- 来源：drafts `{report['sources']['drafts']}`；specs `{report['sources']['specs']}`；"
        f"rollout `{report['sources']['rollout']}`；run_id `{report['sources']['run_id']}`",
        f"- 口径：每环境候选目标 {params['candidates_per_env']} 条；正式局 index {params['select_indices']}；"
        f"演示帧数合格带 {params['demo_band'][0]}～{params['demo_band'][1]}（`info/is_video_demo` 为真的帧数）",
        "",
        "```text",
        report["line"],
        "```",
        "",
        f"草稿尝试 {totals['draft_attempted']}、成功 {totals['draft_ok']}、候选缺口 {totals['candidate_shortfall']}；"
        f"实跑 {totals['rollout_attempted']} 局、成功 {totals['rollout_ok']}、递补成功 {totals['backfilled']}、"
        f"正式局缺口 {totals['selected_shortfall']}；抽签期 BinCollisionError {totals['draft_bin_collision']}。",
        "",
        "## 逐环境",
        "",
        "| 环境 | draft_attempted | draft_ok | candidate_shortfall | 抽签失败类别 | 正式局目标 | rollout_attempted | "
        "rollout_ok | backfilled | selected_shortfall | by_class |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    fmt = lambda d: "；".join(f"{k}×{v}" for k, v in d.items()) or "—"  # noqa: E731
    for task, env in report["per_env"].items():
        lines.append(
            f"| {task} | {env['draft_attempted']} | {env['draft_ok']} | {env['candidate_shortfall']} | "
            f"{fmt(env['draft_fail_classes'])} | {env['selected_target']} | {env['rollout_attempted']} | "
            f"{env['rollout_ok']} | {env['backfilled']} | {env['selected_shortfall']} | {fmt(env['by_class'])} |")
    na = lambda v: NA if v is None else v  # noqa: E731
    lines += ["", f"## PatternLock / RouteStick 演示帧数（合格带 {params['demo_band'][0]}～{params['demo_band'][1]}）", "",
              "| 环境 | episode | seed | 角色 | 演示帧数 | 秒（÷30） | 落在带内 |", "|---|---|---|---|---|---|---|"]
    for row in report["demo_frames"]:
        seconds = f"{row['demo_frames'] / 30:.1f}" if row["demo_frames"] is not None else NA
        lines.append(f"| {row['task']} | {row['episode']} | {row['seed']} | {row['role']} | {na(row['demo_frames'])} | "
                     f"{seconds} | {na(row['in_band'])} |")
    lines += ["", "## Swap 两环境外环交换窗口数 vs n_swaps", "",
              "| 环境 | episode | seed | 演示成功 | n_swaps | 规划窗口数 | 运行时窗口数 | 相等 | 说明 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for row in report["outer_swap"]:
        lines.append(f"| {row['task']} | {row['episode']} | {row['seed']} | {row['ok']} | {na(row['n_swaps'])} | "
                     f"{na(row['planned_windows'])} | {na(row['executed_windows'])} | {na(row['equal'])} | "
                     f"{row['note'] or ''} |")
    lines += ["", "## VideoRepick 每局参与交换的方块数", "",
              "| episode | seed | 演示成功 | 交换次数 | 参与方块数 | 来源 | 说明 |", "|---|---|---|---|---|---|---|"]
    for row in report["vr_participants"]:
        lines.append(f"| {row['episode']} | {row['seed']} | {row['ok']} | {na(row['n_pairs'])} | "
                     f"{na(row['participants'])} | {row['source'] or NA} | {row['note'] or ''} |")
    if report["warnings"]:
        lines += ["", "## 提示", ""] + [f"- {item}" for item in report["warnings"]]
    return "\n".join(lines) + "\n"


def cmd_report(args: argparse.Namespace) -> int:
    report = build_report(args.drafts, args.specs, args.rollout, args.candidates_per_env,
                          (args.band_min, args.band_max))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "generation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    (out / "generation_report.md").write_text(render_markdown(report), encoding="utf-8")
    print(report["line"], flush=True)
    for item in report["warnings"][:20]:
        print(f"# {item}")
    print(f"# 报告：{out / 'generation_report.md'}、{out / 'generation_report.json'}")
    return 0


# ── 一条命令串起三段 ─────────────────────────────────────────────────────


def pipeline_paths(release: str, run_id: str, label: str = DEFAULT_LABEL) -> dict[str, Path]:
    """全部落点只由 release 与 run id 推导（相对仓库根）。"""
    return {
        "sampling": Path("scripts") / "configs" / release / "sampling_config.json",
        "drafts": Path("artifacts") / release / run_id / "draft" / "drafts.jsonl",
        "specs": Path("scripts") / "configs" / release / run_id / "specs.jsonl",
        "rollout_root": Path("artifacts") / release / run_id / "rollout",
        "rollout": Path("artifacts") / release / run_id / "rollout" / label,
        "report": Path("artifacts") / release / run_id / "report",
    }


def plan_pipeline(args: argparse.Namespace, root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    """四步的命令与落点；``--resume`` 时标出可跳过的步骤。纯函数，单测直接调用。"""
    paths = pipeline_paths(args.release, args.run_id, args.label)
    py = [sys.executable, "-m"]
    draw = py + ["scripts.parity.v4_specs", "draw", "--run-id", args.run_id, "--tasks", args.tasks,
                 "--sampling-config", str(paths["sampling"]), "--candidates-per-env", str(args.candidates_per_env),
                 "--max-reset-attempts", str(args.max_reset_attempts), "--workers", str(args.draw_workers),
                 "--out", str(paths["drafts"])]
    if args.draw_gpus:
        draw += ["--gpus", args.draw_gpus]
    freeze = py + ["scripts.parity.v4_specs", "freeze", "--drafts", str(paths["drafts"]),
                   "--sampling-config", str(paths["sampling"]), "--select", args.select,
                   "--candidates-per-env", str(args.candidates_per_env), "--out", str(paths["specs"])]
    run = py + ["scripts.parity.v4_rollout", "run", "--specs", str(paths["specs"]), "--label", args.label,
                "--tasks", args.tasks, "--official-root", args.official_root, "--workers", str(args.workers),
                "--gpu", str(args.rollout_gpu), "--output", str(paths["rollout_root"])]
    report = py + ["scripts.parity.v5_generation", "report", "--drafts", str(paths["drafts"]),
                   "--specs", str(paths["specs"]), "--rollout", str(paths["rollout"]),
                   "--candidates-per-env", str(args.candidates_per_env), "--out", str(paths["report"])]
    steps = [
        {"name": "draw", "cmd": draw, "done": (root / paths["drafts"]).is_file()},
        {"name": "freeze", "cmd": freeze, "done": (root / paths["specs"]).is_file()},
        {"name": "run", "cmd": run, "done": (root / paths["rollout"] / "results.jsonl").is_file()},
        {"name": "report", "cmd": report, "done": False},  # 报告总是重出
    ]
    for step in steps:
        step["skip"] = bool(args.resume and step["done"])
    return steps


def cmd_pipeline(args: argparse.Namespace) -> int:
    paths = pipeline_paths(args.release, args.run_id, args.label)
    steps = plan_pipeline(args)
    if args.dry_run:
        for step in steps:
            print(f"PIPELINE_PLAN {step['name']} skip={step['skip']} :: " + " ".join(step["cmd"][1:]))
        return 0
    if not (REPO_ROOT / paths["sampling"]).is_file():
        print(f"PIPELINE_FAIL step=precheck 快照不存在：{paths['sampling']}（先跑 train_split_config extract "
              f"--release {args.release}）", flush=True)
        return 2
    rollout_dir = REPO_ROOT / paths["rollout"]
    if rollout_dir.exists() and not (rollout_dir / "results.jsonl").is_file() and not args.dry_run:
        print(f"PIPELINE_FAIL step=precheck 实跑目录已存在但没有 results.jsonl（上次中断？）：{paths['rollout']}；"
              "请人工检查后移走再重跑", flush=True)
        return 2
    for step in steps:
        if step["skip"]:
            print(f"PIPELINE_STEP {step['name']} skip（--resume，产物已存在）", flush=True)
            continue
        print(f"PIPELINE_STEP {step['name']} start :: " + " ".join(step["cmd"][1:]), flush=True)
        code = subprocess.run(step["cmd"], cwd=REPO_ROOT).returncode
        if code != 0:
            print(f"PIPELINE_FAIL step={step['name']} exit={code}", flush=True)
            return code
        print(f"PIPELINE_STEP {step['name']} done", flush=True)
    print(f"PIPELINE_DONE run_id={args.run_id} report={paths['report'] / 'generation_report.md'}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="只读产物，输出 V5_GENERATION 判定行、markdown 与 JSON")
    rep.add_argument("--drafts", required=True)
    rep.add_argument("--specs", default=None)
    rep.add_argument("--rollout", required=True, help="实跑某一轮的目录（含 results.jsonl 与 episodes/）")
    rep.add_argument("--candidates-per-env", type=int, default=10)
    rep.add_argument("--band-min", type=int, default=DEMO_BAND[0])
    rep.add_argument("--band-max", type=int, default=DEMO_BAND[1])
    rep.add_argument("--out", required=True, help="报告目录（写 generation_report.md / .json，可覆盖）")
    rep.set_defaults(func=cmd_report)
    pipe = sub.add_parser("pipeline", help="一条命令：draw → freeze → run → report")
    pipe.add_argument("--run-id", required=True)
    pipe.add_argument("--release", default=DEFAULT_RELEASE)
    pipe.add_argument("--label", default=DEFAULT_LABEL)
    pipe.add_argument("--tasks", default="all")
    pipe.add_argument("--candidates-per-env", type=int, default=10)
    pipe.add_argument("--max-reset-attempts", type=int, default=30)
    pipe.add_argument("--select", default=",".join(map(str, DEFAULT_SELECT)))
    pipe.add_argument("--draw-workers", type=int, default=1, help="抽签并行进程数（v4_specs draw --workers）")
    pipe.add_argument("--draw-gpus", default=None, help="抽签子进程轮转使用的物理 GPU，如 0,1")
    pipe.add_argument("--workers", type=int, default=1, help="实跑并行 worker 数（v4_rollout run --workers）")
    pipe.add_argument("--rollout-gpu", default="0", help="实跑 GPU 号（v4_rollout run --gpu）")
    pipe.add_argument("--official-root", default="artifacts/train-parity/local-smoke-01/official-src")
    pipe.add_argument("--resume", action="store_true", help="已有产物的步骤跳过（下游步骤仍会重新核验来源）")
    pipe.add_argument("--dry-run", action="store_true", help="只打印四步命令，不执行")
    pipe.set_defaults(func=cmd_pipeline)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
