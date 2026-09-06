"""把离线复算参数与 h5 时长合成 Markdown 报告（总览 + 四个分源明细）。"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# 报告一律按「任务」组织，test 与 val 合并成一份（每任务 100 条）；
# 每条记录仍带 split，明细里逐条标出来源，所以合并不丢信息。
SOURCES = ["PatternLock", "RouteStick"]
COUNTING_SOURCES = ["BinFill", "PickXtimes"]
SPLITS = ["test", "val"]


def merge_by_task(payload: dict[str, Any], tasks: list[str]) -> dict[str, list[dict[str, Any]]]:
    """把 {"Task-split": ...} 归并成 {"Task": [row, ...]}，给每条补上 split 与 episode。

    输入既可能是 list（derived_params）也可能是 dict（durations / counting_params 以 episode 为键）。
    """
    out: dict[str, list[dict[str, Any]]] = {task: [] for task in tasks}
    for key, value in (payload or {}).items():
        task, _, split = key.partition("-")
        if task not in out:
            continue
        items = value if isinstance(value, list) else [
            {**row, "episode": int(episode)} for episode, row in value.items()
        ]
        for row in items:
            out[task].append({**row, "split": split})
    for task in out:
        out[task].sort(key=lambda r: (SPLITS.index(r["split"]), int(r["episode"])))
    return {task: rows for task, rows in out.items() if rows}


def tag(row: dict[str, Any]) -> str:
    """明细里给每条 episode 的来源标识，如 test-ep17。"""
    return f"{row['split']}-ep{row['episode']}"
DIFFICULTY_ORDER = ["easy", "medium", "hard"]
# BinFill / PickXtimes 各难度的 env 配置（BinFill.configs / PickXtimes.configs），决定动作次数区间
COUNTING_CONFIG_NOTE = {
    "easy": "BinFill：场上 1 种颜色、spawn 4~6 个 cube，要放进 bin 的 `put_in_numbers ∈ [1, 3]`。"
    "PickXtimes：场上 1 种颜色，重复次数 ∈ [1, 3]。",
    "medium": "BinFill：2 种颜色、spawn 8~10 个，目标涉及 1~2 种颜色、总数 ∈ [2, 4]。"
    "PickXtimes：**重复次数区间与 easy 相同（[1, 3]）**，难点在于场上有 3 种颜色的 cube 作干扰。",
    "hard": "BinFill：3 种颜色、spawn 10~12 个，目标涉及 2~3 种颜色、总数 ∈ [3, 5]。"
    "PickXtimes：3 种颜色，重复次数 ∈ [4, 5]。",
}
# 各难度下 env 的配置项（PatternLock.configs / RouteStick.configs），决定 move 次数的上下界
DIFFICULTY_CONFIG_NOTE = {
    "easy": "PatternLock：3×3 格点，路径长度约束 `[2, 4]` → move 1~3 次。"
    "RouteStick：`steps ∈ [2, 3]`，不允许原地折返。",
    "medium": "PatternLock：4×4 格点，路径长度约束 `[3, 5]` → move 2~4 次。"
    "RouteStick：`steps ∈ [4, 5]`，不允许原地折返。",
    "hard": "PatternLock：5×5 格点，路径长度约束 `[4, 8]` → move 3~7 次。"
    "RouteStick：`steps ∈ [4, 7]`，**允许原地折返**（`backtrack=True`）。",
}
COUNTING_ORIGIN = {
    task: (
        f"val 来自原版 h5 `/data/hongzefu/data-0306/record_dataset_{task}.h5`；"
        "test 本机无官方 h5，由本轮按 test metadata 死 seed 实跑生成"
    )
    for task in ("BinFill", "PickXtimes")
}
ORIGIN = {
    task: (
        f"val 来自原版 h5 `/data/hongzefu/data-0306/record_dataset_{task}.h5`；"
        "test 本机无官方 h5，由本轮按 test metadata 死 seed 实跑生成"
    )
    for task in ("PatternLock", "RouteStick")
}


def fmt_xyz(point: list[float]) -> str:
    return f"({point[0]:+.3f}, {point[1]:+.3f}, {point[2]:+.3f})"


def episode_section(row: dict[str, Any], dur: dict[str, Any] | None) -> list[str]:
    task = row["task"]
    lines = [
        f"#### {tag(row)} — seed `{row['seed']}`，难度 {row['difficulty']}，move {row['moves']} 次",
        "",
    ]
    if task == "RouteStick":
        lines.append(f"整排绕 z 轴旋转 `theta = {row['theta_deg']:.3f}°`；节点序列 `{row['path_nodes']}`（1×9 格点，只用偶数下标）。")
    else:
        lines.append(f"{row['grid']}×{row['grid']} 格点，节点序列 `{row['path_nodes']}`。")
    lines.append("")

    if dur is None:
        lines.append("> 时长：**未生成**（该 episode 无 h5）。")
        lines.append("")
        exec_dur: list[int] = []
        demo_dur: list[int] = []
    else:
        exec_dur = dur["exec_durations"]
        demo_dur = dur["demo_durations"]
        lines.append(
            f"整条 {dur['n_timesteps_total']} timestep（其中收尾段 {dur['completed_tail_timesteps']}）。"
        )
        lines.append("")

    header = "| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |"
    lines.append(header)
    lines.append("| --- | --- | --- | --- | --- | --- |")
    coords = row["coords_xyz"]
    for index, semantic in enumerate(row["move_directions"]):
        e = f"{exec_dur[index]} ts" if index < len(exec_dur) else "—"
        d = f"{demo_dur[index]} ts" if index < len(demo_dur) else "—"
        lines.append(
            f"| {index + 1} | {fmt_xyz(coords[index])} | {fmt_xyz(coords[index + 1])} | {semantic} | {e} | {d} |"
        )
    lines.append("")
    return lines


def build_source_report(task: str, rows: list[dict], durations: dict[str, list[dict]]) -> str:
    lines = [
        f"# {task} 逐 episode 动作参数",
        "",
        f"共 {len(rows)} 条（test 50 + val 50，每条标出来源）。数据来源：{ORIGIN[task]}。",
        "",
        "口径：坐标是 SAPIEN 世界坐标，单位米（机器人 base 在 `(-0.615, 0, 0)`），"
        "表中给的是按钮本身的位置；运动规划实际下发的终点高度统一抬到 `z=0.07`。"
        "时长单位是 timestep（1 timestep = 1 个 env step = 0.05 s）；"
        "每组 move 在数据里出现两遍，前一遍是给模型看的演示段，后一遍是真正执行段。",
        "",
    ]
    if task == "RouteStick":
        lines += [
            "RouteStick 的 move 不是直线：末端要绕开挡在中间的柱子，走二次贝塞尔弧线"
            "（横向偏移 0.2 m，顺/逆时针由 `swing_directions` 决定），因此单次 move 时长稳定在 50 timestep 上下。",
            "",
        ]
    index = {(d["split"], int(d["episode"])): d for d in durations or []}
    for row in rows:
        dur = index.get((row["split"], int(row["episode"])))
        lines += episode_section(row, dur)
    return "\n".join(lines)


# Counting 的段名只有三种句式，按前缀归类即可（实测 val+test 四源 1262 段全部命中）
VERB_LABELS = [("pick", "pick up"), ("place", "put / place"), ("press", "press")]


def verb_of(subgoal: str) -> str | None:
    """把子目标名归到 pick / place / press 三类；不属于任何一类返回 None（不应出现）。"""
    text = subgoal.lower()
    if text.startswith("pick up"):
        return "pick"
    if text.startswith(("put ", "place ")):
        return "place"
    if text.startswith("press"):
        return "press"
    return None


def durations_by_verb(rows: list[dict[str, Any]]) -> tuple[dict[str, list[int]], list[str]]:
    """按动词聚合时长；同时返回归类失败的段名，供调用方断言。"""
    buckets: dict[str, list[int]] = {verb: [] for verb, _ in VERB_LABELS}
    unknown: list[str] = []
    for row in rows:
        for subgoal, duration in zip(row["subgoals"], row["durations"]):
            verb = verb_of(subgoal)
            if verb is None:
                unknown.append(subgoal)
            else:
                buckets[verb].append(duration)
    return buckets, unknown


def counting_episode_section(row: dict[str, Any]) -> list[str]:
    lines = [
        f"#### {tag(row)} — seed `{row['seed']}`，难度 {row['difficulty']}，动作 {row['actions']} 次",
        "",
        f"目标：{row['task_goal']}",
        "",
        f"整条 {row['n_timesteps_total']} timestep（其中收尾段 {row['completed_tail_timesteps']}）。",
        "",
        "| # | 子目标 | 时长 | 关键点 (x,y,z) |",
        "| --- | --- | --- | --- |",
    ]
    index = 0
    for segment in row["segments"]:
        if segment["subgoal"] in ("All tasks completed", "NO RECORD"):
            continue
        index += 1
        point = segment.get("target_xyz")
        coord = (
            f"({point[0]:+.3f}, {point[1]:+.3f}, {point[2]:+.3f})" if point else "—"
        )
        lines.append(
            f"| {index} | {segment['subgoal']} | {segment['n_timesteps']} ts | {coord} |"
        )
    lines.append("")
    return lines


def build_counting_report(task: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# {task} 逐 episode 动作参数",
        "",
        f"共 {len(rows)} 条（test 50 + val 50，每条标出来源）。数据来源：{COUNTING_ORIGIN[task]}。",
        "",
        "口径：动作次数与颜色组成直接读 `setup/task_goal`（BinFill 是要放几个什么颜色的 cube，"
        "PickXtimes 是同一动作重复几次）；每次动作在数据里是 pick 与 place 两段，末尾再加一段 press button，"
        "所以核心段数 = 2 × 动作次数 + 1（本报告的每条都验过这条恒等式）。"
        "时长单位是 timestep（1 timestep = 1 个 env step = 0.05 s）。"
        "关键点坐标取该段内 z 最低的 `action/waypoint_action`（段首帧常残留上一段的值，不可用）——"
        "pick 段即 cube 位置、press 段即按钮位置、put 段即 bin 上方的松手点，"
        "SAPIEN 世界坐标、单位米（机器人 base 在 `(-0.615, 0, 0)`）；该帧没有关键点时记 —。",
        "",
        "与 PatternLock / RouteStick 不同，这两个任务**没有视频演示段**，所以不存在「演示段 / 执行段」之分，"
        "下表每一行就是真正执行的一段。每行的子目标必是三类之一："
        "`pick up …`（找到并抓起指定 cube）、`put / place …`（送到 bin 或 target）、`press …`（按按钮）；"
        "每次动作产生一对 pick + place，末尾另有一段 press。",
        "",
    ]
    for row in rows:
        lines += counting_episode_section(row)
    return "\n".join(lines)


# 采样口径与 policy 侧的 motion store / frame sampling 对齐（已用其 16 任务中位集逐条验证）：
#   motion 窗口：[f, f+32]（33 帧），stride=16，不跨段——demo / exec 两段各自从段起点铺网格
#   帧路：even_sampling_indices 在 t>=32 时做 linspace(0, t, N)，故 Δ = t/(N-1)，t = T-1
WINDOW_FRAMES = 33
WINDOW_STRIDE = 16
FRAME_BUDGETS = [32, 8]


def seg_windows(seg_len: int) -> int:
    """一段能铺出的窗口数：len(range(0, max(0, L-32), 16))，与 motion_store.seg_num_grid 同式。"""
    return len(range(0, max(0, seg_len - (WINDOW_FRAMES - 1)), WINDOW_STRIDE))


def frame_delta(total: int, budget: int) -> float:
    """帧路相邻采样帧的间隔 Δ = t/(N-1)，t = T-1。"""
    return (total - 1) / (budget - 1)


def collect_lengths(
    durations: dict[str, list[dict]], counting: dict[str, list[dict]] | None
) -> dict[str, list[dict[str, Any]]]:
    """把四个任务的每条 episode 收成统一形状，供采样窗口一节使用。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for task, rows in (durations or {}).items():
        out[task] = [
            {
                "split": r["split"],
                "episode": int(r["episode"]),
                "seed": r["seed"],
                "difficulty": r["difficulty"],
                "total": r["n_timesteps_total"],
                "demo": sum(r["demo_durations"]),
                "n_segments": r["n_move_segments"],
            }
            for r in rows
        ]
    for task, rows in (counting or {}).items():
        out[task] = [
            {
                "split": r["split"],
                "episode": int(r["episode"]),
                "seed": r["seed"],
                "difficulty": r["difficulty"],
                "total": r["n_timesteps_total"],
                "demo": 0,
                "n_segments": r["n_core_segments"],
            }
            for r in rows
        ]
    for rows in out.values():
        for item in rows:
            item["demo_windows"] = seg_windows(item["demo"])
            item["exec_windows"] = seg_windows(item["total"] - item["demo"])
            item["motion_tokens"] = item["demo_windows"] + item["exec_windows"]
    return out


