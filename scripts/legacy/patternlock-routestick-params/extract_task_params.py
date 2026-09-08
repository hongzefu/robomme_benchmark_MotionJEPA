"""从 h5 提取 BinFill / PickXtimes 的逐 episode 动作参数。

这两个 env 与 PatternLock / RouteStick 的结构不同，不走离线复算：

- **没有视频演示段**（不在 examples/robomme/utils.py 的 TASK_WITH_VIDEO_DEMO 里），
  所以段数就是实际动作次数，不需要除以 2。
- **动作次数与颜色组成写在 `setup/task_goal` 里**（BinFill 是要放几个什么颜色的 cube，
  PickXtimes 是重复几次、什么颜色），直接解析即可，比复算 RNG 稳。
- **坐标**取 `action/waypoint_action`（7 维 = xyz + rpy + gripper，单位米）。注意不能取段边界那一帧：
  切段时 waypoint 往往还停在上一段的值上（实测 BinFill ep0 的第二个 pick 段，首帧仍是上一段 put 的
  bin 上方点）。每段内部的关键点是一串——pick 段是「接近点 z=0.15 → 抓取点 z=0.02 → 抬起 z=0.15」，
  press 段是「接近 z=0.15 → 按下 z=0.007」，put 段只有一个 bin 上方松手点 z=0.2。
  因此取**段内 z 最低的那个点**作为该段的目标点：pick 段即 cube 位置，press 段即按钮位置，
  put 段即松手点。这样既排掉了首帧残留，语义也明确。

段结构（实测）：BinFill 与 PickXtimes 都是「pick / place 成对 + 末尾一个 press button」，
再加一个 `All tasks completed` 收尾段，因此 `核心段数 == 2 × 动作次数 + 1`。这条恒等式被用作
goal 解析是否正确的自洽判据。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np

NON_MOVE_SUBGOALS = {"All tasks completed", "NO RECORD"}
WORD_TO_INT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
COLORS = ("red", "blue", "green")


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def parse_goal(task: str, goal: str) -> dict[str, Any]:
    """从 task_goal 原文解析动作次数与颜色组成。

    BinFill  : "put two red cubes, one blue cube and two green cubes into the bin, then press ..."
    PickXtimes: "pick up the blue cube and place it on the target, repeating this action four times, ..."
               （只做一次时没有 "repeating ..." 从句）
    """
    text = goal.lower()
    if task == "BinFill":
        counts = {color: 0 for color in COLORS}
        for word, color in re.findall(r"(one|two|three|four|five|six|seven|eight) (red|blue|green) cubes?", text):
            counts[color] += WORD_TO_INT[word]
        total = sum(counts.values())
        return {
            "actions": total,
            "color_counts": counts,
            "color_kinds": sum(1 for v in counts.values() if v),
            "composition": "+".join(f"{v}{c[0].upper()}" for c, v in counts.items() if v),
        }
    match = re.search(r"repeating this action (one|two|three|four|five|six|seven|eight) times", text)
    repeats = WORD_TO_INT[match.group(1)] if match else 1
    color_match = re.search(r"pick up the (red|blue|green) cube", text)
    return {
        "actions": repeats,
        "cube_color": color_match.group(1) if color_match else "unknown",
        "color_kinds": 1,
        "composition": f"{repeats}×{color_match.group(1) if color_match else '?'}",
    }


def extract_episode(task: str, group: h5py.Group) -> dict[str, Any]:
    timesteps = sorted(int(name.split("_")[1]) for name in group if name.startswith("timestep_"))
    segments: list[dict[str, Any]] = []
    waypoints: list[np.ndarray | None] = []
    for step in timesteps:
        node = group[f"timestep_{step}"]
        info = node["info"]
        waypoint = node["action"]["waypoint_action"][()]
        waypoints.append(None if np.all(np.isnan(waypoint)) else np.asarray(waypoint, dtype=float))
        if not bool(info["is_subgoal_boundary"][()]):
            continue
        segments.append(
            {
                "start_timestep": step,
                "subgoal": _text(info["simple_subgoal"][()]),
                "is_video_demo": bool(info["is_video_demo"][()]),
            }
        )
    total = len(timesteps)
    for index, segment in enumerate(segments):
        end = segments[index + 1]["start_timestep"] if index + 1 < len(segments) else total
        segment["end_timestep"] = end - 1
        segment["n_timesteps"] = end - segment["start_timestep"]
        # 段内 z 最低的关键点才是这次动作真正够到的位置；段首帧常残留上一段的值，不能用
        inside = [w for w in waypoints[segment["start_timestep"] : end] if w is not None]
        lowest = min(inside, key=lambda w: w[2]) if inside else None
        segment["target_xyz"] = (
            None if lowest is None else [round(float(v), 4) for v in lowest[:3]]
        )

    core = [s for s in segments if s["subgoal"] not in NON_MOVE_SUBGOALS]
    tail = [s for s in segments if s["subgoal"] in NON_MOVE_SUBGOALS]
    setup = group["setup"]
    goals = [_text(x) for x in setup["task_goal"][()]]
    parsed = parse_goal(task, goals[0])

    return {
        "seed": int(setup["seed"][()]),
        "difficulty": _text(setup["difficulty"][()]),
        "task_goal": goals[0],
        **parsed,
        "n_timesteps_total": total,
        "n_core_segments": len(core),
        "completed_tail_timesteps": sum(s["n_timesteps"] for s in tail),
        "has_video_demo": any(s["is_video_demo"] for s in segments),
        # 恒等式：核心段 = 每次动作的 pick + place 两段，再加末尾一个 press button
        "segments_match_goal": len(core) == 2 * parsed["actions"] + 1,
        "durations": [s["n_timesteps"] for s in core],
        "subgoals": [s["subgoal"] for s in core],
        "segments": segments,
    }


def extract(task: str, pattern: str, episodes: list[int] | None) -> dict[int, dict[str, Any]]:
    paths = sorted(Path().glob(pattern)) if any(ch in pattern for ch in "*?[") else [Path(pattern)]
    if not paths:
        raise FileNotFoundError(f"没有匹配到 h5：{pattern}")
    out: dict[int, dict[str, Any]] = {}
    for path in paths:
        with h5py.File(path, "r") as handle:
            available = sorted(
                int(name.split("_")[1]) for name in handle if name.startswith("episode_")
            )
            wanted = available if episodes is None else [e for e in episodes if e in available]
            for episode in wanted:
                out[episode] = extract_episode(task, handle[f"episode_{episode}"])
    return dict(sorted(out.items()))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="提取 BinFill / PickXtimes 的逐 episode 动作参数")
    parser.add_argument(
        "--h5",
        action="append",
        required=True,
        help="格式 <Task>-<split>=<h5 路径或 glob>，可重复；Task 用于选择 goal 解析规则",
    )
    parser.add_argument("--episodes", default="0-49", help="episode 范围，如 0-49，或 all")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[2] / "patternlock-routestick-params" / "outputs" / "counting_params.json"),
    )
    args = parser.parse_args(argv)

    if args.episodes == "all":
        episodes = None
    else:
        low, high = args.episodes.split("-")
        episodes = list(range(int(low), int(high) + 1))

    payload: dict[str, dict[str, Any]] = {}
    failures = 0
    for spec in args.h5:
        key, _, raw_path = spec.partition("=")
        task = key.split("-")[0]
        rows = extract(task, raw_path, episodes)
        payload[key] = {str(ep): row for ep, row in rows.items()}
        bad = [ep for ep, row in rows.items() if not row["segments_match_goal"]]
        failures += len(bad)
        actions = [row["actions"] for row in rows.values()]
        durations = [d for row in rows.values() for d in row["durations"]]
        print(
            f"{key}: {len(rows)} 条，动作次数 {min(actions)}~{max(actions)}，"
            f"单段时长 {min(durations)}~{max(durations)} timestep（均值 {sum(durations)/len(durations):.1f}）"
            f"，段数=2×次数+1 自洽 {len(rows)-len(bad)}/{len(rows)}"
        )
        if bad:
            print(f"  ⚠ 不自洽的 episode：{bad}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出 {out_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
