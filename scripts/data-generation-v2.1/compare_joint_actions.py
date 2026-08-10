#!/usr/bin/env python3
"""独立的 joint_action 逐元素对拍：把生成数据与官方参考数据逐个元素比对。

这是「与外部基准对齐」的检查，跟 `verify_joint_action_bitexact.py` 的自对拍是两回事：

- 本脚本比的是「我们生成的 vs 官方发布的」，允许 1e-8 量级的容差，因为两边是不同机器、
  不同时间跑出来的，规划器退避到 RRTStar 时会有采样差异；
- 自对拍比的是「同一份代码 flow 关 vs flow 开」，要求**逐位相等**，那才是「只增不改」的验收口径。

对拍会保留最大差异出现的位置（任务 / episode / timestep / 元素下标 / 两边的取值），差异超标时
可以直接定位到具体那一步，不必再翻日志。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np

from validate_generated_dataset_contract import (
    MAX_EPISODES,
    REFERENCE_ROOT,
    DatasetContractError,
    add_error,
    episode_groups,
    parse_tasks,
    timestep_indices,
)


class JointActionComparisonError(RuntimeError):
    """joint_action 对拍的入参不满足明确约定。"""


def compare_joint_actions(
    generated_root: str | Path,
    reference_root: str | Path,
    tasks: Sequence[str],
    episodes: Sequence[int],
    max_abs_diff: float = 1e-8,
) -> dict[str, Any]:
    """在指定范围内逐元素比对 action/joint_action，并保留最大差异出现的位置。"""
    output = Path(generated_root).expanduser().resolve()
    reference_root_path = Path(reference_root).expanduser().resolve()
    ordered_tasks = list(tasks)
    episode_indices = list(episodes)
    if not ordered_tasks or len(ordered_tasks) != len(set(ordered_tasks)):
        raise JointActionComparisonError("对拍任务列表不能为空，且不能有重复")
    if not episode_indices or episode_indices != list(range(len(episode_indices))):
        raise JointActionComparisonError("对拍的 episode 必须是从 0 开始的连续区间")
    if not np.isfinite(max_abs_diff) or max_abs_diff < 0:
        raise JointActionComparisonError("max_abs_diff 必须是非负的有限值")

    section: dict[str, Any] = {
        "joint_vector_count": 0,
        "joint_element_count": 0,
        "different_element_count": 0,
        "max_abs_diff": None,
        "max_abs_diff_location": None,
        "max_allowed_abs_diff": float(max_abs_diff),
        "error_count": 0,
        "errors": [],
    }
    for task in ordered_tasks:
        reference_path = reference_root_path / f"record_dataset_{task}.h5"
        generated_path = output / f"record_dataset_{task}.h5"
        if not reference_path.is_file() or not generated_path.is_file():
            add_error(section, f"{task}: 参与对拍的文件不存在")
            continue
        try:
            with h5py.File(reference_path, "r") as reference, h5py.File(
                generated_path,
                "r",
            ) as generated:
                reference_groups = episode_groups(reference, f"reference/{task}", section)
                generated_groups = episode_groups(generated, f"generated/{task}", section)
                for episode in episode_indices:
                    left = reference_groups.get(episode)
                    right = generated_groups.get(episode)
                    if left is None or right is None:
                        add_error(
                            section,
                            f"{task}/episode_{episode}: 参考侧或生成侧缺少该 episode",
                        )
                        continue
                    left_steps, left_errors = timestep_indices(
                        left,
                        f"reference/{task}/episode_{episode}",
                    )
                    right_steps, right_errors = timestep_indices(
                        right,
                        f"generated/{task}/episode_{episode}",
                    )
                    for error in left_errors + right_errors:
                        add_error(section, error)
                    if left_errors or right_errors or left_steps != right_steps:
                        if not left_errors and not right_errors:
                            add_error(section, f"{task}/episode_{episode}: timestep 集合不一致")
                        continue
                    for timestep in left_steps:
                        location = f"{task}/episode_{episode}/timestep_{timestep}"
                        try:
                            reference_joint = left[f"timestep_{timestep}"]["action"][
                                "joint_action"
                            ]
                            generated_joint = right[f"timestep_{timestep}"]["action"][
                                "joint_action"
                            ]
                        except KeyError:
                            add_error(section, f"{location}: 缺少 action/joint_action")
                            continue
                        if (
                            not isinstance(reference_joint, h5py.Dataset)
                            or not isinstance(generated_joint, h5py.Dataset)
                        ):
                            add_error(section, f"{location}: joint_action 不是 dataset")
                            continue
                        if (
                            tuple(reference_joint.shape) != tuple(generated_joint.shape)
                            or np.dtype(reference_joint.dtype)
                            != np.dtype(generated_joint.dtype)
                        ):
                            add_error(section, f"{location}: joint_action 的 shape/dtype 不一致")
                            continue
                        if (
                            tuple(reference_joint.shape) != (8,)
                            or np.dtype(reference_joint.dtype) != np.dtype(np.float64)
                        ):
                            add_error(section, f"{location}: joint_action 不是 (8,) float64")
                            continue
                        reference_values = np.asarray(reference_joint[()])
                        generated_values = np.asarray(generated_joint[()])
                        if not (
                            np.all(np.isfinite(reference_values))
                            and np.all(np.isfinite(generated_values))
                        ):
                            add_error(section, f"{location}: joint_action 含有非有限值")
                            continue
                        delta = np.abs(
                            reference_values.astype(np.float64)
                            - generated_values.astype(np.float64)
                        )
                        section["joint_vector_count"] += 1
                        section["joint_element_count"] += int(delta.size)
                        section["different_element_count"] += int(np.count_nonzero(delta != 0.0))
                        maximum = float(np.max(delta))
                        if (
                            section["max_abs_diff"] is None
                            or maximum > section["max_abs_diff"]
                        ):
                            index = int(np.argmax(delta))
                            section["max_abs_diff"] = maximum
                            section["max_abs_diff_location"] = {
                                "task": task,
                                "episode": episode,
                                "timestep": timestep,
                                "element_index": index,
                                "reference_value": float(reference_values.reshape(-1)[index]),
                                "generated_value": float(generated_values.reshape(-1)[index]),
                            }
        except OSError as exc:
            add_error(section, f"{task}: 读取待对拍的 HDF5 失败：{exc}")

    if section["joint_element_count"] == 0:
        add_error(section, "没有任何 joint_action 元素被比对")
    section["within_max_abs_diff"] = bool(
        section["max_abs_diff"] is not None
        and section["max_abs_diff"] <= float(max_abs_diff)
    )
    section["passed"] = bool(
        section["error_count"] == 0 and section["within_max_abs_diff"]
    )
    return section


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="joint_action 与官方参考数据的逐元素对拍")
    parser.add_argument("--output-dir", required=True, help="已存在的生成产物目录")
    parser.add_argument("--env", "--environment", default="all", help="all，或逗号分隔的环境名列表")
    parser.add_argument("--episodes", type=int, default=MAX_EPISODES, help="每个环境从 episode 0 起参与对拍的 episode 数量")
    parser.add_argument(
        "--reference-root",
        default=str(REFERENCE_ROOT),
        help="官方参考 HDF5 所在目录",
    )
    parser.add_argument("--max-abs-diff", type=float, default=1e-8, help="允许的最大绝对差异")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        if not 1 <= args.episodes <= MAX_EPISODES:
            raise JointActionComparisonError(
                f"--episodes 必须在 1..{MAX_EPISODES} 之间"
            )
        result = compare_joint_actions(
            args.output_dir,
            args.reference_root,
            parse_tasks(args.env),
            list(range(args.episodes)),
            args.max_abs_diff,
        )
    except (DatasetContractError, JointActionComparisonError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