def build_length_section(lengths: dict[str, list[dict[str, Any]]]) -> list[str]:
    keys = [k for k in SOURCES + COUNTING_SOURCES if k in lengths]
    lines = [
        "## 采样窗口与帧路",
        "",
        "口径与 policy 侧的 motion store / frame sampling 对齐：",
        "",
        f"- **motion 窗口**：窗口 `[f, f+{WINDOW_FRAMES - 1}]`（{WINDOW_FRAMES} 帧），"
        f"**stride = {WINDOW_STRIDE}**，且**不跨段** —— demo 与 exec 两段各自从自己的段起点铺网格。"
        f"每段窗口数 `len(range(0, max(0, L - {WINDOW_FRAMES - 1}), {WINDOW_STRIDE}))`；"
        "一条 episode 的 motion token 数 = demo 窗口数 + exec 窗口数。",
        f"- **帧路**：`linspace(0, t, N)`（`t = T - 1`），相邻采样帧间隔 **Δ = t / (N - 1)**。"
        f"帧预算 N 取 {FRAME_BUDGETS[0]}（`512 // (16 × 1)`）与 {FRAME_BUDGETS[1]}（`128 // (16 × 1)`）。"
        "注意 32 / 8 是**帧预算**，16 才是窗口 stride，三者不是同一个东西。",
        "",
        "> 这套公式已用 policy 侧 16 个任务的中位集逐条验证：窗口数（demo+exec）与 Δ 全部一致，16/16。",
        "",
        "### 四个任务总表",
        "",
        "每任务 100 条（test 50 + val 50）。",
        "",
        "| 任务 | 条数 | 整条长度 min~中位~max | demo 窗口 | exec 窗口 | motion token（min~max，中位） | Δ(N=32) | Δ(N=8) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for task in keys:
        rows = lengths[task]
        totals = [r["total"] for r in rows]
        dw = [r["demo_windows"] for r in rows]
        ew = [r["exec_windows"] for r in rows]
        mt = [r["motion_tokens"] for r in rows]
        d32 = [frame_delta(t, 32) for t in totals]
        d8 = [frame_delta(t, 8) for t in totals]
        lines.append(
            f"| {task} | {len(rows)} | {min(totals)}~{statistics.median(totals):.0f}~{max(totals)} | "
            f"{min(dw)}~{max(dw)} | {min(ew)}~{max(ew)} | "
            f"{min(mt)}~{max(mt)}，中位 {statistics.median(mt):.0f} | "
            f"{min(d32):.1f}~{max(d32):.1f} | {min(d8):.1f}~{max(d8):.1f} |"
        )

    zeros = [
        (task, r)
        for task in keys
        for r in lengths[task]
        if r["motion_tokens"] == 0
    ]
    lines += [
        "",
        "### 时序数轴：窗口、subgoal 与帧路叠在一根轴上",
        "",
        "每张图 9 行 = 3 难度 × {最短, 中位, 最长}（按整条长度 T 取），同一任务内共用横轴。"
        "一行从下到上四层：**subgoal 分段**（灰色交替块，块内是压缩后的中文标签，图上标不下时省略）、"
        "**帧路 N=8**（红点）、**motion 窗口**（demo 蓝 / exec 绿，**每格 = 1 个窗口**，"
        "格宽即 stride 16；窗口真实跨度 33 帧、相邻重叠一半，用首窗上方的细线示意）、"
        "**帧路 N=32**（紫色细竖线）。段短于 33 帧铺不出窗口，画成橙色虚线空框。"
        "右侧标 T、`demo窗+exec窗`、两个 Δ。",
        "",
        f"> 同一份内容的**交互版**（难度档切换、悬停看 subgoal 原文、横轴跨档固定）："
        f"[采样窗口数轴](https://claude.ai/code/artifact/093a467c-d567-466b-b57e-e4fdee2bcac0)",
        "",
    ]
    for task in keys:
        lines.append(f"![{task} 采样窗口时序数轴](figures/sampling_{task}.png)")
        lines.append("")

    lines += ["### 产不出 motion token 的 episode", ""]
    if zeros:
        lines += [
            "窗口长 33 帧，段短于 33 帧铺不出窗口，这些 episode 的 motion token 为 0：",
            "",
            "| 任务 | 来源 | seed | 难度 | T | demo 段长 | exec 段长 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for task, r in zeros:
            lines.append(
                f"| {task} | {r['split']}-ep{r['episode']} | {r['seed']} | {r['difficulty']} | "
                f"{r['total']} | {r['demo']} | {r['total'] - r['demo']} |"
            )
        lines.append("")
    else:
        lines += ["四个任务 400 条里没有窗口数为 0 的 episode。", ""]

    imitation = [k for k in SOURCES if k in lengths]
    if imitation:
        lines += [
            "### demo 段占了 Imitation 的一半",
            "",
            "PatternLock / RouteStick 的每条 episode 有 demo 与 exec 两段（`is_video_demo`），窗口不跨段：",
            "",
            "| 任务 | 演示段合计 | 执行段合计 | 演示占比 | demo 窗口合计 | exec 窗口合计 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for task in imitation:
            rows = lengths[task]
            demo = sum(r["demo"] for r in rows)
            total = sum(r["total"] for r in rows)
            lines.append(
                f"| {task} | {demo} | {total - demo} | {demo / total:.1%} | "
                f"{sum(r['demo_windows'] for r in rows)} | {sum(r['exec_windows'] for r in rows)} |"
            )
        lines += ["", "BinFill / PickXtimes 无 demo 段，整条都是 exec。", ""]
    return lines


def summary_stats(rows: list[dict], durations: list[dict] | None) -> dict[str, Any]:
    """按难度分桶统计：move 次数与单次 move 时长。难度是决定这两项的唯一配置，混在一起看没有意义。"""
    moves = [row["moves"] for row in rows]
    index = {(d["split"], int(d["episode"])): d for d in durations or []}
    all_dur = [
        d
        for row in rows
        for d in index.get((row["split"], int(row["episode"])), {}).get("exec_durations", [])
    ]
    return {
        "episodes": len(rows),
        "moves_range": (min(moves), max(moves)),
        "moves_mean": statistics.mean(moves),
        "dur_range": (min(all_dur), max(all_dur)) if all_dur else None,
        "dur_mean": statistics.mean(all_dur) if all_dur else None,
    }


def stats_by_difficulty(rows: list[dict], durations: list[dict] | None) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row["difficulty"], []).append(row)
    return {
        level: summary_stats(buckets[level], durations)
        for level in DIFFICULTY_ORDER
        if level in buckets
    }


def build_summary(
    payload: dict[str, list[dict]],
    durations: dict[str, dict],
    counting: dict[str, dict] | None = None,
) -> str:
    lines = [
        "# PatternLock / RouteStick 的 test+val 源逐 episode 动作参数",
        "",
        "四个任务各 100 条（test 50 + val 50 合并），共 400 个 episode。每个 episode 给出：做了几次动作、"
        "每次动作的起终点坐标、每次动作占多少 timestep。明细见同目录的四份任务报告。",
        "",
        "## 口径",
        "",
        "- **seed / 难度**：一律读 `src/robomme/env_metadata/{test,val}/record_dataset_{Task}_metadata.json`，"
        "不用公式反推（存在 attempt 尾号例外，如 PatternLock-val ep37 = 1153701）。",
        "- **move 次数与坐标**：不需要跑仿真。两个 env 的场景随机段只用一个 `torch.Generator(seed)`，"
        "消费顺序确定，离线重跑一遍随机数即可还原（`derive_episode_params.py`）。",
        "- **坐标**：SAPIEN 世界坐标，单位米，机器人 base 在 `(-0.615, 0, 0)`。表里是按钮本身的位置"
        "（PatternLock z=0.01；RouteStick 偶数下标 z=0.01）；规划实际下发的终点高度统一抬到 z=0.07。",
        "- **时长**：1 timestep = 1 个 env step = 0.05 s（控制频率 20 Hz），与数据集的采样频率一致。"
        "录像 fps=30 与 timestep 不等长，报告里不用视频帧。",
        "- **演示段 / 执行段**：同一组 move 在数据里出现两遍——前一遍 `is_video_demo=True` 是给模型看的示范，"
        "后一遍才是真正 rollout。下面的时长统计只算执行段。每条 episode 末尾还有一个几到十几 timestep 的收尾段，不算 move。",
        "",
        "## 按难度分组",
        "",
        "难度是决定 move 次数的唯一配置项（env 的 `configs[difficulty]`），所以统计一律按难度分开看。"
        "四个任务的难度分布相同：easy 52 / medium 24 / hard 24（每 split easy 26 / medium 12 / hard 12，难度循环 `211`，按 `episode % 4`）。",
        "",
    ]

    for level in DIFFICULTY_ORDER:
        cfg_lines = DIFFICULTY_CONFIG_NOTE[level]
        lines += [
            f"### {level}",
            "",
            cfg_lines,
            "",
            "| 任务 | 条数 | move 次数（min~max） | move 次数均值 | 单次 move 时长（min~max） | 单次 move 时长均值 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for key in SOURCES:
            rows = payload.get(key)
            if not rows:
                continue
            by_level = stats_by_difficulty(rows, durations.get(key, {}))
            stat = by_level.get(level)
            if stat is None:
                continue
            dur = (
                f"{stat['dur_range'][0]}~{stat['dur_range'][1]} ts"
                if stat["dur_range"]
                else "未生成"
            )
            dur_mean = f"{stat['dur_mean']:.1f} ts" if stat["dur_mean"] else "未生成"
            lines.append(
                f"| [{key}]({key}.md) | {stat['episodes']} | "
                f"{stat['moves_range'][0]}~{stat['moves_range'][1]} | {stat['moves_mean']:.2f} | "
                f"{dur} | {dur_mean} |"
            )
        lines.append("")

    if counting:
        lines += [
            "## Counting suite（BinFill / PickXtimes）",
            "",
            "这两个任务的结构与上面两个不同：**没有视频演示段**，动作是 pick / place 成对再加一次 press button，",
            "「动作次数」= BinFill 要放进 bin 的 cube 总数 / PickXtimes 同一动作的重复次数，"
            "直接写在 `setup/task_goal` 里。核心段数 = 2 × 动作次数 + 1（每条都验过）。",
            "",
        ]
        for level in DIFFICULTY_ORDER:
            lines += [
                f"### {level}",
                "",
                COUNTING_CONFIG_NOTE[level],
                "",
                "| 任务 | 条数 | 动作次数（min~max） | 动作次数均值 | "
                "pick up 时长 | put / place 时长 | press 时长 |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for key in COUNTING_SOURCES:
                rows = counting.get(key)
                if not rows:
                    continue
                hit = [r for r in rows if r["difficulty"] == level]
                if not hit:
                    continue
                actions = [r["actions"] for r in hit]
                buckets, unknown = durations_by_verb(hit)
                if unknown:
                    raise ValueError(f"{key}/{level} 有归类不到动词的子目标：{sorted(set(unknown))}")
                cells = []
                for verb, _ in VERB_LABELS:
                    values = buckets[verb]
                    cells.append(
                        f"{statistics.mean(values):.1f}（{min(values)}~{max(values)}）"
                        if values
                        else "—"
                    )
                lines.append(
                    f"| [{key}]({key}.md) | {len(hit)} | {min(actions)}~{max(actions)} | "
                    f"{statistics.mean(actions):.2f} | " + " | ".join(cells) + " |"
                )
            lines.append("")
        lines += [
            "表里是**均值（min~max）**，单位 timestep。每次动作产生一对 pick + place，"
            "每条 episode 末尾另有一段 press。",
            "",
        ]

    lengths = collect_lengths(durations, counting)
    if lengths:
        lines += build_length_section(lengths)

    lines += [
        "## 时长来源",
        "",
        "| 任务 | 数据来源 |",
        "| --- | --- |",
    ]
    for key in SOURCES:
        if payload.get(key):
            lines.append(f"| {key} | {ORIGIN[key]} |")
    for key in COUNTING_SOURCES:
        if counting and counting.get(key):
            lines.append(f"| {key} | {COUNTING_ORIGIN[key]} |")

    lines += [
        "",
        "## 校验",
        "",
        "1. **复算 vs h5 逐条对拍**（`cross_check.py`）：比对 seed、难度、move 次数（= h5 执行段数）、"
        "move 语义串（= h5 段名串），并检查 h5 内部演示段与执行段是否同一组 move。"
        "**四个源 200 条全部一致**（val 见 `outputs/cross_check.json`，test 见 `outputs/cross_check_test.json`）。"
        "语义串是从复算坐标算出来的方向，所以这一项同时验证了坐标。",
        "2. **test seed 一致性**（`check_test_seeds.py`）：本轮实跑 100 条全部 attempt=0 一次通过，"
        "seed 与 test metadata **逐条相等，0 条不一致**，即拿到的时长就是原版 seed 下的时长"
        "（`outputs/test_seed_check.json`）。",
        "3. **口径自洽（Imitation）**：RouteStick 满足「整条时长 = move 段数 × 50」；"
        "两个 env 的 move 段数都是偶数（演示段与执行段成对）。",
        "4. **goal 解析自洽（Counting）**：`核心段数 == 2 × 动作次数 + 1`，**四个源 200 条全中**；"
        "另外 val 侧用 h5 的 `setup/task_goal` 校验过从 eval `video` 字段解析的 goal，48/48 相同。",
        "5. **Counting 的 test seed 锁死**：BinFill / PickXtimes 的 test metadata 里有 9 条 seed 尾号非 0，"
        "由 `run_test_fixed_seed.py` 逐条锁死 seed、`max_attempts=1` 实跑。100 条全部成功，"
        "seed 与 metadata 逐条相等、0 条不一致。",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 Markdown 报告")
    parser.add_argument("--derived", default=str(HERE / "outputs" / "derived_params.json"))
    parser.add_argument(
        "--durations",
        action="append",
        default=None,
        help="时长 JSON，可重复（多份会按源名合并）",
    )
    parser.add_argument("--out-dir", default=str(HERE / "reports"))
    parser.add_argument(
        "--counting",
        action="append",
        default=None,
        help="extract_task_params.py 出的 BinFill / PickXtimes 参数 JSON，可重复",
    )
    parser.add_argument(
        "--eval-section",
        default=str(HERE / "reports" / "eval_section.md"),
        help="由 plot_eval_success.py 生成的成功率分析段落；存在则拼到总览末尾",
    )
    args = parser.parse_args(argv)

    raw_payload = json.loads(Path(args.derived).read_text(encoding="utf-8"))
    raw_durations: dict[str, Any] = {}
    for path in args.durations or [str(HERE / "outputs" / "durations_val.json")]:
        raw_durations.update(json.loads(Path(path).read_text(encoding="utf-8")))
    raw_counting: dict[str, Any] = {}
    for path in args.counting or []:
        raw_counting.update(json.loads(Path(path).read_text(encoding="utf-8")))

    # 一律先按任务把 test / val 合并；每条记录仍带 split，明细里逐条标出来源
    payload = merge_by_task(raw_payload, SOURCES)
    durations = merge_by_task(raw_durations, SOURCES)
    counting = merge_by_task(raw_counting, COUNTING_SOURCES)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for task in SOURCES:
        rows = payload.get(task)
        if not rows:
            continue
        text = build_source_report(task, rows, durations.get(task, []))
        (out_dir / f"{task}.md").write_text(text, encoding="utf-8")
        print(f"已写出 {out_dir / (task + '.md')}")
    for task in COUNTING_SOURCES:
        rows = counting.get(task)
        if not rows:
            continue
        (out_dir / f"{task}.md").write_text(build_counting_report(task, rows), encoding="utf-8")
        print(f"已写出 {out_dir / (task + '.md')}")

    summary = build_summary(payload, durations, counting)
    section_path = Path(args.eval_section) if args.eval_section else None
    if section_path is not None and section_path.exists():
        summary = summary.rstrip("\n") + "\n\n" + section_path.read_text(encoding="utf-8")
        print(f"已拼入 {section_path}")
    (out_dir / "README.md").write_text(summary, encoding="utf-8")
    print(f"已写出 {out_dir / 'README.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
