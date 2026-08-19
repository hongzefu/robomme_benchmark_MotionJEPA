#!/usr/bin/env python3
"""clip 级事件标签：并入 episode_map，并守卫 chunk 级判正规则。

**主标签轴是 `event_slots`**：每条 clip 恰好包含一个事件 —— 第一次 swap 换了哪两个槽位。
标签由「物体的相对位置」描述（槽位对、中心距、方位角），**不含颜色**。`topo_class` 从
主标签降级为**协变量**：最近邻约束下 cross_diagonal 恒为空、Button 侧更是单一取值，
已不具备判别力（详见 clip_plan 模块 docstring 的「最近邻约束」一节）。

chunk 级标签**不再落盘**（2026-08-19）：在 110 帧 clip 上 `grid_starts(110) =
[0,16,32,48,64]` 只有 5 个 chunk，按 ε=0.10 第 0 个为负、其余 4 个为正，区分度极低；
判正规则是纯函数（`grid_starts` + `chunk_progress`），要用随时能从 h5 现算。真正有信息
量的是 clip 级事件类别，它连同全部协变量并入 `episode_map_{Task}.json`。

判正规则（与旧链路逐字相同，口径唯一定义处）：chunk `[s, s+span]` 在任一 swap 窗口
`[a, b)` 内推进的 smoothstep 进度增量 `smoothstep((min(s+span,b)-a)/(b-a)) −
smoothstep((max(s,a)-a)/(b-a))` 的最大值 > ε 判 1。

为什么不用简单窗口重叠：`swap_flat_two_lane` 的 smooth=True 让窗口末尾几帧几乎不动，
人眼判「没在 swap」——几何重叠规则会在窗口尾部多打假正例。规则须先过 `--regression`：
对官方 train ep90-99 复算标签、与 v7 人工资产逐条比对，全对才准使用。

两种模式：
* `--regression`：规则回归（只读官方 h5 与 v7 JSON，不动任何产物；用 **env step** 窗口）；
* 默认：把派生标签增补进 merge_clip_h5.py 产出的 `episode_map_{Task}.json`。
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
    load_metadata_record,
    native_window_slots,
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


def contact_fields(contacts: dict) -> dict:
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

    这里把它量化成三个可过滤的字段：

    * `action_group`：同源内按 joint_action **逐位相同**划分的等价组 id；
    * `action_dev_max`：该 clip 与同源其他全部变体的 joint_action 最大绝对差（rad）
      —— 0 表示同源内动作全都一致。**要无泄露子集就筛这个字段 == 0**；
    * `action_group_identifies_label`：该源的等价组数 == 变体数（每组只剩 1 条）⇒
      关节角可**完全反推**标签。

    ⚠ 最近邻约束把同源变体压到 2~3 条之后，旧口径那句「取同一 action_group 即得无泄露
    子集」已名存实亡 —— 同源只有 2 条且分成 2 组时，「同一组」只剩 1 条。所以下游一律
    用 `action_dev_max == 0` 筛选，并用 `action_group_identifies_label` 识别彻底泄露的源。
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
    identifies_label = len(representatives) == len(indices) and len(indices) > 1
    return {
        index: {
            "action_group": assigned[index],
            "action_group_size": sizes[assigned[index]],
            "action_group_identifies_label": identifies_label,
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
                # v7 人工资产只覆盖官方 train ep90-99 —— 本回归与扩源正交，显式钉死 train
                env_seed, difficulty = load_metadata_record(task, episode, "train")
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


# ── 数据集模式：把派生标签增补进 episode_map ──────────────────────────────────


def augment_episode_maps(
    input_dir: Path,
    tasks: Sequence[str],
    phase0_index: Path | None = None,
) -> dict:
    """把 6 个**不可从 episode_map 现有字段推出**的派生标签增补进 `episode_map_{Task}.json`。

    2026-08-19 起不再单独落 `clip_events.json` / `swap_labels_clip.json` /
    `swap_events_clip.json`：clip 级标签全部并进 `episode_map_{Task}.json`（它本来就带
    `event_slots` / `topo_class` / `pair_*` / 质量指标 / `contacts` 全套），它成为**唯一
    标签载体**。chunk 级标签不再落盘 —— 在 110 帧 clip 上只有 5 个 chunk、区分度极低
    （见模块 docstring），而判正规则是纯函数（`grid_starts` + `chunk_progress`），
    任何时候都能从 h5 现算，且仍由 `--regression` 守卫。

    增补的 6 个字段（其余如 `is_nn_pair` / `event_window_clip` / `swap_times` /
    `has_*_contact` 都是 map 里已有字段的一步推导，按「只留不可复算的」不再冗余落盘）：

    * `action_group` / `action_group_size` / `action_group_identifies_label` /
      `action_dev_max` —— 需跨同源变体逐位比较 joint_action 才能得到；
    * `later_windows_follow_native_nn` / `later_windows_native_slots` —— 需 Phase 0 读回的
      `original_idx1` 才能算「原版那一刻会换哪对槽位」。
    """
    # Phase 0 的 original_idx1：量化「窗口 ≥2 按槽位固定」对原版最近邻规则的偏离
    native_idx1: dict[tuple[str, str, int], list] = {}
    phase0_slot_xy: dict[tuple[str, str, int], list] = {}
    if phase0_index is not None and Path(phase0_index).is_file():
        for record in json.loads(Path(phase0_index).read_text(encoding="utf-8"))["records"]:
            if not record.get("split"):
                continue  # 旧版索引记录：视为几何不可用，绝不默认回填 train
            key = (str(record["split"]), str(record["task"]), int(record["episode"]))
            native_idx1[key] = record.get("original_idx1") or []
            phase0_slot_xy[key] = (record.get("geometry") or {}).get("slot_xy") or []

    all_records: list[dict] = []
    written: list[Path] = []
    for task in sorted(tasks):
        map_path = input_dir / f"episode_map_{task}.json"
        if not map_path.is_file():
            raise SystemExit(f"ERROR: 缺少 {map_path} —— 先跑 merge_clip_h5.py")
        payload = json.loads(map_path.read_text(encoding="utf-8"))
        episode_map = payload["records"]
        variant = SWAP_SCOPE[task]
        missing_split = [e["dense_episode"] for e in episode_map if not e.get("split")]
        if missing_split:
            raise SystemExit(
                f"ERROR: {map_path} 有 {len(missing_split)} 条记录无 split 字段（旧版产物）——"
                "请用新版链路重新合并"
            )
        with h5py.File(input_dir / f"record_dataset_{task}.h5", "r") as handle:
            # 同源分组键必须带 split：test/ep3 与 val/ep3 是无关源，混组会让
            # action_dev_max / action_group 全部算成垃圾且不报错
            by_source: dict[tuple[str, int], list[dict]] = {}
            for entry in episode_map:
                by_source.setdefault((entry["split"], entry["src_episode"]), []).append(entry)
            deviation = {
                (src_key, index): info
                for src_key, entries in by_source.items()
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
                        "映射与 h5 可能不是同批产物"
                    )
                frames = demo_prefix if variant == "demo" else exec_len
                if frames != CLIP_LEN:
                    raise SystemExit(
                        f"ERROR: {task}/episode_{dense} scope 段 {frames} 帧 ≠ 整段 clip {CLIP_LEN}"
                    )
                slot_pairs = [tuple(pair) for pair in entry["slot_pairs"]]

                # 窗口 ≥2 的两种口径对账（见 clip_plan.native_window_slots）：
                #   本链路 = 按槽位固定（后 30 帧跨变体一致的前提）
                #   原版   = 拿该窗口定死的 idx1(bin) 取当时的最近邻
                # 窗口 1 已把某些 bin 挪了位，两者不一定重合 —— 不重合不作废，逐条量化。
                key0 = (entry["split"], task, entry["src_episode"])
                later_native: list[list[int]] = []
                later_follows = None
                if native_idx1.get(key0) and phase0_slot_xy.get(key0):
                    later_follows = True
                    for widx in range(1, len(slot_pairs)):
                        idx1_bin = native_idx1[key0][widx] if widx < len(native_idx1[key0]) else None
                        if idx1_bin is None:
                            later_native.append([])
                            continue
                        native = native_window_slots(
                            phase0_slot_xy[key0], int(idx1_bin), slot_pairs[:widx]
                        )
                        later_native.append(list(native))
                        if native != slot_pairs[widx]:
                            later_follows = False

                entry["later_windows_follow_native_nn"] = later_follows
                entry["later_windows_native_slots"] = later_native
                entry.update(
                    deviation[((entry["split"], entry["src_episode"]), entry["variant_idx"])]
                )
                all_records.append({"task": task, **entry})

        payload["labels"] = _label_meta(task, episode_map)
        temporary = map_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(map_path)
        written.append(map_path)

    return {"records": all_records, "written": written}


def _label_meta(task: str, episode_map: Sequence[dict]) -> dict:
    """episode_map 里的标签说明块 —— 原 clip_events.json 的 meta，逐字保留。"""
    class_counts: dict[str, int] = {}
    topo_counts: dict[str, int] = {}
    per_source_legal: dict[str, list[str]] = {}
    for entry in episode_map:
        key = "".join(str(v) for v in entry["event_slots"])
        class_counts[key] = class_counts.get(key, 0) + 1
        topo_counts[entry["topo_class"]] = topo_counts.get(entry["topo_class"], 0) + 1
        per_source_legal[f"{entry['split']}/ep{entry['src_episode']}"] = [
            "".join(str(v) for v in pair) for pair in (entry["legal_event_slots"] or [])
        ]
    native_deviation = [
        {
            "dense_episode": entry["dense_episode"],
            "split": entry["split"],
            "src_episode": entry["src_episode"],
            "variant_idx": entry["variant_idx"],
            "event_slots": entry["event_slots"],
            "fixed_later_slots": [list(p) for p in entry["slot_pairs"][1:]],
            "native_later_slots": entry["later_windows_native_slots"],
        }
        for entry in episode_map
        if entry.get("later_windows_follow_native_nn") is False
    ]
    leaky_sources = sorted(
        {
            f"{entry['split']}/ep{entry['src_episode']}"
            for entry in episode_map
            if entry.get("action_group_identifies_label")
        }
    )
    return {
        "schema_version": 2,
        "scope": SWAP_SCOPE[task],
        "clip_len": CLIP_LEN,
        "env_step_offset": CLIP_START,
        "event_source": {"swap": "oracle"},
        "annotator": "oracle-swap-clips",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label_axis": "event_slots",
        "label": (
            "event_slots —— 第一次 swap 换了哪两个槽位；受最近邻约束"
            "（idx2 恒为 idx1 的严格最近邻），取值域 4 类：01/03/12/23"
        ),
        "covariates": [
            "topo_class", "pair_distance", "pair_azimuth", "pair_azimuth_local",
            "difficulty", "buttons", "src_episode", "env_seed",
        ],
        "constraint": {
            "name": "nearest_neighbor",
            "rule": "第一次 swap 的两个槽位中，其一必为另一之严格最近邻（平局取下标最小）",
            "source": "VideoUnmaskSwap.step / ButtonUnmaskSwap.step 的 pair_idx2 is None 分支",
            "relaxation": "idx1 不受原版 randperm/target_bin 耦合限制，可为任意 bin",
            "scope": "只作用于第一次 swap；窗口 ≥2 仍按槽位固定（后 30 帧跨变体一致）",
            "dead_code_warning": (
                "_compute_dynamic_swap_candidates / _select_swap_pair_from_positions"
                "（取最近两个再随机）全仓无调用点，不是真实机制，不得采信"
            ),
        },
        "per_source_legal_pairs": per_source_legal,
        "class_counts": class_counts,
        "class_balance_note": (
            "类别分布不均衡是最近邻约束的结构性后果，本数据集不做重采样、不做类别平衡；"
            "下游若要平衡须自行处理（可按 per_source_legal_pairs 做源内分层）"
        ),
        "topo_class_counts": topo_counts,
        "cross_diagonal_note": (
            "cross_diagonal 在旧的 train 8 源上恒为空 —— 实测事实、不是几何必然。"
            "扩源到 test/val 后若某源的对角对成为最近邻，它会正常入选并进验收告警"
            "（判据 10c-iii 已从硬失败降级为告警+计数）"
        ),
        "later_windows_deviating_from_native_nn": native_deviation,
        "later_windows_note": (
            "窗口 ≥2 本链路按槽位固定（后 30 帧跨变体一致的前提），原版则是拿该窗口"
            "定死的 idx1(bin) 取当时的最近邻。窗口 1 可能已把那个 bin 挪了位，所以两者"
            "不一定重合。上表逐条列出不重合的变体：它们的**事件本身**（第一次 swap）仍"
            "严格落在原版可达空间内，只是后 30 帧露出的第二次 swap 换的不是原版会换的"
            "那一对。下游若要求整条 clip 都原版可达，按 later_windows_follow_native_nn "
            "== true 过滤"
        ),
        "action_leak_sources": leaky_sources,
        "action_leak_note": (
            "这些源的每个 action_group 只剩 1 条 ⇒ 关节角可完全反推标签。"
            "要动作无泄露的子集，取 action_dev_max == 0 的记录，"
            "**不要**沿用旧口径「取同一 action_group」——同源只有 2 条时那会退化成 1 条"
        ),
        "chunk_label_note": (
            f"chunk 级标签不再落盘（110 帧 clip 只有 {len(grid_starts(CLIP_LEN))} 个 chunk、"
            f"区分度极低）；判正规则是纯函数 grid_starts + chunk_progress（ε={DEFAULT_EPSILON}），"
            "要用随时可从 h5 现算，规则本身由 make_clip_labels.py --regression 守卫"
        ),
        "note": (
            "每条 episode 是一段 110 帧 clip，恰含一个事件；标签只用相对位置，不含 cube 颜色；"
            "主轴是 event_slots，topo_class 是它的 4→2 粗化协变量。"
            "h5 内只嵌不可复算的 11 个 setup 字段（含 split）+ 8 个逐帧字段，派生标签一律以本文件为准"
        ),
        "n_records": len(episode_map),
    }


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
    parser.add_argument("--epsilon", type=float, default=DEFAULT_EPSILON)
    parser.add_argument(
        "--phase0-index",
        default=str(SCRIPT_DIR / "outputs" / "phase0" / "original_index.json"),
        help="Phase 0 索引；用于量化窗口 ≥2 相对原版最近邻规则的偏离",
    )
    args = parser.parse_args(argv)

    if args.regression:
        return run_regression(Path(args.swap_labels_v7), Path(args.official_h5_dir), args.epsilon)

    if not args.input_dir:
        print("ERROR: 数据集模式需要 --input-dir", file=sys.stderr)
        return 1
    input_dir = Path(args.input_dir).resolve()
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    result = augment_episode_maps(input_dir, tasks, Path(args.phase0_index))
    records = result["records"]

    class_counts: dict[str, int] = {}
    topo_counts: dict[str, int] = {}
    legal_pairs: dict[str, list[str]] = {}
    for record in records:
        key = "".join(str(v) for v in record["event_slots"])
        class_counts[key] = class_counts.get(key, 0) + 1
        topo_counts[record["topo_class"]] = topo_counts.get(record["topo_class"], 0) + 1
        legal_pairs[f"{record['task']}/{record['split']}/ep{record['src_episode']}"] = [
            "".join(str(v) for v in pair) for pair in (record["legal_event_slots"] or [])
        ]
    print(
        f"clip 级事件标签 {len(records)} 条 —— 主标签轴 event_slots："
        + "、".join(f"{name} {count}" for name, count in sorted(class_counts.items()))
    )
    print(
        "  协变量 topo_class（非主轴）："
        + "、".join(f"{name} {count}" for name, count in sorted(topo_counts.items()))
        + f"；cross_diagonal {topo_counts.get('cross_diagonal', 0)} 条"
        "（train 8 源实测恒空，非几何必然；非零会进验收告警）"
    )
    print("  逐源合法对：" + "  ".join(
        f"{key}={','.join(pairs)}" for key, pairs in sorted(legal_pairs.items())
    ))
    print("标签已并入：" + "、".join(path.name for path in result["written"]))

    clean = [r for r in records if r["action_dev_max"] == 0.0]
    by_task: dict[str, list[float]] = {}
    for record in records:
        by_task.setdefault(record["task"], []).append(record["action_dev_max"])
    print("动作通道泄露量化（action_dev_max = 与同源其他变体的 joint_action 最大差，rad）：")
    for task, values in sorted(by_task.items()):
        zero = sum(1 for v in values if v == 0.0)
        print(f"  {task}: {zero}/{len(values)} 条为 0，最大 {max(values):.3e}")
    print(f"  全体无泄露（action_dev_max==0）的 clip：{len(clean)}/{len(records)} 条")
    leaky = sorted(
        {
            f"{r['task']}/{r['split']}/ep{r['src_episode']}"
            for r in records if r.get("action_group_identifies_label")
        }
    )
    if leaky:
        print(
            "  ⚠ 关节角可完全反推标签的源（每个 action_group 只剩 1 条）：" + "、".join(leaky)
        )
    native_dev = [r for r in records if r.get("later_windows_follow_native_nn") is False]
    print(
        f"窗口 ≥2 与原版最近邻规则不重合：{len(native_dev)}/{len(records)} 条"
        "（事件本身仍全部落在原版可达空间内；要整条 clip 原版可达按 "
        "later_windows_follow_native_nn == true 过滤）"
    )

    contacts = [(r, contact_fields(r.get("contacts") or {})) for r in records]
    rb = [r for r, c in contacts if c["has_robot_bin_contact"]]
    bb = [(r, c) for r, c in contacts if c["has_bin_bin_contact"]]
    print("接触检测（物理引擎 get_contacts 实测，冲量 > 1e-9 才算）：")
    print(f"  机械臂 ↔ 容器：{len(rb)}/{len(records)} 条 —— 机器人是否被 swap 中的容器碰到")
    print(f"  容器 ↔ 容器  ：{len(bb)}/{len(records)} 条，全部落在第一次 swap 窗口内")
    # 最近邻子集里互撞条数极少，按 topo_class 分组统计已无意义 —— 直接逐条列出
    for record, fields in bb:
        print(
            f"    {record['task']}/{record['split']}/ep{record['src_episode']}/var{record['variant_idx']}"
            f" 事件={record['event_slots']} 互撞 {fields['contact_bin_bin_forceful_frames']} 帧"
            f"（最大冲量 {fields['contact_bin_bin_impulse_max']:.4g}）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
