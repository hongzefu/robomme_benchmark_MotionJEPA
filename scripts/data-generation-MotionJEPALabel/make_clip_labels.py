#!/usr/bin/env python3
"""clip 级事件标签（主）+ chunk 级二值/富标签（兼容 MotionJEPA v7 schema）。

**主标签是 clip 级的多类事件**：每条 clip 恰好包含一个事件 —— 第一次 swap 换了哪两个
槽位。标签由「物体的相对位置」描述（槽位对、拓扑类别、中心距、方位角），**不含颜色**。

chunk 级二值标签仍然出一份供 `load_manual_swap` 零改动读取，但要注意它在 clip 上区分度
很低：`grid_starts(110) = [0,16,32,48,64]` 只有 5 个 chunk，按 ε=0.10 规则第 0 个为负、
其余 4 个为正（48 clip → 240 条、192 正）。真正有信息量的是 clip 级事件类别。

判正规则（与旧链路逐字相同，口径唯一定义处）：chunk `[s, s+span]` 在任一 swap 窗口
`[a, b)` 内推进的 smoothstep 进度增量 `smoothstep((min(s+span,b)-a)/(b-a)) −
smoothstep((max(s,a)-a)/(b-a))` 的最大值 > ε 判 1。

为什么不用简单窗口重叠：`swap_flat_two_lane` 的 smooth=True 让窗口末尾几帧几乎不动，
人眼判「没在 swap」——几何重叠规则会在窗口尾部多打假正例。规则须先过 `--regression`：
对官方 train ep90-99 复算标签、与 v7 人工资产逐条比对，全对才准使用。

两种模式：
* `--regression`：规则回归（只读官方 h5 与 v7 JSON，不动任何产物；用 **env step** 窗口）；
* 默认：对 merge_clip_h5.py 的产物出三份标签 JSON（用 **clip 帧号**窗口）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from clip_plan import (  # noqa: E402
    CLIP_LEN,
    CLIP_START,
    compute_swap_times,
    load_train_record,
    swap_windows_clip,
    swap_windows_env,
)
from clip_worker import segment_lengths, sorted_timesteps  # noqa: E402

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
    return list(range(0, max(0, segment_frames - CHUNK_SPAN), CHUNK_STEP))


# ── 接触检测字段（物理引擎实测） ──────────────────────────────────────────────


def _contact_fields(contacts: dict) -> dict:
    """把 clip 的接触统计摊平进标签。判据说明见 swap_inject.contact_summary。

    * `contact_robot_bin_*` —— 机械臂连杆 ↔ 容器。2026-08-18 全量实测 **0/48 条**，
      机器人从未被 swap 中的容器碰到；
    * `contact_bin_bin_*` —— 容器互撞（交换中的两个容器相撞，或撞上被锁定的旁观容器）。
      这是 clip 内实际发生的物理接触，也是 ButtonUnmaskSwap 动作分叉的源头：
      它改变 PhysX 的接触求解，间接让机械臂-按钮的接触力数值解发生变化；
    * `contact_robot_button_*` —— 机械臂 ↔ 按钮，任务本身的接触，对照基线。

    `*_frames` 含零冲量的接触候选（PhysX 把贴近的物体也配成接触对），
    **判「真的撞上了」一律用 `*_forceful_frames`**。
    """
    return {
        "contact_robot_bin_forceful_frames": contacts.get("robot_bin_forceful_frames", 0),
        "contact_robot_bin_impulse_max": contacts.get("robot_bin_impulse_max", 0.0),
        "contact_bin_bin_forceful_frames": contacts.get("bin_bin_forceful_frames", 0),
        "contact_bin_bin_event_forceful_frames": contacts.get(
            "bin_bin_event_forceful_frames", 0
        ),
        "contact_bin_bin_impulse_max": contacts.get("bin_bin_impulse_max", 0.0),
        "contact_bin_bin_onset_clip_frame": (
            contacts["bin_bin_onset_env_step"] - CLIP_START
            if contacts.get("bin_bin_onset_env_step", -1) >= 0
            else -1
        ),
        "contact_bin_bin_forceful_pairs": contacts.get("bin_bin_forceful_pairs") or [],
        "contact_robot_button_forceful_frames": contacts.get(
            "robot_button_forceful_frames", 0
        ),
        # 一句话结论：这条 clip 里有没有检测到物理接触，分别是哪一类
        "has_robot_bin_contact": bool(contacts.get("robot_bin_forceful_frames", 0)),
        "has_bin_bin_contact": bool(contacts.get("bin_bin_forceful_frames", 0)),
    }


# ── 动作通道泄露的量化（ButtonUnmaskSwap 的已知问题） ────────────────────────


def action_deviation(handle: h5py.File, entries: Sequence[dict]) -> dict[int, dict]:
    """同源变体之间的 joint_action 偏差与「动作等价组」。

    背景（实测）：机械臂**从未**被 swap 中的容器碰到（接触检测实测 0/48）。真正的链条是
    **交换中的两个容器互撞**（20/48 条）改变了 PhysX 的接触求解规模与顺序，进而让机械臂-按钮
    的接触力数值解发生变化 —— ep95/var2 实测 env 70 起 bin_0↔bin_3 持续接触、env 79
    button_cap↔panda_finger 的冲量出现差异、关节角从严格 0.0 突跳到 4.7e-5 后指数增长，
    到 env 88 时 `solve_button` 的第 2/3 段规划以偏离后的关节角为起点，指令随之分叉，
    最大差 1.6e-1 rad（≈9°）。于是机器人动作与 swap 内容产生确定性对应，构成
    **动作通道的信息泄露**。VideoUnmaskSwap 不受影响（demo 段 `solve_hold_obj` 开环发
    同一指令、不做规划，实测严格 0.0）。

    这里把它量化成两个可过滤的字段：

    * `action_group`：同源内按 joint_action **逐位相同**划分的等价组 id
      —— 下游只取同一组，就能得到动作完全无泄露的子集；
    * `action_dev_max`：该 clip 与同源其他全部变体的 joint_action 最大绝对差（rad）
      —— 0 表示同源内动作全都一致。
    """
    actions: dict[int, np.ndarray] = {}
    for entry in entries:
        group = handle[f"episode_{entry['dense_episode']}"]
        actions[entry["variant_idx"]] = np.stack(
            [
                np.asarray(group[name]["action"]["joint_action"], dtype=np.float64)
                for name in sorted_timesteps(group)
            ]
        )
    indices = sorted(actions)
    assigned: dict[int, int] = {}
    representatives: list[np.ndarray] = []
    for index in indices:
        for gid, rep in enumerate(representatives):
            if np.array_equal(actions[index], rep):
                assigned[index] = gid
                break
        else:
            assigned[index] = len(representatives)
            representatives.append(actions[index])
    sizes: dict[int, int] = {}
    for gid in assigned.values():
        sizes[gid] = sizes.get(gid, 0) + 1
    return {
        index: {
            "action_group": assigned[index],
            "action_group_size": sizes[assigned[index]],
            "action_dev_max": round(
                max(
                    (float(np.max(np.abs(actions[index] - actions[other]))) for other in indices if other != index),
                    default=0.0,
                ),
                6,
            ),
        }
        for index in indices
    }


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
                total, demo_prefix, exec_len = segment_lengths(group)
                env_seed, difficulty = load_train_record(task, episode)
                windows = swap_windows_env(compute_swap_times(env_seed, difficulty))
                frames = demo_prefix if SWAP_SCOPE[task] == "demo" else exec_len
                for start in grid_starts(frames):
                    progress, _ = chunk_progress(start, windows)
                    computed[(task, episode, SWAP_SCOPE[task], start)] = int(progress > epsilon)

    only_manual = sorted(set(manual) - set(computed))
    only_computed = sorted(set(computed) - set(manual))
    if only_manual or only_computed:
        print(
            f"ERROR: 网格主键不对齐：v7 独有 {len(only_manual)} 条、复算独有 {len(only_computed)} 条",
            file=sys.stderr,
        )
        for key in (only_manual + only_computed)[:10]:
            print(f"  {key}", file=sys.stderr)
        return 2

    mismatches = [
        (key, manual[key]["swap"], computed[key])
        for key in sorted(manual)
        if int(manual[key]["swap"]) != computed[key]
    ]
    print(
        f"规则 ε={epsilon}：{len(manual) - len(mismatches)}/{len(manual)} 与人工标注一致，"
        f"失配 {len(mismatches)} 条"
    )
    for key, human, ours in mismatches[:20]:
        print(f"  失配 {key}: 人工={human} 复算={ours}")
    return 0 if not mismatches else 1


# ── 数据集模式：对合并产物出三份标签 JSON ─────────────────────────────────────


def build_labels(input_dir: Path, dataset_name: str, epsilon: float, tasks: Sequence[str]):
    clip_records = []
    chunk_binary = []
    chunk_rich = []
    episode_ranges = []
    for task in sorted(tasks):
        map_path = input_dir / f"episode_map_{task}.json"
        if not map_path.is_file():
            raise SystemExit(f"ERROR: 缺少 {map_path} —— 先跑 merge_clip_h5.py")
        episode_map = json.loads(map_path.read_text(encoding="utf-8"))["records"]
        variant = SWAP_SCOPE[task]
        with h5py.File(input_dir / f"record_dataset_{task}.h5", "r") as handle:
            by_source: dict[int, list[dict]] = {}
            for entry in episode_map:
                by_source.setdefault(entry["src_episode"], []).append(entry)
            deviation = {
                (src, index): info
                for src, entries in by_source.items()
                for index, info in action_deviation(handle, entries).items()
            }
            for entry in episode_map:
                dense = entry["dense_episode"]
                group = handle[f"episode_{dense}"]
                total, demo_prefix, exec_len = segment_lengths(group)
                if (total, demo_prefix, exec_len) != (
                    entry["n_timesteps"], entry["demo_prefix"], entry["exec_len"]
                ):
                    raise SystemExit(
                        f"ERROR: {task}/episode_{dense} 段长与 episode_map 不符——"
                        "manifest 与 h5 可能不是同批产物"
                    )
                frames = demo_prefix if variant == "demo" else exec_len
                if frames != CLIP_LEN:
                    raise SystemExit(
                        f"ERROR: {task}/episode_{dense} scope 段 {frames} 帧 ≠ 整段 clip {CLIP_LEN}"
                    )
                slot_pairs = [tuple(pair) for pair in entry["slot_pairs"]]
                windows = swap_windows_clip(len(slot_pairs))

                # ── 主标签：clip 级事件（一条 clip 一个事件） ──
                clip_records.append(
                    {
                        "task": task,
                        "episode": f"ep{dense}",
                        "event_slots": entry["event_slots"],
                        "topo_class": entry["topo_class"],
                        "pair_distance": entry["pair_distance"],
                        "pair_azimuth": entry["pair_azimuth"],
                        "pair_azimuth_local": entry["pair_azimuth_local"],
                        "event_window_clip": list(windows[0]),
                        "slot_xy": entry["slot_xy"],
                        "reference_axis_deg": entry["reference_axis_deg"],
                        "src_episode": entry["src_episode"],
                        "variant_idx": entry["variant_idx"],
                        "env_seed": entry["env_seed"],
                        "variant_seed": entry["variant_seed"],
                        "is_original": entry["is_original"],
                        # 协变量（跨源变化、非标签目标）
                        "difficulty": entry["difficulty"],
                        "swap_times": len(slot_pairs),
                        "buttons": entry.get("buttons"),
                        # 质量指标
                        "min_clearance": entry["min_clearance"],
                        "bystander_net_max": entry["bystander_net_max"],
                        "disturbed_bins": entry["disturbed_bins"],
                        # 动作通道泄露的量化：同组内 joint_action 逐位相同
                        **deviation[(entry["src_episode"], entry["variant_idx"])],
                        # 接触检测（物理引擎 get_contacts 实测，见 swap_inject）
                        **_contact_fields(entry.get("contacts") or {}),
                    }
                )

                # ── 兼容标签：chunk 级二值 + 富标签 ──
                for start in grid_starts(frames):
                    progress, window_idx = chunk_progress(start, windows)
                    swap = int(progress > epsilon)
                    base = {
                        "task": task,
                        "episode": f"ep{dense}",
                        "variant": variant,
                        "start_frame": start,
                    }
                    chunk_binary.append({**base, "swap": swap, "labeled": True})
                    chunk_rich.append(
                        {
                            **base,
                            "swap": swap,
                            "progress": round(progress, 4),
                            "window_idx": window_idx,
                            "slots": list(slot_pairs[window_idx]) if window_idx >= 0 else None,
                            "is_event_window": window_idx == 0,
                            "event_slots": entry["event_slots"],
                            "topo_class": entry["topo_class"],
                            "signature": entry["signature"],
                            "src_episode": entry["src_episode"],
                            "variant_idx": entry["variant_idx"],
                            "is_original": entry["is_original"],
                            "min_clearance": entry["min_clearance"],
                        }
                    )
        episode_ranges.append(f"{task}:0-{len(episode_map) - 1}")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta_common = {
        "schema_version": 1,
        "dataset": dataset_name,
        "scope": dict(SWAP_SCOPE),
        "episodes": ";".join(episode_ranges),
        "clip_len": CLIP_LEN,
        "env_step_offset": CLIP_START,
        "event_source": {"swap": "oracle"},
        "annotator": "oracle-swap-clips",
        "created_at": now,
        "updated_at": now,
    }
    clip_payload = {
        "meta": {
            **meta_common,
            "key": ["task", "episode"],
            "label": "event_slots / topo_class —— 第一次 swap 换了哪两个槽位",
            "note": "每条 clip 恰含一个事件；标签只用相对位置，不含 cube 颜色",
            "n_records": len(clip_records),
        },
        "records": clip_records,
    }
    binary_payload = {
        "meta": {
            **meta_common,
            "key": ["task", "episode", "variant", "start_frame"],
            "chunk_span": CHUNK_SPAN,
            "chunk_step": CHUNK_STEP,
            "epsilon": epsilon,
            "n_records": len(chunk_binary),
        },
        "records": chunk_binary,
    }
    rich_payload = {
        "meta": {
            **binary_payload["meta"],
            "schema_note": "富标签；二值口径与同名 binary 文件逐条一致",
            "n_records": len(chunk_rich),
        },
        "records": chunk_rich,
    }
    return clip_payload, binary_payload, rich_payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成/回归 clip 级事件标签与 chunk 级标签")
    parser.add_argument("--regression", action="store_true", help="规则回归模式（不产标签）")
    parser.add_argument(
        "--swap-labels-v7",
        default="/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA/docs/labels/swap_labels_v7.json",
    )
    parser.add_argument("--official-h5-dir", default="/data/hongzefu/robomme_data_h5")
    parser.add_argument("--input-dir", default=None, help="merge_clip_h5.py 的输出目录")
    parser.add_argument("--tasks", default=",".join(sorted(SWAP_SCOPE)))
    parser.add_argument("--dataset-name", default="dataset-swapclip-event1")
    parser.add_argument("--epsilon", type=float, default=DEFAULT_EPSILON)
    args = parser.parse_args(argv)

    if args.regression:
        return run_regression(Path(args.swap_labels_v7), Path(args.official_h5_dir), args.epsilon)

    if not args.input_dir:
        print("ERROR: 数据集模式需要 --input-dir", file=sys.stderr)
        return 1
    input_dir = Path(args.input_dir).resolve()
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    clip_payload, binary_payload, rich_payload = build_labels(
        input_dir, args.dataset_name, args.epsilon, tasks
    )
    for name, payload in (
        ("clip_events.json", clip_payload),
        ("swap_labels_clip.json", binary_payload),
        ("swap_events_clip.json", rich_payload),
    ):
        (input_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    positives = sum(record["swap"] for record in binary_payload["records"])
    counts: dict[str, int] = {}
    for record in clip_payload["records"]:
        counts[record["topo_class"]] = counts.get(record["topo_class"], 0) + 1
    print(
        f"clip 级事件标签 {len(clip_payload['records'])} 条："
        + "、".join(f"{name} {count}" for name, count in sorted(counts.items()))
    )
    print(
        f"chunk 级标签 {len(binary_payload['records'])} 条（swap=1 有 {positives} 条）"
        f"；三份 JSON 已写入 {input_dir}"
    )
    clean = [r for r in clip_payload["records"] if r["action_dev_max"] == 0.0]
    by_task: dict[str, list[float]] = {}
    for record in clip_payload["records"]:
        by_task.setdefault(record["task"], []).append(record["action_dev_max"])
    print("动作通道泄露量化（action_dev_max = 与同源其他变体的 joint_action 最大差，rad）：")
    for task, values in sorted(by_task.items()):
        zero = sum(1 for v in values if v == 0.0)
        print(f"  {task}: {zero}/{len(values)} 条为 0，最大 {max(values):.3e}")
    print(f"  全体无泄露（action_dev_max==0）的 clip：{len(clean)}/{len(clip_payload['records'])} 条")
    total = len(clip_payload["records"])
    rb = [r for r in clip_payload["records"] if r["has_robot_bin_contact"]]
    bb = [r for r in clip_payload["records"] if r["has_bin_bin_contact"]]
    print("接触检测（物理引擎 get_contacts 实测，冲量 > 1e-9 才算）：")
    print(f"  机械臂 ↔ 容器：{len(rb)}/{total} 条 —— 机器人是否被 swap 中的容器碰到")
    print(f"  容器 ↔ 容器  ：{len(bb)}/{total} 条，全部落在第一次 swap 窗口内")
    by_topo: dict[str, list[int]] = {}
    for record in clip_payload["records"]:
        by_topo.setdefault(record["topo_class"], []).append(
            int(record["has_bin_bin_contact"])
        )
    for name, flags in sorted(by_topo.items()):
        print(f"    {name}: {sum(flags)}/{len(flags)} 条检测到容器互撞")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
