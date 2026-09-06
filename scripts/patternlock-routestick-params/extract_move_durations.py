"""从 h5 里按子目标边界切段，得到每次 move 的时长（timestep 数）。

时长口径与 dataset 的采样频率对齐：1 timestep = 1 个 env step = 0.05 s（控制频率 20 Hz）。
录像 fps=30 与 timestep 不等长，本脚本一律不用视频帧。

切段规则：``info/is_subgoal_boundary`` 为 True 的 timestep 是一段的起点，段名读 ``info/simple_subgoal``，
``info/is_video_demo`` 区分演示段与执行段。task_list 里的 "NO RECORD" 段（首步到位、reset）不进 h5，
所以 h5 里只剩 move 段与一个 "All tasks completed" 尾段；同一组 move 出现两遍（先演示后执行），
真实 move 次数 = move 段数 / 2。尾段不是 move，单独记进 completed_tail_timesteps，不计入时长统计。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py


# 这两个段名不是 move：前者是每条 episode 末尾的收尾段，后者理论上不会落进 h5（保险起见一并排除）
NON_MOVE_SUBGOALS = {"All tasks completed", "NO RECORD"}


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def extract_episode(group: h5py.Group) -> dict[str, Any]:
    timesteps = sorted(
        (int(name.split("_")[1]) for name in group if name.startswith("timestep_")),
    )
    segments: list[dict[str, Any]] = []
    for step in timesteps:
        info = group[f"timestep_{step}"]["info"]
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

    tail = [s for s in segments if s["subgoal"] in NON_MOVE_SUBGOALS]
    moves = [s for s in segments if s["subgoal"] not in NON_MOVE_SUBGOALS]
    demo = [s for s in moves if s["is_video_demo"]]
    exec_ = [s for s in moves if not s["is_video_demo"]]
    setup = group["setup"]
    return {
        "seed": int(setup["seed"][()]),
        "difficulty": _text(setup["difficulty"][()]),
        "n_timesteps_total": total,
        "n_segments": len(segments),
        "n_move_segments": len(moves),
        "completed_tail_timesteps": sum(s["n_timesteps"] for s in tail),
        "demo_moves": len(demo),
        "exec_moves": len(exec_),
        "demo_durations": [s["n_timesteps"] for s in demo],
        "exec_durations": [s["n_timesteps"] for s in exec_],
        "demo_subgoals": [s["subgoal"] for s in demo],
        "exec_subgoals": [s["subgoal"] for s in exec_],
        "segments": segments,
    }


def extract_h5(pattern: str, episodes: list[int] | None = None) -> dict[int, dict[str, Any]]:
    """pattern 可以是单个 h5 文件，也可以是 glob（逐 episode h5 的目录用得上）。"""
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
                out[episode] = extract_episode(handle[f"episode_{episode}"])
    return dict(sorted(out.items()))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从 h5 提取每次 move 的 timestep 时长")
    parser.add_argument(
        "--h5",
        action="append",
        required=True,
        help="格式 <源名>=<h5 路径或 glob>，可重复；glob 用于逐 episode h5 的目录",
    )
    parser.add_argument("--episodes", default="0-49", help="episode 范围，如 0-49，或 all")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "outputs" / "durations.json"),
    )
    args = parser.parse_args(argv)

    if args.episodes == "all":
        episodes = None
    else:
        low, high = args.episodes.split("-")
        episodes = list(range(int(low), int(high) + 1))

    payload: dict[str, dict[str, Any]] = {}
    for spec in args.h5:
        key, _, raw_path = spec.partition("=")
        rows = extract_h5(raw_path, episodes)
        payload[key] = {str(ep): row for ep, row in rows.items()}
        move_counts = [row["exec_moves"] for row in rows.values()]
        durations = [d for row in rows.values() for d in row["exec_durations"]]
        print(
            f"{key}: {len(rows)} 条，执行段 move 次数 {min(move_counts)}~{max(move_counts)}，"
            f"单次 move 时长 {min(durations)}~{max(durations)} timestep"
            f"（均值 {sum(durations) / len(durations):.1f}）"
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"已写出 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
