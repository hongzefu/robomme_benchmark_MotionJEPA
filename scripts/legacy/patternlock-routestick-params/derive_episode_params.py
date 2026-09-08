"""离线复算 PatternLock / RouteStick 每个 episode 的动作参数（move 次数、落点坐标、方向）。

原理：两个 env 的场景随机段都只用一个局部 ``torch.Generator(seed)``，消费顺序完全确定，
因此不必启动 SAPIEN 仿真，按同样的顺序重跑一遍随机数即可还原 ``selected_buttons``。
路径生成直接 import env 自己用的 ``find_path_0_to_8`` / ``generate_dynamic_walk``，不复制实现。

seed 与 difficulty 一律读 ``src/robomme/env_metadata/{split}/record_dataset_{task}_metadata.json``，
不用公式反推（历史上存在 attempt 尾号例外，如 PatternLock-val ep37 = 1153701）。

时长（每次 move 占多少 timestep）不在本脚本范围内——它由运动规划器跑出来，只能从 h5 数帧，
见 extract_move_durations.py。
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import torch

from robomme.robomme_env.utils.adjacent import find_path_0_to_8
from robomme.robomme_env.utils.route import generate_dynamic_walk
from robomme.robomme_env.utils.subgoal_evaluate_func import direction as compass_direction

REPO_ROOT = Path(__file__).resolve().parents[3]
METADATA_ROOT = REPO_ROOT / "src" / "robomme" / "env_metadata"

# 与 PatternLock.configs / RouteStick.configs 逐字一致
PATTERNLOCK_CONFIGS = {
    "easy": {"grid": 3, "length": [2, 4]},
    "medium": {"grid": 4, "length": [3, 5]},
    "hard": {"grid": 5, "length": [4, 8]},
}
ROUTESTICK_CONFIGS = {
    "easy": {"length": [2, 3], "backtrack": False},
    "medium": {"length": [4, 5], "backtrack": False},
    "hard": {"length": [4, 7], "backtrack": True},
}

PATTERNLOCK_MAX_ATTEMPTS = 1000  # PatternLock._load_scene 的 max_attempts
ROUTESTICK_BUTTON_INDICES = [0, 2, 4, 6, 8]  # 可落点（偶数下标），奇数下标是障碍长方体
ROUTESTICK_CUBE_INDICES = [1, 3, 5, 7]  # 障碍柱，每个消费一次 torch.rand(3)
MOVE_TARGET_Z = 0.07  # solve_swingonto / solve_swingonto_withDirection 实际下发的终点高度


class _PoseShim:
    """让 subgoal_evaluate_func.direction() 能吃到离线算出的 xy（它只读 .pose.p）。"""

    class _P:
        def __init__(self, p):
            self.p = p

    def __init__(self, xy):
        self.pose = _PoseShim._P([float(xy[0]), float(xy[1]), 0.0])


def load_metadata(task: str, split: str) -> list[dict[str, Any]]:
    path = METADATA_ROOT / split / f"record_dataset_{task}_metadata.json"
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload["records"]
    records.sort(key=lambda item: item["episode"])
    return records


def derive_patternlock(seed: int, difficulty: str) -> dict[str, Any]:
    """复现 PatternLock._load_scene 的随机段。

    注意：格点构建不消耗 RNG；失败的 attempt 同样消耗 RNG，必须逐次模拟；
    1000 次都不满足长度约束时（for...else）沿用最后一次的路径。
    """
    generator = torch.Generator()
    generator.manual_seed(seed)

    grid = PATTERNLOCK_CONFIGS[difficulty]["grid"]
    length_range = PATTERNLOCK_CONFIGS[difficulty]["length"]
    num_targets = grid * grid
    center = (grid - 1) / 2

    path_nodes: list[int] = []
    attempt_used = -1
    length_ok = False
    for attempt in range(PATTERNLOCK_MAX_ATTEMPTS):
        node_choices = torch.randperm(num_targets, generator=generator)[:2]
        start_node, end_node = node_choices.tolist()
        path_nodes, _, _, _ = find_path_0_to_8(
            start=start_node,
            target=end_node,
            R=grid,
            C=grid,
            diagonals=True,
            generator=generator,
        )
        attempt_used = attempt
        if length_range[0] <= len(path_nodes) <= length_range[1]:
            length_ok = True
            break

    def button_xy(index: int) -> tuple[float, float]:
        row, col = divmod(index, grid)
        return (-0.1 + (row - center) * 0.1, 0.0 + (col - center) * 0.1)

    coords = [button_xy(i) for i in path_nodes]
    shims = [_PoseShim(xy) for xy in coords]
    directions = [
        f"move {compass_direction(shims[i + 1], shims[i])}" for i in range(len(shims) - 1)
    ]

    return {
        "grid": grid,
        "moves": len(path_nodes) - 1,
        "path_nodes": path_nodes,
        "coords_xyz": [[round(x, 6), round(y, 6), 0.01] for x, y in coords],
        "move_target_xyz": [[round(x, 6), round(y, 6), MOVE_TARGET_Z] for x, y in coords],
        "move_directions": directions,
        "attempt_used": attempt_used,
        "length_constraint_met": length_ok,
    }


def derive_routestick(seed: int, difficulty: str) -> dict[str, Any]:
    """复现 RouteStick._load_scene 的随机段（顺序：theta → 4×柱颜色 → steps → walk → 绕行方向）。"""
    generator = torch.Generator()
    generator.manual_seed(seed)

    theta = math.radians((torch.rand(1, generator=generator).item() * 60) - 30)
    for _ in ROUTESTICK_CUBE_INDICES:
        torch.rand(3, generator=generator)  # 障碍柱颜色，值本身不用但必须消费

    length_min, length_max = ROUTESTICK_CONFIGS[difficulty]["length"]
    allow_backtracking = bool(ROUTESTICK_CONFIGS[difficulty]["backtrack"])
    steps = int(torch.randint(length_min, length_max + 1, (1,), generator=generator).item())
    traj = generate_dynamic_walk(
        ROUTESTICK_BUTTON_INDICES,
        steps=steps,
        allow_backtracking=allow_backtracking,
        generator=generator,
    )
    swing_directions = [
        "clockwise" if torch.rand(1, generator=generator).item() < 0.5 else "counterclockwise"
        for _ in traj[1:]
    ]

    def button_xy(index: int) -> tuple[float, float]:
        orig_x, orig_y = -0.1, (index - 4) * 0.07
        return (
            orig_x * math.cos(theta) - orig_y * math.sin(theta),
            orig_x * math.sin(theta) + orig_y * math.cos(theta),
        )

    coords = [button_xy(i) for i in traj]
    # _stick_side(current, prev)：y 更大 = left（机器人视角已反转）
    sides = ["left" if coords[i + 1][1] > coords[i][1] else "right" for i in range(len(coords) - 1)]
    subgoals = [
        f"move to the nearest {side} target by circling around the stick {swing}"
        for side, swing in zip(sides, swing_directions)
    ]

    return {
        "theta_deg": round(math.degrees(theta), 6),
        "moves": steps,
        "path_nodes": list(traj),
        "coords_xyz": [
            [round(x, 6), round(y, 6), 0.01 if idx in (0, 2, 4, 6, 8) else -0.01]
            for idx, (x, y) in zip(traj, coords)
        ],
        "move_target_xyz": [[round(x, 6), round(y, 6), MOVE_TARGET_Z] for x, y in coords],
        "swing_directions": swing_directions,
        "stick_sides": sides,
        "move_directions": subgoals,
        "allow_backtracking": allow_backtracking,
    }


DERIVERS = {"PatternLock": derive_patternlock, "RouteStick": derive_routestick}


def derive_source(task: str, split: str) -> list[dict[str, Any]]:
    deriver = DERIVERS[task]
    rows = []
    for record in load_metadata(task, split):
        seed = int(record["seed"])
        difficulty = record["difficulty"]
        row = {
            "task": task,
            "split": split,
            "episode": int(record["episode"]),
            "seed": seed,
            "difficulty": difficulty,
        }
        row.update(deriver(seed, difficulty))
        rows.append(row)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="离线复算 PatternLock / RouteStick 的 episode 动作参数")
    parser.add_argument("--tasks", default="PatternLock,RouteStick")
    parser.add_argument("--splits", default="test,val")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[2] / "patternlock-routestick-params" / "outputs" / "derived_params.json"),
    )
    args = parser.parse_args(argv)

    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    splits = [item.strip() for item in args.splits.split(",") if item.strip()]

    payload: dict[str, list[dict[str, Any]]] = {}
    for split in splits:
        for task in tasks:
            key = f"{task}-{split}"
            rows = derive_source(task, split)
            payload[key] = rows
            moves = [row["moves"] for row in rows]
            print(
                f"{key}: {len(rows)} 条，move 次数 {min(moves)}~{max(moves)}，"
                f"合计 {sum(moves)} 次 move"
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"已写出 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
