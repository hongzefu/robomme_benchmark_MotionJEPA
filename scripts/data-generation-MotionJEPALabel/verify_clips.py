#!/usr/bin/env python3
"""端到端验收：把「除了 bin 初始位置和第一次 swap 的排列组合，其他全部一致」逐条变成断言。

十一条判据（全过才算数）。核心是判据 4 —— clip 全程 110 帧的 joint_action 跨同源变体
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
    REQUIRED_BINS,
    bin_pairs,
    swap_windows_clip,
    topo_table,
)
from clip_worker import CLIP_IS_DEMO, segment_lengths, sorted_timesteps  # noqa: E402
from swap_inject import MOVED_NET_EPS  # noqa: E402

# 判据 3/4 期望逐位相同；实测若出现 ulp 级残差，降到这个阈值并在报告里单列实测值
BITWISE_FALLBACK_TOL = 1e-9
# 判据 4 只对「clip 内机器人不做运动规划」的 env 做硬断言。
# ButtonUnmaskSwap 例外并非放水，而是已实测定位的环境行为 —— 注意机械臂**从未**被容器
# 碰到（判据 11 实测 0/48）。真正的链条是：交换中的两个容器互撞（判据 11 的 bin_bin，
# 20/48 条）→ 改变 PhysX 的接触求解规模与顺序 → 机械臂-按钮的接触力数值解发生变化
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


def load_episode(group: h5py.Group) -> dict:
    names = sorted_timesteps(group)
    gt = group["setup"]["swap_gt"]
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
        "event_slots": tuple(np.asarray(gt["event_slots"]).tolist()),
        "topo_class": gt["topo_class"][()].decode("utf-8"),
        "bin_pairs": np.asarray(gt["bin_pairs"]).tolist(),
        "slot_pairs": np.asarray(gt["slot_pairs"]).tolist(),
        "is_original": int(np.asarray(gt["is_original"])),
        "min_clearance": float(np.asarray(gt["min_clearance"])),
        "bystander_net_max": float(np.asarray(gt["bystander_net_max"])),
        "n_bins": int(np.asarray(gt["slot_xy"]).shape[0]),
        "contact_robot_bin": int(np.asarray(gt["contact_robot_bin_forceful_frames"])),
        "contact_bin_bin": int(np.asarray(gt["contact_bin_bin_forceful_frames"])),
        "contact_bin_bin_event": int(np.asarray(gt["contact_bin_bin_event_forceful_frames"])),
        "contact_bin_bin_impulse": float(np.asarray(gt["contact_bin_bin_impulse_max"])),
        "contact_robot_button": int(np.asarray(gt["contact_robot_button_forceful_frames"])),
    }


def verify(gen_dir: Path, phase0_index: Path, tasks: Sequence[str]) -> dict:
    failures: list[str] = []
    notes: list[str] = []
    report: dict = {"checks": {}, "per_source": [], "quality": []}

    manifest_path = gen_dir / "clips_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["records"]
    baseline = {
        (record["task"], int(record["episode"])): record
        for record in json.loads(phase0_index.read_text(encoding="utf-8"))["records"]
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

    for task in tasks:
        map_path = gen_dir / f"episode_map_{task}.json"
        episode_map = json.loads(map_path.read_text(encoding="utf-8"))["records"]
        by_source: dict[int, list[dict]] = defaultdict(list)
        for entry in episode_map:
            by_source[entry["src_episode"]].append(entry)

        with h5py.File(gen_dir / f"record_dataset_{task}.h5", "r") as handle:
            # ── 判据 9：merged h5 结构 ──
            names = [n for n in handle if n.startswith("episode_")]
            indices = sorted(int(n.rsplit("_", 1)[1]) for n in names)
            if indices != list(range(len(indices))):
                failures.append(f"[9] {task}: episode 编号不密集连续")

            for src_episode, entries in sorted(by_source.items()):
                entries.sort(key=lambda item: item["variant_idx"])
                loaded = []
                for entry in entries:
                    group = handle[f"episode_{entry['dense_episode']}"]
                    data = load_episode(group)
                    loaded.append((entry, data))
                    total_clips += 1
                    topo_counts[data["topo_class"]] += 1

                    # 判据 1：bin 数
                    if data["n_bins"] != REQUIRED_BINS:
                        failures.append(
                            f"[1] {task}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"bin 数 {data['n_bins']} ≠ {REQUIRED_BINS}"
                        )
                    # 判据 9：帧数与 scope 段
                    if data["n"] != CLIP_LEN:
                        failures.append(
                            f"[9] {task}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"{data['n']} 帧 ≠ {CLIP_LEN}"
                        )
                    total, demo_prefix, exec_len = segment_lengths(group)
                    scope = demo_prefix if CLIP_IS_DEMO[task] else exec_len
                    if scope != CLIP_LEN:
                        failures.append(
                            f"[9] {task}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"scope 段 {scope} ≠ {CLIP_LEN}"
                        )
                    # 判据 2：布局指纹（槽位 xy 与 Phase 0 基线）
                    base_bins = np.asarray(
                        [b["p"][:2] for b in baseline[(task, src_episode)]["fingerprint"]["bins"]]
                    )
                    if not np.array_equal(np.asarray(entry["slot_xy"]), base_bins):
                        failures.append(
                            f"[2] {task}/ep{src_episode}/var{entry['variant_idx']}: "
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
                            f"[6] {task}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"计划交换 bin {sorted(planned)}，实测移动 {sorted(moved)}"
                            f"（net={np.round(net, 4).tolist()}）"
                        )
                    # 判据 8：cube 可见性分段
                    cubes = data["cubes"]
                    if not (cubes[:CLIP_MARGIN, :, 2] < CUBE_ON_TABLE_Z).all():
                        failures.append(
                            f"[8] {task}/ep{src_episode}/var{entry['variant_idx']}: "
                            "事件前 30 帧有 cube 不在桌面高度"
                        )
                    if not (cubes[CLIP_MARGIN:, :, 2] > CUBE_AWAY_Z).all():
                        failures.append(
                            f"[8] {task}/ep{src_episode}/var{entry['variant_idx']}: "
                            "事件开始后有 cube 未被藏走"
                        )
                    # ── 判据 11：机械臂 ↔ 容器接触（物理引擎实测，必须为 0）──
                    # 本链路的前提是「机器人动作只由任务本身决定」。若机械臂真被 swap 中的
                    # 容器碰到，那 clip 里就多了一条 swap→机器人的直接因果通路。
                    # 2026-08-18 全量实测：0/48 条，从未发生。
                    if data["contact_robot_bin"] > 0:
                        failures.append(
                            f"[11] {task}/ep{src_episode}/var{entry['variant_idx']}: "
                            f"检测到机械臂 ↔ 容器接触 {data['contact_robot_bin']} 帧"
                        )
                    contact_rows.append(
                        {
                            "task": task,
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
                    rgb_hashes[(task, src_episode)].append(data["rgb_event_end"])
                    report["quality"].append(
                        {
                            "task": task,
                            "src_episode": src_episode,
                            "variant_idx": entry["variant_idx"],
                            "event_slots": list(data["event_slots"]),
                            "topo_class": data["topo_class"],
                            "min_clearance": data["min_clearance"],
                            "bystander_net_max": data["bystander_net_max"],
                        }
                    )

                # ── 判据 1：枚举完整度与 is_original ──
                slots = sorted(item[1]["event_slots"] for item in loaded)
                if slots != bin_pairs(REQUIRED_BINS):
                    failures.append(
                        f"[1] {task}/ep{src_episode}: 事件槽位对集合 {slots} ≠ 全部 6 种"
                    )
                originals = sum(item[1]["is_original"] for item in loaded)
                if originals != 1:
                    failures.append(f"[1] {task}/ep{src_episode}: is_original 有 {originals} 条，应为 1")

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
                        "src_episode": src_episode,
                        "n_action_groups": len(reps),
                        "group_of_variant": {
                            str(entry["variant_idx"]): gid
                            for (entry, _), gid in zip(loaded, assigned)
                        },
                        "max_dev": source_dev,
                    }
                )
                if source_dev != 0.0:
                    bitwise_ja = False
                    if ACTION_BITWISE_REQUIRED[task]:
                        failures.append(
                            f"[4] {task}/ep{src_episode}: clip 全程 joint_action 跨同源变体"
                            f"最大差 {source_dev:.3e}，该 env 要求逐位相同"
                        )

                for entry, data in loaded[1:]:
                    tag = f"{task}/ep{src_episode}/var{entry['variant_idx']}"
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
                        failures.append(
                            f"[5] {tag}: clip 末帧位置集合与同源基准差 {diff_end:.3e} > {ENDPOINT_TOL}"
                        )

                report["per_source"].append(
                    {
                        "task": task,
                        "src_episode": src_episode,
                        "variants": len(loaded),
                        "topo_classes": sorted({item[1]["topo_class"] for item in loaded}),
                        "min_clearance_min": min(item[1]["min_clearance"] for item in loaded),
                        "bystander_net_max": max(item[1]["bystander_net_max"] for item in loaded),
                    }
                )

    # ── 判据 7：同源变体互异 ──
    for key, hashes in rgb_hashes.items():
        if len(set(hashes)) != len(hashes):
            failures.append(f"[7] {key[0]}/ep{key[1]}: 事件末帧画面存在重复")

    # ── 判据 10：标签对账 ──
    clip_labels = json.loads((gen_dir / "clip_events.json").read_text(encoding="utf-8"))
    chunk_labels = json.loads((gen_dir / "swap_labels_clip.json").read_text(encoding="utf-8"))
    if len(clip_labels["records"]) != total_clips:
        failures.append(
            f"[10] clip 级标签 {len(clip_labels['records'])} 条 ≠ clip 总数 {total_clips}"
        )
    label_counts: dict[str, int] = defaultdict(int)
    for record in clip_labels["records"]:
        label_counts[record["topo_class"]] += 1
    if dict(label_counts) != dict(topo_counts):
        failures.append(f"[10] 标签类别分布 {dict(label_counts)} ≠ h5 实测 {dict(topo_counts)}")
    expected_classes = {name for name in topo_table().values()}
    per_class = total_clips // len(expected_classes)
    if set(label_counts) != expected_classes or any(v != per_class for v in label_counts.values()):
        failures.append(
            f"[10] 拓扑类别不均衡：{dict(label_counts)}，期望每类 {per_class} 条"
        )
    expected_chunks = total_clips * len(range(0, max(0, CLIP_LEN - 32), 16))
    if len(chunk_labels["records"]) != expected_chunks:
        failures.append(
            f"[10] chunk 标签 {len(chunk_labels['records'])} 条 ≠ 网格期望 {expected_chunks} 条"
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
        notes.append(
            "  ↳ ButtonUnmaskSwap 的动作差异是已实测定位的环境行为，但**不是**机械臂被容器碰到"
            "（判据 11 实测 0/48）：真正发生的是**交换中的两个容器互撞**（20/48 条），它改变 "
            "PhysX 的接触求解规模与顺序，进而让机械臂-按钮的接触力数值解发生变化 —— ep95/var2 "
            "实测 env 70 起 bin_0↔bin_3 持续接触、env 79 button_cap↔panda_finger 冲量出现差异、"
            "qpos 偏离 4.7e-5 后指数放大，env 88 时 solve_button 的后两段规划以偏离的关节角为"
            "起点而分叉。零 src 改动无法消除，标签里 action_group / action_dev_max 逐条量化，"
            "下游取同一 action_group 即得无泄露子集。"
        )
    notes.append(f"判据 3（前 {CLIP_MARGIN} 帧 bins_pos）最大差 {worst_prefix:.3e}")
    notes.append(f"判据 5（clip 末帧位置集合）最大差 {worst_endpoint:.3e}（阈值 {ENDPOINT_TOL}）")
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
    notes.append(
        f"质量：min_clearance < 0.055 m 的 clip 有 {len(low)}/{total_clips} 条"
        + (f"（最小 {min(i['min_clearance'] for i in low):.4f}）" if low else "")
    )

    report["checks"] = {
        "total_clips": total_clips,
        "joint_action_bitwise_identical": bitwise_ja,
        "joint_action_max_abs_diff": worst_ja,
        "action_dev_by_task": dict(action_dev_by_task),
        "action_groups_by_source": action_groups_by_source,
        "prefix_bins_max_abs_diff": worst_prefix,
        "endpoint_positions_max_abs_diff": worst_endpoint,
        "topo_class_counts": dict(topo_counts),
        "chunk_label_count": len(chunk_labels["records"]),
        "contact_robot_bin_clips": len(rb_hit),
        "contact_bin_bin_clips": len(bb_hit),
        "contact_rows": contact_rows,
    }
    report["failures"] = failures
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

    lines = [
        "# clip 数据集验收报告",
        "",
        f"生成时间：{time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"目录：{gen_dir}",
        "",
        "## 汇总",
        "",
        f"- clip 总数：{report['checks']['total_clips']}",
        f"- 拓扑类别分布：{report['checks']['topo_class_counts']}",
        f"- chunk 标签数：{report['checks']['chunk_label_count']}",
        "",
        "## 关键判据",
        "",
    ]
    lines += [f"- {note}" for note in report["notes"]]
    lines += ["", "## 逐源明细", "", "| task | 源 ep | 变体 | 拓扑类别 | min_clearance | bystander_net_max |", "| --- | ---: | ---: | --- | ---: | ---: |"]
    for item in report["per_source"]:
        lines.append(
            f"| {item['task']} | {item['src_episode']} | {item['variants']} | "
            f"{'/'.join(item['topo_classes'])} | {item['min_clearance_min']:.4f} | "
            f"{item['bystander_net_max']:.4f} |"
        )
    lines += ["", "## 动作等价组（判据 4 的逐源明细）", "",
              "| task | 源 ep | 动作组数 | 各变体所属组 | 组间最大差 (rad) |",
              "| --- | ---: | ---: | --- | ---: |"]
    for item in report["checks"]["action_groups_by_source"]:
        mapping = "、".join(
            f"var{k}→{v}" for k, v in sorted(item["group_of_variant"].items(), key=lambda x: int(x[0]))
        )
        lines.append(
            f"| {item['task']} | {item['src_episode']} | {item['n_action_groups']} | "
            f"{mapping} | {item['max_dev']:.3e} |"
        )
    lines += ["", "## 接触检测（物理引擎 get_contacts 实测，冲量 > 1e-9 才算）", "",
              f"- **机械臂 ↔ 容器：{report['checks']['contact_robot_bin_clips']}/"
              f"{report['checks']['total_clips']} 条** —— 机器人是否被 swap 中的容器碰到",
              f"- 容器 ↔ 容器互撞：{report['checks']['contact_bin_bin_clips']}/"
              f"{report['checks']['total_clips']} 条（全部落在第一次 swap 窗口内）",
              "",
              "| task | 源 ep | var | 事件槽位 | 拓扑类别 | 机械臂↔容器 | 容器互撞帧 | 冲量max | 机械臂↔按钮 |",
              "| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |"]
    for row in report["checks"]["contact_rows"]:
        lines.append(
            f"| {row['task']} | {row['src_episode']} | {row['variant_idx']} | "
            f"{tuple(row['event_slots'])} | {row['topo_class']} | {row['robot_bin_frames']} | "
            f"{row['bin_bin_frames']} | {row['bin_bin_impulse_max']:.3f} | "
            f"{row['robot_button_frames']} |"
        )
    if report["failures"]:
        lines += ["", "## 失败项", ""] + [f"- {line}" for line in report["failures"]]
    else:
        lines += ["", "## 结论", "", "**全部十一条判据通过。**"]

    (gen_dir / "verification_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (gen_dir / "verification_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
