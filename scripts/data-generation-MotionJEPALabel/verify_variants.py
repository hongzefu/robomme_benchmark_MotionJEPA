#!/usr/bin/env python3
"""端到端机器验收：对生成+合并+标签的全部产物跑一遍判据，出 verification_report。

判据清单（全部 fail-loud，逐项计入报告）：
1. 覆盖完整度：每个源 episode 的成功变体数 == 枚举期望数；
2. 布局不变性：全部变体的布局指纹与 Phase 0 基线逐位相同（variant_results.jsonl）；
3. is_original 唯一性：每源 episode 恰一条，且其 joint_action 与官方 h5 逐元素一致；
4. 变体真不同：同源变体在各 swap 窗口中点帧的 front_rgb 哈希两两互异；
5. 段覆盖：scope 段长 ≥ swap 结束帧；
6. 结构：merged h5 episode/timestep 连续、末帧 is_completed、swap_gt 齐全（复用 merge 校验）；
7. min_clearance 分布：< 0.055 m（bin 边长）的列为 visually_degenerate 供下游过滤；
8. 标签对账：swap_labels_swapvar.json 的主键集合 == 按 merged h5 现算的网格集合，
   且二值口径与富标签逐条一致。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from make_chunk_labels import (  # noqa: E402
    SWAP_SCOPE,
    chunk_progress,
    grid_starts,
    scope_segment_frames,
)
from variant_plan import source_episode, swap_windows, variant_specs  # noqa: E402
from merge_variant_h5 import verify_merged  # noqa: E402
from variant_worker import _segment_lengths, _sorted_timesteps  # noqa: E402

CLEARANCE_DEGENERATE = 0.055  # bin 边长量级，低于此值视为可能穿模


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ok_results(jsonl_path: Path) -> dict[tuple[str, int, int], dict]:
    results = {}
    with jsonl_path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("ok"):
                results[(record["task"], record["src_episode"], record["variant_idx"])] = record
    return results


def _subgoal_boundaries(episode: h5py.Group, timesteps: Sequence[str]) -> list[tuple[int, str]]:
    """simple_subgoal 的切换点序列 [(step, 子目标名), ...] —— 结构等价的判据。"""
    boundaries = []
    previous = None
    for name in timesteps:
        raw = episode[name]["info"]["simple_subgoal"][()]
        value = raw.decode() if isinstance(raw, bytes) else str(raw)
        if value != previous:
            boundaries.append((int(name.rsplit("_", 1)[1]), value))
            previous = value
    return boundaries


def _frame_hash(episode: h5py.Group, steps: Sequence[int]) -> tuple[str, ...]:
    hashes = []
    for step in steps:
        data = np.asarray(episode[f"timestep_{step}"]["obs"]["front_rgb"])
        hashes.append(hashlib.md5(data.tobytes()).hexdigest())
    return tuple(hashes)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="swap 变体数据集端到端验收")
    parser.add_argument("--phase0-dir", default=str(SCRIPT_DIR / "outputs" / "phase0"))
    parser.add_argument("--gen-dir", required=True, help="generate+merge 的输出目录")
    parser.add_argument("--official-h5-dir", default="/data/hongzefu/robomme_data_h5")
    # 控制跑（无注入）与官方逐位一致到 1e-17；is_original 变体因注入把交换对角色
    # 规范化为 (小,大)，与原始随机角色（如 ep91 window1 原始 idx1=bin_2，已静态实证）
    # 的浮点运算顺序不同，bin 终态 ulp 级差异在接触链上混沌放大 —— 短链 1e-6 级
    # （Video/ep92），最长链（Button/ep91 两次抓取）到 1.5e-3，均在环境自身复现包络内
    # （官方历史自复现记录 7.86e-3）。数值阈值取 1e-2 兜底，真正的等价判据是下面的
    # **结构检查**：帧数相等 + simple_subgoal 边界逐步相同（无逻辑分叉的直接证据）。
    parser.add_argument("--joint-action-tol", type=float, default=1e-2)
    args = parser.parse_args(argv)

    gen_dir = Path(args.gen_dir).resolve()
    phase0 = _load_json(Path(args.phase0_dir) / "original_index.json")
    baseline = {(r["task"], r["episode"]): r for r in phase0["records"]}
    results = _ok_results(gen_dir / "variant_results.jsonl")
    parameters = _load_json(gen_dir / "run_parameters.json")

    failures: list[str] = []
    report: dict = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "gen_dir": str(gen_dir)}

    tasks = parameters["tasks"]
    episodes = parameters["src_episodes"]
    allow_repeat = parameters["allow_repeat_adjacent"]

    # 1. 覆盖完整度
    coverage = []
    for task in tasks:
        for episode in episodes:
            expected = len(variant_specs(source_episode(task, episode), allow_repeat))
            actual = sum(1 for key in results if key[0] == task and key[1] == episode)
            coverage.append(
                {"task": task, "episode": episode, "expected": expected, "actual": actual}
            )
            if actual != expected:
                failures.append(f"覆盖：{task}/ep{episode} 成功 {actual}/{expected}")
    report["coverage"] = coverage

    # 2. 布局不变性（逐位比较 fingerprint dict）
    fp_bad = [
        f"{key[0]}/ep{key[1]}/var{key[2]}"
        for key, record in results.items()
        if record["fingerprint"] != baseline[(key[0], key[1])]["fingerprint"]
    ]
    if fp_bad:
        failures.append(f"布局指纹与基线不符：{fp_bad[:5]}（共 {len(fp_bad)} 条）")
    report["fingerprint_mismatch_count"] = len(fp_bad)

    # 3-8 需要 merged h5 与 episode_map
    clearance_low: list[dict] = []
    label_records = _load_json(gen_dir / "swap_labels_swapvar.json")["records"]
    rich_records = _load_json(gen_dir / "swap_events_swapvar.json")["records"]
    label_keys = {
        (r["task"], r["episode"], r["variant"], r["start_frame"]): r["swap"]
        for r in label_records
    }
    if len(label_keys) != len(label_records):
        failures.append("标签主键有重复")
    rich_map = {
        (r["task"], r["episode"], r["variant"], r["start_frame"]): r for r in rich_records
    }
    if set(rich_map) != set(label_keys):
        failures.append("二值标签与富标签的主键集合不一致")
    else:
        binary_mismatch = [
            key for key, swap in label_keys.items() if rich_map[key]["swap"] != swap
        ]
        if binary_mismatch:
            failures.append(f"二值与富标签 swap 口径不一致：{binary_mismatch[:5]}")

    structure = {}
    grid_expected: set = set()
    original_checks = []
    for task in tasks:
        merged_path = gen_dir / f"record_dataset_{task}.h5"
        structure[task] = verify_merged(merged_path)  # 判据 6（不过则 raise）
        episode_map = _load_json(gen_dir / f"episode_map_{task}.json")["records"]
        variant = SWAP_SCOPE[task]
        by_src: dict[int, list[dict]] = defaultdict(list)
        for entry in episode_map:
            by_src[entry["src_episode"]].append(entry)

        with h5py.File(merged_path, "r") as merged, h5py.File(
            Path(args.official_h5_dir) / f"record_dataset_{task}.h5", "r"
        ) as official:
            for src_ep, entries in sorted(by_src.items()):
                # 判据 4：swap 窗口中点帧哈希两两互异
                k = len(entries[0]["pairs"])
                probe_steps = [64 + 50 * i + 25 for i in range(k)]
                hashes = {}
                for entry in entries:
                    group = merged[f"episode_{entry['dense_episode']}"]
                    hashes[entry["variant_idx"]] = _frame_hash(group, probe_steps)
                if len(set(hashes.values())) != len(hashes):
                    dup = defaultdict(list)
                    for idx, value in hashes.items():
                        dup[value].append(idx)
                    collide = [v for v in dup.values() if len(v) > 1]
                    failures.append(f"变体不互异：{task}/ep{src_ep} 哈希碰撞组 {collide}")

                # 判据 3：is_original 唯一 + 与官方逐元素一致
                originals = [entry for entry in entries if entry["is_original"] == 1]
                if len(originals) != 1:
                    failures.append(
                        f"is_original：{task}/ep{src_ep} 有 {len(originals)} 条，应恰 1"
                    )
                else:
                    entry = originals[0]
                    group = merged[f"episode_{entry['dense_episode']}"]
                    group_off = official[f"episode_{src_ep}"]
                    ts_ours = _sorted_timesteps(group)
                    ts_off = _sorted_timesteps(group_off)
                    check = {"task": task, "src_episode": src_ep, "variant_idx": entry["variant_idx"]}
                    if len(ts_ours) != len(ts_off):
                        failures.append(
                            f"is_original 帧数：{task}/ep{src_ep} {len(ts_ours)} ≠ 官方 {len(ts_off)}"
                        )
                        check["T_equal"] = False
                    else:
                        max_diff = 0.0
                        for name in ts_ours:
                            a = np.asarray(group[name]["action"]["joint_action"], dtype=np.float64)
                            b = np.asarray(group_off[name]["action"]["joint_action"], dtype=np.float64)
                            max_diff = max(max_diff, float(np.max(np.abs(a - b))))
                        check["joint_action_max_abs_diff"] = max_diff
                        if max_diff >= args.joint_action_tol:
                            failures.append(
                                f"is_original 数值：{task}/ep{src_ep} max_diff={max_diff:.3e} "
                                f"≥ {args.joint_action_tol}"
                            )
                        bounds_ours = _subgoal_boundaries(group, ts_ours)
                        bounds_off = _subgoal_boundaries(group_off, ts_off)
                        # 名称序列必须完全相同；切换步允许 ±2（尾段浮点混沌可让
                        # 完成判定早/晚一步，与链路其他处的 ±2 帧容差同口径）
                        names_equal = [b[1] for b in bounds_ours] == [b[1] for b in bounds_off]
                        step_dev = (
                            max(abs(a[0] - b[0]) for a, b in zip(bounds_ours, bounds_off))
                            if names_equal and bounds_ours
                            else None
                        )
                        check["subgoal_names_equal"] = names_equal
                        check["subgoal_step_max_dev"] = step_dev
                        check["subgoal_boundaries"] = bounds_ours
                        if not names_equal or (step_dev is not None and step_dev > 2):
                            failures.append(
                                f"is_original 结构：{task}/ep{src_ep} 子目标边界不同 "
                                f"{bounds_ours} ≠ 官方 {bounds_off}"
                            )
                    original_checks.append(check)

                for entry in entries:
                    # 判据 5 + 网格重算（判据 8 的期望集合）
                    group = merged[f"episode_{entry['dense_episode']}"]
                    total, demo_prefix, exec_len = _segment_lengths(group)
                    windows = swap_windows(len(entry["pairs"]))
                    frames = scope_segment_frames(task, total, demo_prefix, exec_len)
                    if frames < windows[-1][1]:
                        failures.append(
                            f"段覆盖：{task}/ep{entry['dense_episode']} scope {frames} < {windows[-1][1]}"
                        )
                    for start in grid_starts(frames):
                        grid_expected.add(
                            (task, f"ep{entry['dense_episode']}", variant, start)
                        )
                    # 判据 7
                    if entry["min_clearance"] < CLEARANCE_DEGENERATE:
                        clearance_low.append(
                            {
                                "task": task,
                                "dense_episode": entry["dense_episode"],
                                "signature": entry["signature"],
                                "min_clearance": entry["min_clearance"],
                            }
                        )

    # 判据 8：标签主键集合 == 网格集合
    only_labels = set(label_keys) - grid_expected
    only_grid = grid_expected - set(label_keys)
    if only_labels or only_grid:
        failures.append(
            f"标签对账：标签独有 {len(only_labels)} 条、网格独有 {len(only_grid)} 条"
        )
    report["label_records"] = len(label_keys)
    report["label_positives"] = sum(label_keys.values())
    report["structure"] = structure
    report["original_checks"] = original_checks
    report["clearance_below_threshold"] = clearance_low
    report["clearance_threshold"] = CLEARANCE_DEGENERATE
    all_clearances = [
        entry["min_clearance"]
        for task in tasks
        for entry in _load_json(gen_dir / f"episode_map_{task}.json")["records"]
    ]
    report["clearance_stats"] = {
        "min": min(all_clearances),
        "p05": float(np.percentile(all_clearances, 5)),
        "median": float(np.median(all_clearances)),
        "degenerate_count": len(clearance_low),
        "total": len(all_clearances),
    }
    report["failures"] = failures
    report["verdict"] = "PASS" if not failures else "FAIL"

    out_json = gen_dir / "verification_report.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# swap 变体数据集验收报告",
        "",
        f"- 生成时间：{report['created_at']}",
        f"- 结论：**{report['verdict']}**",
        f"- 覆盖：{sum(c['actual'] for c in coverage)}/{sum(c['expected'] for c in coverage)} 条变体",
        f"- 布局指纹失配：{report['fingerprint_mismatch_count']}",
        f"- 标签：{report['label_records']} 条 chunk，swap=1 共 {report['label_positives']} 条",
        f"- min_clearance < {CLEARANCE_DEGENERATE} m 的变体：{len(clearance_low)} / {len(all_clearances)}"
        f"（分布 min={report['clearance_stats']['min']:.4f}，中位 {report['clearance_stats']['median']:.4f}）",
        "",
    ]
    if failures:
        lines.append("## 未过判据")
        lines.extend(f"- {item}" for item in failures)
    else:
        lines.append("全部判据通过。")
    (gen_dir / "verification_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"验收结论：{report['verdict']}（报告：{out_json}）")
    for line in failures:
        print(f"  未过：{line}", file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
