#!/usr/bin/env python3
"""chunk 级 swap 标签：与 MotionJEPA `swap_labels_v7.json` 同构 schema + 富标签。

判正规则（口径唯一定义处）：chunk `[s, s+span]` 在任一 swap 窗口 `[a, b)` 内
推进的 smoothstep 进度增量 `smoothstep((min(s+span,b)-a)/(b-a)) −
smoothstep((max(s,a)-a)/(b-a))` 的最大值 > ε 判 1。

为什么不用简单窗口重叠：`swap_flat_two_lane` 的 smooth=True 让窗口末尾几帧
几乎不动，人眼判「没在 swap」——几何重叠规则会在 ButtonUnmaskSwap 每个
episode 的窗口尾部多打一个假正例。进度阈值规则须先过 `--regression`：
对官方 train ep90-99 复算标签，与 v7 人工资产 319 条逐条比对，全对才准使用。

两种模式：
* `--regression`：规则回归（只读官方 h5 与 v7 JSON，不动任何产物）；
* 默认：对 merge_variant_h5.py 的产物出两份标签 JSON。

段长口径：demo = `is_video_demo` 前缀长；exec = 段内首个 `is_completed` 真 + 2
（与 MotionJEPA build_data_raw 同源，从 h5 现算，不额外存长度）。
段内帧号 == env step（两个 scope 段都从 step 0 起），窗口无需换算。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import h5py

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from variant_plan import (  # noqa: E402
    compute_swap_times,
    load_train_record,
    swap_windows,
    variant_signature,
)
from variant_worker import _segment_lengths  # noqa: E402

# 与 MotionJEPA 侧 label_swap.py / viz_grid 完全一致的口径常量
SWAP_SCOPE = {"ButtonUnmaskSwap": "exec", "VideoUnmaskSwap": "demo"}
CHUNK_SPAN = 32
CHUNK_STEP = 16
DEFAULT_EPSILON = 0.10


def _smoothstep(alpha: float) -> float:
    alpha = min(max(alpha, 0.0), 1.0)
    return alpha * alpha * (3.0 - 2.0 * alpha)


def chunk_progress(
    start_frame: int, windows: Sequence[tuple[int, int]]
) -> tuple[float, int]:
    """chunk 在各窗口推进的最大 smoothstep 进度增量，与主导窗口下标（无则 -1）。"""
    best, best_idx = 0.0, -1
    lo, hi = start_frame, start_frame + CHUNK_SPAN
    for idx, (a, b) in enumerate(windows):
        if min(hi, b) <= max(lo, a):
            continue
        gained = _smoothstep((min(hi, b) - a) / (b - a)) - _smoothstep((max(lo, a) - a) / (b - a))
        if gained > best:
            best, best_idx = gained, idx
    return best, best_idx


def grid_starts(segment_frames: int) -> list[int]:
    """与 viz_grid.enumerate_points 同口径：range(0, num_chunks, step)，num_chunks = T−span。"""
    num_chunks = max(0, segment_frames - CHUNK_SPAN)
    return list(range(0, num_chunks, CHUNK_STEP))


def scope_segment_frames(task: str, total: int, demo_prefix: int, exec_len: int) -> int:
    return demo_prefix if SWAP_SCOPE[task] == "demo" else exec_len


# ── 回归模式：对官方数据复算标签，与 v7 人工资产逐条比对 ──────────────────────


def run_regression(v7_path: Path, official_dir: Path, epsilon: float) -> int:
    payload = json.loads(v7_path.read_text(encoding="utf-8"))
    manual = {
        (
            record["task"],
            int(record["episode"].removeprefix("ep")),
            record["variant"],
            int(record["start_frame"]),
        ): record
        for record in payload["records"]
    }
    episodes = sorted({key[1] for key in manual})
    tasks = sorted({key[0] for key in manual})
    print(f"v7 资产 {len(manual)} 条，覆盖 {tasks} × ep{episodes[0]}-{episodes[-1]}")

    computed: dict[tuple, int] = {}
    for task in tasks:
        with h5py.File(official_dir / f"record_dataset_{task}.h5", "r") as handle:
            for episode in episodes:
                group = handle[f"episode_{episode}"]
                total, demo_prefix, exec_len = _segment_lengths(group)
                env_seed, difficulty = load_train_record(task, episode)
                windows = swap_windows(compute_swap_times(env_seed, difficulty))
                frames = scope_segment_frames(task, total, demo_prefix, exec_len)
                for start in grid_starts(frames):
                    progress, _ = chunk_progress(start, windows)
                    computed[(task, episode, SWAP_SCOPE[task], start)] = int(progress > epsilon)

    only_manual = sorted(set(manual) - set(computed))
    only_computed = sorted(set(computed) - set(manual))
    if only_manual or only_computed:
        print(f"ERROR: 网格主键不对齐：v7 独有 {len(only_manual)} 条、复算独有 {len(only_computed)} 条", file=sys.stderr)
        for key in (only_manual + only_computed)[:10]:
            print(f"  {key}", file=sys.stderr)
        return 2

    mismatches = [
        (key, manual[key]["swap"], computed[key], manual[key].get("labeled"))
        for key in sorted(manual)
        if int(manual[key]["swap"]) != computed[key]
    ]
    print(
        f"规则 ε={epsilon}：{len(manual) - len(mismatches)}/{len(manual)} 与人工标注一致，"
        f"失配 {len(mismatches)} 条"
    )
    for key, human, ours, labeled in mismatches[:20]:
        print(f"  失配 {key}: 人工={human} 复算={ours} labeled={labeled}")
    return 0 if not mismatches else 1


# ── 数据集模式：对合并产物出两份标签 JSON ─────────────────────────────────────


def build_labels(
    input_dir: Path, dataset_name: str, epsilon: float, tasks: Sequence[str] | None = None
) -> tuple[dict, dict]:
    records_binary = []
    records_rich = []
    episode_ranges = []
    for task in sorted(tasks if tasks is not None else SWAP_SCOPE):
        map_path = input_dir / f"episode_map_{task}.json"
        if not map_path.is_file():
            raise SystemExit(f"ERROR: 缺少 {map_path} —— 先跑 merge_variant_h5.py")
        episode_map = json.loads(map_path.read_text(encoding="utf-8"))["records"]
        h5_file = input_dir / f"record_dataset_{task}.h5"
        variant = SWAP_SCOPE[task]
        with h5py.File(h5_file, "r") as handle:
            for entry in episode_map:
                dense = entry["dense_episode"]
                group = handle[f"episode_{dense}"]
                total, demo_prefix, exec_len = _segment_lengths(group)
                if (total, demo_prefix, exec_len) != (
                    entry["n_timesteps"],
                    entry["demo_prefix"],
                    entry["exec_len"],
                ):
                    raise SystemExit(
                        f"ERROR: {task}/episode_{dense} 段长与 episode_map 不符——"
                        "manifest 与 h5 可能不是同批产物"
                    )
                pairs = [tuple(pair) for pair in entry["pairs"]]
                windows = swap_windows(len(pairs))
                swap_end = windows[-1][1]
                frames = scope_segment_frames(task, total, demo_prefix, exec_len)
                if frames < swap_end:
                    raise SystemExit(
                        f"ERROR: {task}/episode_{dense} scope 段 {frames} 帧 < swap 结束 {swap_end}"
                    )
                for start in grid_starts(frames):
                    progress, window_idx = chunk_progress(start, windows)
                    swap = int(progress > epsilon)
                    base = {
                        "task": task,
                        "episode": f"ep{dense}",
                        "variant": variant,
                        "start_frame": start,
                    }
                    records_binary.append({**base, "swap": swap, "labeled": True})
                    records_rich.append(
                        {
                            **base,
                            "swap": swap,
                            "progress": round(progress, 4),
                            "window_idx": window_idx,
                            "pair": list(pairs[window_idx]) if window_idx >= 0 else None,
                            "swap_kind": variant_signature([pairs[window_idx]])
                            if window_idx >= 0
                            else "none",
                            "episode_signature": entry["signature"],
                            "src_episode": entry["src_episode"],
                            "variant_idx": entry["variant_idx"],
                            "env_seed": entry["env_seed"],
                            "variant_seed": entry["variant_seed"],
                            "difficulty": entry["difficulty"],
                            "net_permutation": entry["net_permutation"],
                            "is_identity_net": entry["net_permutation"]
                            == sorted(entry["net_permutation"]),
                            "is_original": entry["is_original"],
                            "min_clearance": entry["min_clearance"],
                            "bystander_net_max": entry["bystander_net_max"],
                            "disturbed_bins": entry["disturbed_bins"],
                            "pickup_hold_step": entry.get("pickup_hold_step"),
                        }
                    )
        episode_ranges.append(f"{task}:0-{len(episode_map) - 1}")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta_common = {
        "schema_version": 1,
        "dataset": dataset_name,
        "key": ["task", "episode", "variant", "start_frame"],
        "scope": dict(SWAP_SCOPE),
        "episodes": ";".join(episode_ranges),
        "chunk_span": CHUNK_SPAN,
        "chunk_step": CHUNK_STEP,
        "event_source": {"swap": "oracle"},
        "annotator": "oracle-swap-variants",
        "epsilon": epsilon,
        "created_at": now,
        "updated_at": now,
    }
    binary = {"meta": {**meta_common, "n_records": len(records_binary)}, "records": records_binary}
    rich = {
        "meta": {**meta_common, "schema_note": "富标签，供子事件分析；二值口径与同名 binary 文件逐条一致",
                 "n_records": len(records_rich)},
        "records": records_rich,
    }
    return binary, rich


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成/回归 chunk 级 swap 标签")
    parser.add_argument("--regression", action="store_true", help="规则回归模式（不产标签）")
    parser.add_argument(
        "--swap-labels-v7",
        default="/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA/docs/labels/swap_labels_v7.json",
    )
    parser.add_argument("--official-h5-dir", default="/data/hongzefu/robomme_data_h5")
    parser.add_argument("--input-dir", default=None, help="merge_variant_h5.py 的输出目录")
    parser.add_argument("--tasks", default=",".join(sorted(SWAP_SCOPE)))
    parser.add_argument("--dataset-name", default="dataset-swapvar")
    parser.add_argument("--epsilon", type=float, default=DEFAULT_EPSILON)
    args = parser.parse_args(argv)

    if args.regression:
        return run_regression(
            Path(args.swap_labels_v7), Path(args.official_h5_dir), args.epsilon
        )

    if not args.input_dir:
        print("ERROR: 数据集模式需要 --input-dir", file=sys.stderr)
        return 1
    input_dir = Path(args.input_dir).resolve()
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    binary, rich = build_labels(input_dir, args.dataset_name, args.epsilon, tasks)
    binary_path = input_dir / "swap_labels_swapvar.json"
    rich_path = input_dir / "swap_events_swapvar.json"
    binary_path.write_text(json.dumps(binary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rich_path.write_text(json.dumps(rich, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    positives = sum(record["swap"] for record in binary["records"])
    print(
        f"标签已写出：{binary_path.name} / {rich_path.name}，"
        f"共 {len(binary['records'])} 条 chunk（swap=1 有 {positives} 条）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
