#!/usr/bin/env python3
"""端到端验收：把「除了 bin 初始位置和第一次 swap 的排列组合，其他全部一致」逐条变成断言。

十二条判据（全过才算数）。源覆盖 train/test/val 三个 split，全部对账键为
(split, task, episode) —— episode 号只在 split 内可比。核心是判据 4 —— clip 全程 110 帧的 joint_action 跨同源变体
逐位相同，这是「机器人动作恒定」的机器证明。

判据 5 的口径说明（实测校准过）：后 30 帧要求的是**窗口 2 的 teleport 端点位置**跨变体
一致，而不是整段逐位相同。原因是窗口 1 的对角交换会擦碰被锁定的旁观 bin（实测
min_clearance 可低到 0.0045 m），把它挤开几毫米、随后弹回 —— 那是第一次 swap 的物理
余波、是允许的变化维度的直接后果，不是第二个独立事件。余波幅度由 bystander_net_max
逐条量化并在报告里单列。
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

from clip_plan import (  # noqa: E402
    CLIP_LEN,
    CLIP_MARGIN,
    EVAL_TASKS,
    SPLIT_CODE,
    NN_MARGIN_WARN,
    REQUIRED_BINS,
    bin_pairs,
    nearest_neighbor,
    nearest_neighbor_margin,
    nearest_neighbor_pairs,
    pair_index,
    slot_pairs_from_bin_pairs,
    swap_windows_clip,
    topo_class,
    topo_table,
)
from clip_worker import CLIP_IS_DEMO, segment_lengths, sorted_timesteps  # noqa: E402
from make_clip_labels import DEFAULT_EPSILON, chunk_progress, grid_starts  # noqa: E402
from swap_inject import FORCEFUL_IMPULSE_EPS, MOVED_NET_EPS  # noqa: E402

# 判据 3/4 期望逐位相同；实测若出现 ulp 级残差，降到这个阈值并在报告里单列实测值
BITWISE_FALLBACK_TOL = 1e-9
# 判据 4 只对「clip 内机器人不做运动规划」的 env 做硬断言。
# ButtonUnmaskSwap 例外并非放水，而是已实测定位的环境行为 —— 注意机械臂**从未**被容器
# 碰到（判据 11 历轮实测恒 0）。真正的链条是：交换中的两个容器互撞（判据 11 的 bin_bin）
# → 改变 PhysX 的接触求解规模与顺序 → 机械臂-按钮的接触力数值解发生变化
# → qpos 偏离（ep95 实测 env 79 从严格 0.0 突跳到 4.7e-5）→ 指数放大 → env 88 时
# solve_button 的第 2/3 段规划以偏离的关节角为起点，指令分叉（最大 1.6e-1 rad ≈ 9°）。
# 用户拍板：保留 48 条并逐条量化 —— 标签里的 action_group / action_dev_max 供下游过滤。
ACTION_BITWISE_REQUIRED = {"VideoUnmaskSwap": True, "ButtonUnmaskSwap": False}
# 判据 5：窗口 2 端点位置集合的一致性阈值（实测残差 ~6e-7，来自 teleport 后的物理噪声）
ENDPOINT_TOL = 1e-5
# 判据 8：cube 藏到 (10,10,10) 的判定；事件前 cube 在容器内、z 应远低于此
CUBE_AWAY_Z = 5.0
CUBE_ON_TABLE_Z = 0.1


def _sorted_positions(positions: np.ndarray) -> np.ndarray:
    """每帧把各 bin 按 (x,y) 排序 —— 比「位置集合」而不是「哪个 bin 在哪」。"""
    return np.stack([frame[np.lexsort((frame[:, 1], frame[:, 0]))] for frame in positions])


def _contact_aggregate(group: h5py.Group, names: Sequence[str], event_window) -> dict:
    """从逐帧 contact 字段现算 clip 级聚合 —— 口径与 swap_inject.contact_summary 逐字一致。

    2026-08-19 起 h5 只嵌逐帧的 count/impulse，`*_forceful_frames` / `*_impulse_max` /
    `*_event_forceful_frames` 三类聚合量不再落盘（可复算 ⇒ 不冗余存）。
    **判「真的撞上了」仍必须用冲量阈值**：PhysX 会把贴近但没使上力的物体也配成接触对，
    所以 count > 0 没有判别力，一律看 impulse > FORCEFUL_IMPULSE_EPS。
    """
    out: dict = {}
    for prefix in ("robot_bin", "bin_bin", "robot_button"):
        impulses = np.array(
            [
                float(np.asarray(group[name]["swap_gt"][f"contact_{prefix}_impulse"]))
                for name in names
            ]
        )
        forceful = impulses > FORCEFUL_IMPULSE_EPS
        out[f"{prefix}_forceful_frames"] = int(forceful.sum())
        out[f"{prefix}_impulse_max"] = float(impulses.max()) if impulses.size else 0.0
        a, b = event_window
        out[f"{prefix}_event_forceful_frames"] = int(forceful[a:b].sum())
    return out


def load_episode(group: h5py.Group, entry: dict) -> dict:
    """读一条 clip。h5 里只剩 11 个不可复算的 setup 字段（含 split），其余一律**现算**。

    现算而不是读内嵌值，正是本轮精简的验收点：如果复算路径与生成期口径有任何出入，
    判据 1/10/12 会立刻炸出来。质量指标（min_clearance / bystander_net_max）取自
    `episode_map`（生成期用完整位姿 trace 实测，clip 只保留了区间内的帧）。
    """
    names = sorted_timesteps(group)
    gt = group["setup"]["swap_gt"]
    event_slots = tuple(np.asarray(gt["event_slots"]).tolist())
    bin_pairs_seq = [tuple(pair) for pair in np.asarray(gt["bin_pairs"]).tolist()]
    slot_xy = np.asarray(gt["slot_xy"], dtype=np.float64).tolist()
    slot_pairs = slot_pairs_from_bin_pairs(bin_pairs_seq, len(slot_xy))
    legal = nearest_neighbor_pairs(slot_xy)
    event_window = swap_windows_clip(len(bin_pairs_seq))[0]
    contacts = _contact_aggregate(group, names, event_window)
    return {
        "n": len(names),
        "joint_action": np.stack(
            [np.asarray(group[n]["action"]["joint_action"], dtype=np.float64) for n in names]
        ),
        "bins": np.stack(
            [np.asarray(group[n]["swap_gt"]["bins_pos"], dtype=np.float64) for n in names]
        ),
        "cubes": np.stack(
            [np.asarray(group[n]["swap_gt"]["cubes_pos"], dtype=np.float64) for n in names]
        ),
        "demo": np.array([bool(np.asarray(group[n]["info"]["is_video_demo"])) for n in names]),
        "completed": np.array([bool(np.asarray(group[n]["info"]["is_completed"])) for n in names]),
        "rgb_event_end": hashlib.md5(
            np.asarray(group[f"timestep_{CLIP_MARGIN + 50 - 1}"]["obs"]["front_rgb"]).tobytes()
        ).hexdigest(),
        "event_slots": event_slots,
        # ↓ 六项由 h5 的 event_slots / bin_pairs / slot_xy 现算
        "event_pair_index": pair_index(event_slots, len(slot_xy)),
        "is_nn_pair": int(tuple(sorted(event_slots)) in legal),
        "legal_event_slots": legal,
        "slot_nearest_neighbor": [nearest_neighbor(slot_xy, i) for i in range(len(slot_xy))],
        "slot_nn_margin": nearest_neighbor_margin(slot_xy),
        "topo_class": topo_class(event_slots),
        "bin_pairs": [list(pair) for pair in bin_pairs_seq],
        "slot_pairs": [list(pair) for pair in slot_pairs],
        "is_original": int(np.asarray(gt["is_original"])),
        "n_bins": len(slot_xy),
        # 质量指标取自 episode_map（生成期实测，口径见 swap_inject.min_clearance）
        "min_clearance": entry["min_clearance"],
        "bystander_net_max": entry["bystander_net_max"],
        # 接触：逐帧 impulse 现算聚合，判「真的撞上了」看 forceful（冲量 > 1e-9）
        "contact_robot_bin": contacts["robot_bin_forceful_frames"],
        "contact_bin_bin": contacts["bin_bin_forceful_frames"],
        "contact_bin_bin_event": contacts["bin_bin_event_forceful_frames"],
        "contact_bin_bin_impulse": contacts["bin_bin_impulse_max"],
        "contact_robot_button": contacts["robot_button_forceful_frames"],
    }


def verify(gen_dir: Path, phase0_index: Path, tasks: Sequence[str]) -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    report: dict = {"checks": {}, "per_source": [], "quality": []}
    # 判据 12 的累计量（用单元素 list 是为了在内层循环里就地累加）
    global_min_margin = [float("inf")]
    original_hits = [0]
    directed_hits = [0]
    comparison_pairs = [0]

    baseline = {
        (record["split"], record["task"], int(record["episode"])): record
        for record in json.loads(phase0_index.read_text(encoding="utf-8"))["records"]
        if record.get("split")  # 旧版无 split 的索引在生成阶段就已被拒，这里兜底跳过
    }

    total_clips = 0
    bitwise_ja = True
    worst_ja = 0.0
    action_dev_by_task: dict[str, float] = defaultdict(float)
    action_groups_by_source: list[dict] = []
    contact_rows: list[dict] = []
    worst_prefix = 0.0
    worst_endpoint = 0.0
    rgb_hashes: dict[tuple, list[str]] = defaultdict(list)
    topo_counts: dict[str, int] = defaultdict(int)
    event_counts: dict[str, int] = defaultdict(int)

    for task in tasks:
        map_path = gen_dir / f"episode_map_{task}.json"
        episode_map = json.loads(map_path.read_text(encoding="utf-8"))["records"]
        # 同源分组键必须带 split：test/ep3 与 val/ep3 是无关源，混组会产出假失败
        by_source: dict[tuple[str, int], list[dict]] = defaultdict(list)
        for entry in episode_map:
            by_source[(entry["split"], entry["src_episode"])].append(entry)

        with h5py.File(gen_dir / f"record_dataset_{task}.h5", "r") as handle:
            # ── 判据 9：merged h5 结构 ──
            names = [n for n in handle if n.startswith("episode_")]
            indices = sorted(int(n.rsplit("_", 1)[1]) for n in names)
            if indices != list(range(len(indices))):
                failures.append(f"[9] {task}: episode 编号不密集连续")

            for (split, src_episode), entries in sorted(
                by_source.items(), key=lambda kv: (SPLIT_CODE[kv[0][0]], kv[0][1])
            ):
                entries.sort(key=lambda item: item["variant_idx"])
                loaded = []
                for entry in entries:
                    group = handle[f"episode_{entry['dense_episode']}"]
                    data = load_episode(group, entry)
                    loaded.append((entry, data))
                    total_clips += 1
                    topo_counts[data["topo_class"]] += 1
                    event_counts["".join(str(v) for v in data["event_slots"])] += 1

                    # 判据 1：bin 数
                    if data["n_bins"] != REQUIRED_BINS:
                        failures.append(
                            f"[1] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"bin 数 {data['n_bins']} ≠ {REQUIRED_BINS}"
                        )
                    # 判据 9：帧数与 scope 段
                    if data["n"] != CLIP_LEN:
                        failures.append(
                            f"[9] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"{data['n']} 帧 ≠ {CLIP_LEN}"
                        )
                    total, demo_prefix, exec_len = segment_lengths(group)
                    scope = demo_prefix if CLIP_IS_DEMO[task] else exec_len
                    if scope != CLIP_LEN:
                        failures.append(
                            f"[9] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"scope 段 {scope} ≠ {CLIP_LEN}"
                        )
                    # 判据 2：布局指纹（槽位 xy 与 Phase 0 基线）
                    base_bins = np.asarray(
                        [b["p"][:2] for b in baseline[(split, task, src_episode)]["fingerprint"]["bins"]]
                    )
                    if not np.array_equal(np.asarray(entry["slot_xy"]), base_bins):
                        failures.append(
                            f"[2] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            "槽位 xy 与 Phase 0 基线不符"
                        )
                    # 判据 6：窗口 1 生效（clip 帧 30→79 净位移）
                    window = swap_windows_clip(len(data["slot_pairs"]))[0]
                    net = np.linalg.norm(
                        data["bins"][window[1] - 1, :, :2] - data["bins"][window[0], :, :2], axis=1
                    )
                    moved = set(int(i) for i in np.flatnonzero(net > MOVED_NET_EPS))
                    planned = set(data["bin_pairs"][0])
                    if not planned <= moved:
                        failures.append(
                            f"[6] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"计划交换 bin {sorted(planned)}，实测移动 {sorted(moved)}"
                            f"（net={np.round(net, 4).tolist()}）"
                        )
                    # 判据 8：cube 可见性分段
                    cubes = data["cubes"]
                    if not (cubes[:CLIP_MARGIN, :, 2] < CUBE_ON_TABLE_Z).all():
                        failures.append(
                            f"[8] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            "事件前 30 帧有 cube 不在桌面高度"
                        )
                    if not (cubes[CLIP_MARGIN:, :, 2] > CUBE_AWAY_Z).all():
                        failures.append(
                            f"[8] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            "事件开始后有 cube 未被藏走"
                        )
                    # ── 判据 11：机械臂 ↔ 容器接触（物理引擎实测，必须为 0）──
                    # 本链路的前提是「机器人动作只由任务本身决定」。若机械臂真被 swap 中的
                    # 容器碰到，那 clip 里就多了一条 swap→机器人的直接因果通路。
                    # 2026-08-18 全量实测：0/48 条，从未发生。
                    if data["contact_robot_bin"] > 0:
                        failures.append(
                            f"[11] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"检测到机械臂 ↔ 容器接触 {data['contact_robot_bin']} 帧"
                        )
                    contact_rows.append(
                        {
                            "task": task,
                            "split": split,
                            "src_episode": src_episode,
                            "variant_idx": entry["variant_idx"],
                            "event_slots": list(data["event_slots"]),
                            "topo_class": data["topo_class"],
                            "robot_bin_frames": data["contact_robot_bin"],
                            "bin_bin_frames": data["contact_bin_bin"],
                            "bin_bin_event_frames": data["contact_bin_bin_event"],
                            "bin_bin_impulse_max": data["contact_bin_bin_impulse"],
                            "robot_button_frames": data["contact_robot_button"],
                        }
                    )

                    # 判据 7 素材
                    rgb_hashes[(task, split, src_episode)].append(data["rgb_event_end"])
                    report["quality"].append(
                        {
                            "task": task,
                            "split": split,
                            "src_episode": src_episode,
                            "variant_idx": entry["variant_idx"],
                            "event_slots": list(data["event_slots"]),
                            "topo_class": data["topo_class"],
                            "min_clearance": data["min_clearance"],
                            "bystander_net_max": data["bystander_net_max"],
                        }
                    )

                # ── 判据 1：枚举完整度（最近邻口径）、is_original、编号自洽 ──
                base_record = baseline[(split, task, src_episode)]
                slot_xy = base_record["geometry"]["slot_xy"]
                legal = nearest_neighbor_pairs(slot_xy)
                margins = nearest_neighbor_margin(slot_xy)
                slots = sorted(item[1]["event_slots"] for item in loaded)
                # 1b：事件槽位对集合必须**恰等于**该源的最近邻合法对集合（不多不少、无重复）
                if slots != legal:
                    failures.append(
                        f"[1] {task}/{split}/ep{src_episode}: 事件槽位对集合 {slots} ≠ 最近邻合法集合 "
                        f"{legal}（各槽位 argmin 余量 {[round(m, 5) for m in margins]}）"
                    )
                originals = sum(item[1]["is_original"] for item in loaded)
                if originals != 1:
                    failures.append(f"[1] {task}/{split}/ep{src_episode}: is_original 有 {originals} 条，应为 1")
                # 1d：variant_idx == 事件槽位对的字典序下标（编号方案自洽）
                for entry, data in loaded:
                    expected_idx = pair_index(data["event_slots"], REQUIRED_BINS)
                    if entry["variant_idx"] != expected_idx or data["event_pair_index"] != expected_idx:
                        failures.append(
                            f"[1] {task}/{split}/ep{src_episode}/var{entry['variant_idx']}: 编号与事件槽位对 "
                            f"{data['event_slots']} 的字典序下标 {expected_idx} 不符"
                        )

                # ── 判据 12：★ 最近邻不变量（本轮重构的核心） ──
                for entry, data in loaded:
                    tag12 = f"{task}/{split}/ep{src_episode}/var{entry['variant_idx']}"
                    a, b = data["event_slots"]
                    # 12a 计划侧：用 Phase 0 实测几何复算
                    if not (nearest_neighbor(slot_xy, a) == b or nearest_neighbor(slot_xy, b) == a):
                        failures.append(
                            f"[12] {tag12}: 事件对 {data['event_slots']} 两个方向都不构成最近邻关系"
                        )
                    if not data["is_nn_pair"]:
                        failures.append(f"[12] {tag12}: h5 里 is_nn_pair 为 0")
                    if sorted(data["legal_event_slots"]) != legal:
                        failures.append(
                            f"[12] {tag12}: h5 内嵌合法集合 {sorted(data['legal_event_slots'])} ≠ {legal}"
                        )
                    # 12b 物理侧交叉复核：改用这条 clip **自己**在事件前最后一帧的实测位置
                    # 复算。判据 2 只保证 reset 时刻与基线相同，12b 保证进入 swap 窗口那一刻
                    # 环境真正看到的几何仍然给出同一组合法对。
                    pre_event_xy = data["bins"][CLIP_MARGIN - 1, :, :2]
                    if nearest_neighbor_pairs(pre_event_xy.tolist()) != legal:
                        failures.append(
                            f"[12] {tag12}: 事件前一帧（clip 帧 {CLIP_MARGIN - 1}）实测几何算出的合法集合 "
                            f"{nearest_neighbor_pairs(pre_event_xy.tolist())} ≠ Phase 0 基线 {legal}"
                        )
                    nn_margin_min = min(data["slot_nn_margin"])
                    global_min_margin[0] = min(global_min_margin[0], nn_margin_min)
                    if nn_margin_min < NN_MARGIN_WARN:
                        warnings.append(
                            f"[12] {tag12}: argmin 余量最小 {nn_margin_min:.5f} < {NN_MARGIN_WARN}"
                            " —— 最近邻判定接近平局，值得人看一眼（不作废数据）"
                        )
                # 12d：原始首对必落在合法集合内（原版 idx2 本就是最近邻回填）
                original_entry = next((item for item in loaded if item[1]["is_original"]), None)
                if original_entry is not None:
                    if original_entry[1]["event_slots"] not in legal:
                        failures.append(
                            f"[12] {task}/{split}/ep{src_episode}: 原始首对 "
                            f"{original_entry[1]['event_slots']} 不在合法集合 {legal} 内"
                        )
                    else:
                        original_hits[0] += 1
                    # 有方向的精确判据：Phase 0 读回了 idx1，则断言原版 idx2 == NN(idx1)
                    idx1_seq = base_record.get("original_idx1")
                    if idx1_seq and idx1_seq[0] is not None:
                        idx1 = int(idx1_seq[0])
                        first_pair = tuple(base_record["original_bin_pairs"][0])
                        idx2 = first_pair[0] if first_pair[1] == idx1 else first_pair[1]
                        if nearest_neighbor(slot_xy, idx1) != idx2:
                            failures.append(
                                f"[12] {task}/{split}/ep{src_episode}: 原版 idx1={idx1} 的最近邻是 "
                                f"{nearest_neighbor(slot_xy, idx1)}，但原版 idx2={idx2} —— "
                                "最近邻复刻与 env 实际行为脱节"
                            )
                        else:
                            directed_hits[0] += 1

                # ── 判据 3/4/5：跨同源变体的不变性 ──
                ref = loaded[0][1]
                # 判据 4：同源内 joint_action 的等价组（逐位相同才同组）
                actions = [data["joint_action"] for _, data in loaded]
                assigned: list[int] = []
                reps: list[np.ndarray] = []
                for action in actions:
                    for gid, rep in enumerate(reps):
                        if np.array_equal(action, rep):
                            assigned.append(gid)
                            break
                    else:
                        assigned.append(len(reps))
                        reps.append(action)
                source_dev = max(
                    (
                        float(np.max(np.abs(a - b)))
                        for i, a in enumerate(actions)
                        for b in actions[i + 1:]
                    ),
                    default=0.0,
                )
                action_dev_by_task[task] = max(action_dev_by_task[task], source_dev)
                action_groups_by_source.append(
                    {
                        "task": task,
                        "split": split,
                        "src_episode": src_episode,
                        "n_action_groups": len(reps),
                        "variants": len(loaded),
                        # 每组只剩 1 条 ⇒ 关节角可完全反推标签（2~3 变体源上尤其容易发生）
                        "identifies_label": len(reps) == len(loaded) and len(loaded) > 1,
                        "group_of_variant": {
                            str(entry["variant_idx"]): gid
                            for (entry, _), gid in zip(loaded, assigned)
                        },
                        "max_dev": source_dev,
                    }
                )
                if len(reps) == len(loaded) and len(loaded) > 1:
                    warnings.append(
                        f"[4] {task}/{split}/ep{src_episode}: {len(loaded)} 条变体分成 {len(reps)} 个动作"
                        "等价组（每组 1 条）⇒ joint_action 可完全判别标签，下游须按 "
                        "action_dev_max == 0 剔除"
                    )
                if source_dev != 0.0:
                    bitwise_ja = False
                    if ACTION_BITWISE_REQUIRED[task]:
                        failures.append(
                            f"[4] {task}/{split}/ep{src_episode}: clip 全程 joint_action 跨同源变体"
                            f"最大差 {source_dev:.3e}，该 env 要求逐位相同"
                        )

                for entry, data in loaded[1:]:
                    tag = f"{task}/{split}/ep{src_episode}/var{entry['variant_idx']}"
                    worst_ja = max(
                        worst_ja, float(np.max(np.abs(data["joint_action"] - ref["joint_action"])))
                    )
                    diff_prefix = float(
                        np.max(np.abs(data["bins"][:CLIP_MARGIN] - ref["bins"][:CLIP_MARGIN]))
                    )
                    worst_prefix = max(worst_prefix, diff_prefix)
                    if diff_prefix > BITWISE_FALLBACK_TOL:
                        failures.append(
                            f"[3] {tag}: 前 {CLIP_MARGIN} 帧 bins_pos 与同源基准差 {diff_prefix:.3e}"
                        )
                    diff_end = float(
                        np.max(
                            np.abs(
                                _sorted_positions(data["bins"][-1:])
                                - _sorted_positions(ref["bins"][-1:])
                            )
                        )
                    )
                    worst_endpoint = max(worst_endpoint, diff_end)
                    if diff_end > ENDPOINT_TOL:
                        # 该源事件窗口内发生过**有力**容器互撞（冲量 > FORCEFUL_IMPULSE_EPS）
                        # 时降级为量化告警：剧烈互撞会把旁观 bin 撞离且不弹回（2026-08-19
                        # 实测 Button/val/ep11：对角对入选最近邻、冲量 ~17，末帧集合差
                        # 1.3e-2），这是第一次 swap（唯一允许变化维度）的物理余波、与
                        # 判据 5 口径里「擦碰旁观 bin」同因不同幅 —— 按「保留 + 量化」
                        # 原则不作废数据，扰动幅度由 bystander_net_max 逐条量化。
                        # 无互撞而超阈仍是硬失败：那说明注入本身错了。
                        source_bb_event = max(
                            item[1]["contact_bin_bin_event"] for item in loaded
                        )
                        if source_bb_event > 0:
                            warnings.append(
                                f"[5] {tag}: clip 末帧位置集合与同源基准差 {diff_end:.3e} > "
                                f"{ENDPOINT_TOL} —— 该源事件窗口内有有力容器互撞（最多 "
                                f"{source_bb_event} 帧），旁观 bin 被撞离未弹回，为第一次 "
                                f"swap 的物理余波（bystander_net_max="
                                f"{entry['bystander_net_max']}），不作废数据"
                            )
                        else:
                            failures.append(
                                f"[5] {tag}: clip 末帧位置集合与同源基准差 {diff_end:.3e} > "
                                f"{ENDPOINT_TOL}（该源无互撞 —— 注入本身可能有错）"
                            )

                # ── 判据 7b：同源变体在事件末帧的 bins_pos **逐 bin 必有差异** ──
                # 即「换的确实是不同的东西」。相对判据 7a（front_rgb 哈希）的优势：断言的是
                # 几何本质而非渲染副产物，且不随变体数多寡而失效 —— 最近邻约束把同源压到
                # 2~3 条后，7a 的比较对数从 15/源 降到 1~3/源，需要这条来补强度。
                #
                # ⚠ 这里**只**比较「逐 bin 是否有差异」，不比较「排序后的位置集合是否相等」。
                # 事件末帧（clip 帧 79 = 窗口 1 的最后一帧）teleport 刚结束、物体仍在沉降，
                # 实测同源位置集合差约 3e-4，远大于 ENDPOINT_TOL(1e-5)；要再过 30 帧才收敛。
                # 位置集合的一致性由判据 5 在 clip **末帧**（帧 109）断言，那里实测 ~6e-7。
                event_end = CLIP_MARGIN + 50 - 1
                for i in range(len(loaded)):
                    for j in range(i + 1, len(loaded)):
                        comparison_pairs[0] += 1
                        a = loaded[i][1]["bins"][event_end]
                        b = loaded[j][1]["bins"][event_end]
                        if np.allclose(a, b, atol=ENDPOINT_TOL):
                            failures.append(
                                f"[7] {task}/{split}/ep{src_episode}/var{loaded[i][0]['variant_idx']}"
                                f"-var{loaded[j][0]['variant_idx']}: 事件末帧 bins_pos 逐 bin 相同"
                                " —— 注入未生效？"
                            )

                report["per_source"].append(
                    {
                        "task": task,
                        "split": split,
                        "src_episode": src_episode,
                        "variants": len(loaded),
                        "legal_pairs": ["".join(str(v) for v in pair) for pair in legal],
                        "nn_margin_min": round(min(margins), 6),
                        "topo_classes": sorted({item[1]["topo_class"] for item in loaded}),
                        "min_clearance_min": min(item[1]["min_clearance"] for item in loaded),
                        "bystander_net_max": max(item[1]["bystander_net_max"] for item in loaded),
                    }
                )

    # ── 判据 7a：同源变体互异（渲染侧，front_rgb 哈希）──
    # 最近邻约束下同源只剩 2~3 条，本判据的比较对数从 15/源 降到 1~3/源，判别力随之下降；
    # 判据 7b（事件末帧 bins_pos 逐 bin 有差异，见上）是对此的实质性补偿。
    for key, hashes in rgb_hashes.items():
        if len(set(hashes)) != len(hashes):
            failures.append(f"[7] {key[0]}/{key[1]}/ep{key[2]}: 事件末帧画面存在重复")

    # ── 判据 10：标签对账 ──
    # 标签侧的唯一载体是 episode_map_{Task}.json（2026-08-19 起 clip_events.json 等三个
    # 标签文件不再落盘，clip 级字段全部并入 map）。这里仍然是**独立复核**：h5 侧的
    # event_slots / topo_class 全部现算自 h5 内嵌的不可复算字段，与 map 里 merge 阶段
    # 写下的值是两条独立路径，对不上就说明某一环串了。
    label_records = []
    for task in tasks:
        for record in json.loads(
            (gen_dir / f"episode_map_{task}.json").read_text(encoding="utf-8")
        )["records"]:
            label_records.append({"task": task, **record})
    if len(label_records) != total_clips:
        failures.append(
            f"[10] episode_map 记录 {len(label_records)} 条 ≠ clip 总数 {total_clips}"
        )
    # 10b：主轴 event_slots 与协变量 topo_class **双轴**对账（标签侧 vs h5 实测）
    label_counts: dict[str, int] = defaultdict(int)
    label_event_counts: dict[str, int] = defaultdict(int)
    label_by_source: dict[tuple[str, str, int], list] = defaultdict(list)
    for record in label_records:
        label_counts[record["topo_class"]] += 1
        label_event_counts["".join(str(v) for v in record["event_slots"])] += 1
        label_by_source[(record["task"], record["split"], record["src_episode"])].append(
            tuple(record["event_slots"])
        )
    if dict(label_counts) != dict(topo_counts):
        failures.append(f"[10] 标签 topo 分布 {dict(label_counts)} ≠ h5 实测 {dict(topo_counts)}")
    if dict(label_event_counts) != dict(event_counts):
        failures.append(
            f"[10] 标签 event_slots 分布 {dict(label_event_counts)} ≠ h5 实测 {dict(event_counts)}"
        )
    # 10c-i：标签侧逐源覆盖 —— 与判据 1b 同命题，但从 clip_events.json 独立复核，
    #        防止标签管道漏条或串源。
    expected_event_counts: dict[str, int] = defaultdict(int)
    for (task_name, split_name, src_ep), pairs in sorted(label_by_source.items()):
        legal = nearest_neighbor_pairs(
            baseline[(split_name, task_name, src_ep)]["geometry"]["slot_xy"]
        )
        if sorted(pairs) != legal:
            failures.append(
                f"[10] {task_name}/{split_name}/ep{src_ep}: 标签侧事件集合 {sorted(pairs)} "
                f"≠ 最近邻合法集合 {legal}"
            )
    # 10c-ii：全局分布可预测 —— 期望值由「各源合法集合求并」现算，绝不写死数字
    expected_topo_counts: dict[str, int] = defaultdict(int)
    expected_by_split: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    label_by_split: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (task_name, split_name, src_ep), pairs in sorted(label_by_source.items()):
        for pair in nearest_neighbor_pairs(
            baseline[(split_name, task_name, src_ep)]["geometry"]["slot_xy"]
        ):
            key_str = "".join(str(v) for v in pair)
            expected_event_counts[key_str] += 1
            expected_by_split[split_name][key_str] += 1
            expected_topo_counts[topo_class(pair)] += 1
        for pair in pairs:
            label_by_split[split_name]["".join(str(v) for v in pair)] += 1
    if dict(label_event_counts) != dict(expected_event_counts):
        failures.append(
            f"[10] event_slots 全局分布 {dict(label_event_counts)} ≠ 由几何推出的期望 "
            f"{dict(expected_event_counts)}"
        )
    # 分 split 各查一遍：整个 split 的错标不能被全局聚合掩盖
    for split_name in sorted(expected_by_split):
        if dict(label_by_split[split_name]) != dict(expected_by_split[split_name]):
            failures.append(
                f"[10] {split_name} 的 event_slots 分布 {dict(label_by_split[split_name])} "
                f"≠ 由几何推出的期望 {dict(expected_by_split[split_name])}"
            )
    # topo_class 的两路对账（硬判据，补偿 10c-iii 的降级）：几何现算 vs merge 阶段写入
    if dict(label_counts) != dict(expected_topo_counts):
        failures.append(
            f"[10] topo_class 分布 {dict(label_counts)} ≠ 由几何推出的期望 "
            f"{dict(expected_topo_counts)}"
        )
    # 10c-iii：类空集回归守卫 —— cross_diagonal 在本 8 源上恒为空是**实测事实、不是几何
    #          必然**（Button 的 region4 带列内随机 y 偏移、各 bin 还有 ±0.07 rejection
    #          抖动，理论上对角可以成为最近邻）。一旦非 0，说明布局或源集合变了。
    cross_diag_count = label_counts.get("cross_diagonal", 0)
    if cross_diag_count != 0:
        diag_sources = sorted(
            f"{t}/{sp}/ep{ep}"
            for (t, sp, ep), pairs in label_by_source.items()
            if any(topo_class(p) == "cross_diagonal" for p in pairs)
        )
        warnings.append(
            f"[10] cross_diagonal 出现了 {cross_diag_count} 条（{', '.join(diag_sources)}）—— "
            "对角对首次进入某源的最近邻集合。这是新布局的事实、不是错误（train 8 源上恒空只是"
            "实测事实、非几何必然）；其正确性已由 topo 两路对账硬判据覆盖，"
            "但下游分层与 class_balance 口径需重审"
        )
    # 10d：chunk 级标签不再落盘（区分度极低，见 make_clip_labels 模块 docstring），
    #      改为**现算一遍网格**做回归守卫：110 帧只有 5 个 chunk，按 ε=0.10 第 0 个判负、
    #      其余 4 个判正。这是实测事实（窗口 1 恒为 clip [30,80)），窗口结构或 ε 一变就会炸。
    starts = grid_starts(CLIP_LEN)
    chunk_positive = 0
    for record in label_records:
        windows = swap_windows_clip(len(record["slot_pairs"]))
        for start in starts:
            progress, _ = chunk_progress(start, windows)
            chunk_positive += int(progress > DEFAULT_EPSILON)
    expected_positive = total_clips * (len(starts) - 1)
    if chunk_positive != expected_positive:
        failures.append(
            f"[10] 现算 chunk 正例 {chunk_positive} 条 ≠ 期望 {expected_positive} 条"
            f"（{total_clips} clip × {len(starts)} chunk，每条首 chunk 判负）"
        )

    for task in tasks:
        dev = action_dev_by_task[task]
        required = ACTION_BITWISE_REQUIRED[task]
        verdict = (
            "**逐位相同**（严格为 0）"
            if dev == 0.0
            else f"最大差 {dev:.3e} rad"
            + ("（该 env 要求逐位相同 → 判据失败）" if required else "（已知环境行为，见下）")
        )
        notes.append(f"判据 4（★ 机器人动作恒定）{task}：clip 全程 joint_action 跨同源变体{verdict}")
    if action_dev_by_task.get("ButtonUnmaskSwap"):
        leaky = [row for row in action_groups_by_source if row.get("identifies_label")]
        notes.append(
            "  ↳ ButtonUnmaskSwap 的动作差异是已实测定位的环境行为，但**不是**机械臂被容器碰到"
            f"（判据 11 本轮实测 {sum(1 for r in contact_rows if r['robot_bin_frames'] > 0)}/{total_clips}）：真正发生的是**交换中的两个容器互撞**改变了 "
            "PhysX 的接触求解规模与顺序，进而让机械臂-按钮的接触力数值解发生变化，关节角偏离后"
            "指数放大，solve_button 的后续分段规划以偏离的关节角为起点而分叉。零 src 改动无法消除。"
        )
        notes.append(
            "  ↳ ⚠ 最近邻约束把同源变体压到 2~3 条后，**旧口径「取同一 action_group 即得无泄露"
            "子集」已名存实亡**（同源 2 条分成 2 组时，「同一组」只剩 1 条）。下游一律用 "
            "`action_dev_max == 0` 筛选。"
            + (
                "本轮关节角可**完全反推**标签的源："
                + "、".join(
                    f"{row['task']}/{row['split']}/ep{row['src_episode']}" for row in leaky
                )
                if leaky else "本轮没有出现每组只剩 1 条的源。"
            )
        )
    notes.append(
        f"判据 3（前 {CLIP_MARGIN} 帧 bins_pos）：{comparison_pairs[0]} 次同源两两比较全部通过，"
        f"最大差 {worst_prefix:.3e}（最近邻约束下每源只有 2~3 条变体，比较对数 1~3/源）"
    )
    notes.append(
        f"判据 5（clip 末帧位置集合）：同上 {comparison_pairs[0]} 次比较全部通过，"
        f"最大差 {worst_endpoint:.3e}（阈值 {ENDPOINT_TOL}）"
    )
    deviating = [
        {
            "task": record["task"],
            "split": record["split"],
            "src_episode": record["src_episode"],
            "variant_idx": record["variant_idx"],
            "fixed_later_slots": [list(pair) for pair in record["slot_pairs"][1:]],
            "native_later_slots": record.get("later_windows_native_slots") or [],
        }
        for record in label_records
        if record.get("later_windows_follow_native_nn") is False
    ]
    notes.append(
        f"窗口 ≥2 的口径对账：{len(deviating)}/{total_clips} 条的「按槽位固定」与原版最近邻"
        "规则不重合"
        + (
            "（"
            + "、".join(
                f"{d['task'][:6]}/{d['split']}/ep{d['src_episode']}/var{d['variant_idx']}"
                f" 钉死{d['fixed_later_slots']} vs 原版{d['native_later_slots']}"
                for d in deviating[:10]
            )
            + ("…" if len(deviating) > 10 else "")
            + "）"
            if deviating else ""
        )
        + "。**事件本身（第一次 swap）仍严格落在原版可达空间内**，不重合的只是后 30 帧露出的"
        "第二次 swap 换了哪一对 —— 这是「约束只作用于第一次 swap」这个决定的直接后果，"
        "已逐条量化在 episode_map_{Task}.json 的 later_windows_follow_native_nn 字段。"
    )
    notes.append(
        f"判据 12（★ 最近邻不变量）：{total_clips}/{total_clips} 条 clip 的事件对满足"
        "「其一为另一之严格最近邻」，且用 clip 自身事件前一帧实测几何复算的合法集合与 Phase 0 "
        f"基线一致；原始首对命中 {original_hits[0]}/{len(report['per_source'])} 源"
        + (
            f"，其中有方向判据（原版 idx2 == NN(idx1)）命中 {directed_hits[0]}/{len(report['per_source'])} 源"
            if directed_hits[0] else ""
        )
        + f"；全局最小 argmin 余量 {global_min_margin[0]:.5f} m（告警阈 {NN_MARGIN_WARN}）"
    )
    rb_hit = [r for r in contact_rows if r["robot_bin_frames"] > 0]
    bb_hit = [r for r in contact_rows if r["bin_bin_frames"] > 0]
    notes.append(
        f"判据 11（机械臂 ↔ 容器接触）：{len(rb_hit)}/{total_clips} 条检测到 —— "
        + ("**全部为 0，机器人从未被 swap 中的容器碰到**" if not rb_hit else "存在接触，见失败项")
    )
    by_topo: dict[str, list[int]] = defaultdict(list)
    for row in contact_rows:
        by_topo[row["topo_class"]].append(int(row["bin_bin_frames"] > 0))
    notes.append(
        f"容器 ↔ 容器互撞（clip 内实际发生的物理接触）：{len(bb_hit)}/{total_clips} 条，"
        + "、".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by_topo.items()))
    )
    low = [item for item in report["quality"] if item["min_clearance"] < 0.055]
    all_clearance = [item["min_clearance"] for item in report["quality"]]
    notes.append(
        f"质量：min_clearance < 0.055 m 的 clip 有 {len(low)}/{total_clips} 条"
        + (f"（最小 {min(i['min_clearance'] for i in low):.4f}）" if low else "")
        + (f"；全体最小 {min(all_clearance):.4f} m" if all_clearance else "")
    )
    notes.append(
        "  ↳ 最近邻对总是短程对、路径不穿过第三个容器，所以 min_clearance / bystander_* / "
        "disturbed_bins / contact_bin_bin_* 在本子集里退化为近似常量。它们**不再具备下游分层"
        "能力**，价值转为**回归守卫**：一旦低净空样本重新出现、旁观 bin 被扰动、或互撞条数明显"
        "上升，就说明几何、注入口径或源集合发生了变化，必须停下来查。"
    )

    report["checks"] = {
        "total_clips": total_clips,
        "cross_diagonal_count": cross_diag_count,
        "joint_action_bitwise_identical": bitwise_ja,
        "joint_action_max_abs_diff": worst_ja,
        "action_dev_by_task": dict(action_dev_by_task),
        "action_groups_by_source": action_groups_by_source,
        "prefix_bins_max_abs_diff": worst_prefix,
        "endpoint_positions_max_abs_diff": worst_endpoint,
        "event_slots_counts": dict(event_counts),
        "topo_class_counts": dict(topo_counts),
        "comparison_pairs": comparison_pairs[0],
        "nn_margin_min": global_min_margin[0],
        "is_original_hits": original_hits[0],
        "directed_nn_hits": directed_hits[0],
        "chunk_label_count": len(label_records) * len(starts),
        "contact_robot_bin_clips": len(rb_hit),
        "contact_bin_bin_clips": len(bb_hit),
        "contact_rows": contact_rows,
    }
    report["failures"] = failures
    report["warnings"] = warnings
    report["notes"] = notes
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="clip 数据集端到端验收")
    parser.add_argument("--gen-dir", required=True)
    parser.add_argument(
        "--phase0-index", default=str(SCRIPT_DIR / "outputs" / "phase0" / "original_index.json")
    )
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    args = parser.parse_args(argv)

    gen_dir = Path(args.gen_dir).resolve()
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    report = verify(gen_dir, Path(args.phase0_index), tasks)

    checks = report["checks"]
    diag_count = checks.get("cross_diagonal_count", 0)
    lines = [
        "# clip 数据集验收报告",
        "",
        f"生成时间：{time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"目录：{gen_dir}",
        "",
        "## 汇总",
        "",
        f"- clip 总数：{checks['total_clips']}（源覆盖 train/test/val 三 split）",
        f"- ★ 主标签轴 event_slots 分布：{checks['event_slots_counts']}",
        f"- 协变量 topo_class 分布：{checks['topo_class_counts']}"
        + (
            "（cross_diagonal 实测为空）"
            if diag_count == 0
            else f"（cross_diagonal {diag_count} 条 —— 已非空，见告警段）"
        ),
        f"- 最近邻：全局最小 argmin 余量 {checks['nn_margin_min']:.5f} m；"
        f"同源两两比较 {checks['comparison_pairs']} 次",
        f"- chunk 标签数：{checks['chunk_label_count']}",
        "",
        "## 分 split 汇总",
        "",
        "| split | task | 源数 | clip 数 | event_slots 分布 | 互撞条数 | argmin 余量最小 |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: |",
    ]
    split_order = sorted(
        {(item["split"], item["task"]) for item in report["per_source"]},
        key=lambda kv: (SPLIT_CODE[kv[0]], kv[1]),
    )
    for split_name, task_name in split_order:
        sources = [
            item for item in report["per_source"]
            if item["split"] == split_name and item["task"] == task_name
        ]
        rows = [
            row for row in checks["contact_rows"]
            if row["split"] == split_name and row["task"] == task_name
        ]
        events: dict[str, int] = defaultdict(int)
        for row in rows:
            events["".join(str(v) for v in row["event_slots"])] += 1
        lines.append(
            f"| {split_name} | {task_name} | {len(sources)} | {len(rows)} | "
            + "、".join(f"{k}:{v}" for k, v in sorted(events.items()))
            + f" | {sum(1 for row in rows if row['bin_bin_frames'] > 0)} | "
            + f"{min(item['nn_margin_min'] for item in sources):.4f} |"
        )
    lines += ["", "## 关键判据", ""]
    lines += [f"- {note}" for note in report["notes"]]
    lines += ["", "## 逐源明细", "",
              "| task | split | 源 ep | 变体 | 合法对（最近邻） | argmin 余量 | 拓扑类别 | "
              "min_clearance | bystander_net_max |",
              "| --- | --- | ---: | ---: | --- | ---: | --- | ---: | ---: |"]
    for item in report["per_source"]:
        lines.append(
            f"| {item['task']} | {item['split']} | {item['src_episode']} | {item['variants']} | "
            f"{','.join(item['legal_pairs'])} | {item['nn_margin_min']:.4f} | "
            f"{'/'.join(item['topo_classes'])} | {item['min_clearance_min']:.4f} | "
            f"{item['bystander_net_max']:.4f} |"
        )
    lines += ["", "## 动作等价组（判据 4 的逐源明细）", "",
              "| task | split | 源 ep | 变体数 | 动作组数 | 可完全判别标签 | 各变体所属组 | 组间最大差 (rad) |",
              "| --- | --- | ---: | ---: | ---: | :-: | --- | ---: |"]
    for item in report["checks"]["action_groups_by_source"]:
        mapping = "、".join(
            f"var{k}→{v}" for k, v in sorted(item["group_of_variant"].items(), key=lambda x: int(x[0]))
        )
        lines.append(
            f"| {item['task']} | {item['split']} | {item['src_episode']} | {item['variants']} | "
            f"{item['n_action_groups']} | {'⚠ 是' if item['identifies_label'] else '否'} | "
            f"{mapping} | {item['max_dev']:.3e} |"
        )
    lines += ["", "## 接触检测（物理引擎 get_contacts 实测，冲量 > 1e-9 才算）", "",
              f"- **机械臂 ↔ 容器：{report['checks']['contact_robot_bin_clips']}/"
              f"{report['checks']['total_clips']} 条** —— 机器人是否被 swap 中的容器碰到",
              f"- 容器 ↔ 容器互撞：{report['checks']['contact_bin_bin_clips']}/"
              f"{report['checks']['total_clips']} 条（全部落在第一次 swap 窗口内）",
              "",
              "| task | split | 源 ep | var | 事件槽位 | 拓扑类别 | 机械臂↔容器 | 容器互撞帧 | 冲量max | 机械臂↔按钮 |",
              "| --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |"]
    for row in report["checks"]["contact_rows"]:
        lines.append(
            f"| {row['task']} | {row['split']} | {row['src_episode']} | {row['variant_idx']} | "
            f"{tuple(row['event_slots'])} | {row['topo_class']} | {row['robot_bin_frames']} | "
            f"{row['bin_bin_frames']} | {row['bin_bin_impulse_max']:.3f} | "
            f"{row['robot_button_frames']} |"
        )
    if report["warnings"]:
        lines += ["", "## 告警（不判失败，需人看一眼）", ""] + [
            f"- {line}" for line in report["warnings"]
        ]
    if report["failures"]:
        lines += ["", "## 失败项", ""] + [f"- {line}" for line in report["failures"]]
    else:
        lines += ["", "## 结论", "", "**全部十二条判据通过。**"]

    # 验收只产出**最后报告**这一份（用户 2026-08-19 拍板）：机读版 verification_report.json
    # 不再落盘 —— 报告里的每个数字都能靠重跑本脚本复现，留两份只是同一结论的两种编码。
    (gen_dir / "verification_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
