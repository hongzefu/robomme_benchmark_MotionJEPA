#!/usr/bin/env python3
"""官方比较器的稀疏范围适配（方案第二部分 9.6，闸门 G5）。

官方两个函数都要求 episode 从 0 连续：
``validate_generated_dataset_contract`` 与 ``compare_joint_actions`` 都有
``episode_indices != list(range(len(episode_indices)))`` 的守卫，而本轮的 144 条子集
每环境是 ``[0,1,2,3,4,6,7,10,11]``，会在读 HDF5 之前就被拒；官方 CLI 的
``--episodes 9`` 又会误选 0～8。

本模块**不改官方源文件**，而是从冻结的官方源码目录导入原模块，直接复用其
``add_error/episode_groups/timestep_indices/_audit_metadata/_audit_file/_summary``
等比较核心，只重写最外层的范围守卫与预期集合：

* ``validate_manifest_scope``：显式原 episode 列表逐条回查官方 metadata，
  拒绝重复、额外、跨任务与身份不符。
* ``validate_generated_subset``：生成文件的 episode 集合必须恰为所选集合，
  发布参考文件仍按原方式检查（不要求恰好相等）后只比较所选条目。
* ``compare_joint_actions_subset``：只遍历显式选定的键，字段检查、dtype／shape、
  ``delta != 0`` 计数、最大差定位与 ``1e-8`` 阈值一律不变。

``check`` 子命令跑 G5 离线夹具并输出
``COMPARATOR_SCOPE=PASS contiguous_mismatch=0 sparse_mismatch=0 invalid_accepts=0``。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]


class ComparatorScopeError(RuntimeError):
    """请求的比较范围不合法（重复、额外、跨任务或身份不符）。"""


# --------------------------------------------------------------------------
# 官方模块加载
# --------------------------------------------------------------------------


def load_official(official_root: str | Path):
    """从冻结的官方源码目录导入两个原比较器模块，返回 (contract, comparison)。"""
    root = Path(official_root).resolve()
    script_dir = root / "scripts" / "data-generation"
    target = script_dir / "validate_generated_dataset_contract.py"
    if not target.exists():
        raise ComparatorScopeError(f"官方比较器不存在：{target}")
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import compare_joint_actions as comparison  # noqa: PLC0415  官方固定源码
    import validate_generated_dataset_contract as contract  # noqa: PLC0415

    for module in (contract, comparison):
        if Path(module.__file__).resolve().parent != script_dir:
            raise ComparatorScopeError(f"导入到的不是官方比较器：{module.__file__}")
    return contract, comparison


# --------------------------------------------------------------------------
# 范围校验
# --------------------------------------------------------------------------


def validate_manifest_scope(
    rows: Sequence[Mapping[str, Any]],
    records_by_task: Mapping[str, Mapping[int, Mapping[str, Any]]],
    all_tasks: Sequence[str],
) -> dict[str, list[int]]:
    """把 manifest 行整理成 task → 有序 episode 列表，并逐条回查官方 metadata。

    拒绝：空范围、未知任务、同任务内重复 episode、官方 metadata 里没有的 episode、
    以及 seed／difficulty／task 与官方记录不符的身份。
    """
    if not rows:
        raise ComparatorScopeError("比较范围为空")
    grouped: dict[str, list[int]] = {}
    for row in rows:
        task = str(row["task"])
        if task not in all_tasks:
            raise ComparatorScopeError(f"未知环境：{task}")
        if task not in records_by_task:
            raise ComparatorScopeError(f"官方 metadata 缺少环境：{task}")
        episode = int(row["episode"])
        official = records_by_task[task].get(episode)
        if official is None:
            raise ComparatorScopeError(f"{task}/episode_{episode} 不在官方 metadata 内")
        if int(official["seed"]) != int(row["seed"]):
            raise ComparatorScopeError(
                f"{task}/episode_{episode} seed 不符：manifest={row['seed']} official={official['seed']}"
            )
        if str(official["difficulty"]) != str(row["difficulty"]):
            raise ComparatorScopeError(
                f"{task}/episode_{episode} difficulty 不符："
                f"manifest={row['difficulty']} official={official['difficulty']}"
            )
        if str(official["task"]) != task:
            raise ComparatorScopeError(f"{task}/episode_{episode} 记录的 task 不符")
        bucket = grouped.setdefault(task, [])
        if episode in bucket:
            raise ComparatorScopeError(f"{task}/episode_{episode} 重复")
        bucket.append(episode)
    return {task: sorted(episodes) for task, episodes in grouped.items()}


# --------------------------------------------------------------------------
# 合同校验（稀疏范围）
# --------------------------------------------------------------------------


def validate_generated_subset(
    generated_root: str | Path,
    episodes_by_task: Mapping[str, Sequence[int]],
    records_by_task: Mapping[str, Mapping[int, Mapping[str, Any]]],
    reference_root: str | Path,
    contract,
) -> dict[str, Any]:
    """官方 ``validate_generated_dataset_contract`` 的稀疏范围版。

    与原函数的**唯一**差异：范围由「从 0 连续的 episodes」改为「每 task 的显式
    原 episode 列表」，元数据按该列表投影；审计、汇总与通过判定全部调用原函数。
    """
    output = Path(generated_root).expanduser().resolve()
    reference = Path(reference_root).expanduser().resolve()
    ordered_tasks = [task for task in contract.ALL_TASKS if task in episodes_by_task]
    if not ordered_tasks:
        raise ComparatorScopeError("校验范围为空")

    generated, official, metadata = [], [], []
    expected = 0
    for task in ordered_tasks:
        episode_indices = list(episodes_by_task[task])
        if len(episode_indices) != len(set(episode_indices)):
            raise ComparatorScopeError(f"{task}: episode 列表有重复")
        records_for_task = records_by_task[task]
        if any(episode not in records_for_task for episode in episode_indices):
            raise ComparatorScopeError(f"{task}: 官方 metadata 缺少请求的 episode")
        records = [records_for_task[episode] for episode in episode_indices]
        expected += len(episode_indices)
        metadata.append(
            contract._audit_metadata(
                output / f"record_dataset_{task}_metadata.json", task, records
            )
        )
        generated.append(
            contract._audit_file(
                output / f"record_dataset_{task}.h5",
                task,
                records_for_task,
                episode_indices,
                True,  # 生成文件的 episode 集合必须恰为所选集合
                "generated",
            )
        )
        official.append(
            contract._audit_file(
                reference / f"record_dataset_{task}.h5",
                task,
                records_for_task,
                episode_indices,
                False,  # 发布参考集仍是完整 0～99，只比较所选条目
                "official",
            )
        )

    generated_summary = contract._summary(generated)
    official_summary = contract._summary(official)
    metadata_errors = sum(int(item["error_count"]) for item in metadata)
    scope = {
        "tasks": ordered_tasks,
        "episode_indices_by_task": {task: list(episodes_by_task[task]) for task in ordered_tasks},
        "expected_episode_count": expected,
        "full_16x100": False,
        "contiguous_from_zero": all(
            list(episodes_by_task[task]) == list(range(len(episodes_by_task[task])))
            for task in ordered_tasks
        ),
    }
    passed = (
        metadata_errors == 0
        and generated_summary["error_count"] == 0
        and official_summary["error_count"] == 0
        and generated_summary["completed_count"] == expected
        and official_summary["completed_count"] == expected
    )
    return {
        "passed": passed,
        "scope": scope,
        "metadata": {"error_count": metadata_errors, "audits": metadata},
        "generated": {**generated_summary, "audits": generated},
        "official": {**official_summary, "audits": official},
        "acceptance": {
            "expected_final_completed": expected,
            "generated_final_completed": generated_summary["completed_count"],
            "official_final_completed": official_summary["completed_count"],
        },
    }


# --------------------------------------------------------------------------
# 动作比较（稀疏范围）
# --------------------------------------------------------------------------


def compare_joint_actions_subset(
    generated_root: str | Path,
    reference_root: str | Path,
    episodes_by_task: Mapping[str, Sequence[int]],
    contract,
    comparison,
    max_abs_diff: float = 1e-8,
) -> dict[str, Any]:
    """官方 ``compare_joint_actions`` 的稀疏范围版：只换遍历的键集合。

    字段检查顺序、``(8,) float64`` 要求、有限性检查、``delta != 0`` 计数、
    最大差定位与阈值判定与原函数逐句一致。
    """
    import h5py
    import numpy as np

    output = Path(generated_root).expanduser().resolve()
    reference_root_path = Path(reference_root).expanduser().resolve()
    ordered_tasks = [task for task in contract.ALL_TASKS if task in episodes_by_task]
    if not ordered_tasks:
        raise ComparatorScopeError("比较范围为空")
    if not np.isfinite(max_abs_diff) or max_abs_diff < 0:
        raise comparison.JointActionComparisonError(
            "max_abs_diff must be a non-negative finite value"
        )

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
    add_error = contract.add_error
    for task in ordered_tasks:
        episode_indices = list(episodes_by_task[task])
        if len(episode_indices) != len(set(episode_indices)):
            raise ComparatorScopeError(f"{task}: episode 列表有重复")
        reference_path = reference_root_path / f"record_dataset_{task}.h5"
        generated_path = output / f"record_dataset_{task}.h5"
        if not reference_path.is_file() or not generated_path.is_file():
            add_error(section, f"{task}: comparison file does not exist")
            continue
        try:
            with h5py.File(reference_path, "r") as reference, h5py.File(
                generated_path, "r"
            ) as generated:
                reference_groups = contract.episode_groups(reference, f"reference/{task}", section)
                generated_groups = contract.episode_groups(generated, f"generated/{task}", section)
                for episode in episode_indices:
                    left = reference_groups.get(episode)
                    right = generated_groups.get(episode)
                    if left is None or right is None:
                        add_error(section, f"{task}/episode_{episode}: missing reference or generated")
                        continue
                    left_steps, left_errors = contract.timestep_indices(
                        left, f"reference/{task}/episode_{episode}"
                    )
                    right_steps, right_errors = contract.timestep_indices(
                        right, f"generated/{task}/episode_{episode}"
                    )
                    for error in left_errors + right_errors:
                        add_error(section, error)
                    if left_errors or right_errors or left_steps != right_steps:
                        if not left_errors and not right_errors:
                            add_error(section, f"{task}/episode_{episode}: timestep sets do not match")
                        continue
                    for timestep in left_steps:
                        location = f"{task}/episode_{episode}/timestep_{timestep}"
                        try:
                            reference_joint = left[f"timestep_{timestep}"]["action"]["joint_action"]
                            generated_joint = right[f"timestep_{timestep}"]["action"]["joint_action"]
                        except KeyError:
                            add_error(section, f"{location}: missing action/joint_action")
                            continue
                        if not isinstance(reference_joint, h5py.Dataset) or not isinstance(
                            generated_joint, h5py.Dataset
                        ):
                            add_error(section, f"{location}: joint_action is not a dataset")
                            continue
                        if tuple(reference_joint.shape) != tuple(generated_joint.shape) or np.dtype(
                            reference_joint.dtype
                        ) != np.dtype(generated_joint.dtype):
                            add_error(section, f"{location}: joint_action shape/dtype mismatch")
                            continue
                        if tuple(reference_joint.shape) != (8,) or np.dtype(
                            reference_joint.dtype
                        ) != np.dtype(np.float64):
                            add_error(section, f"{location}: joint_action is not (8,) float64")
                            continue
                        reference_values = np.asarray(reference_joint[()])
                        generated_values = np.asarray(generated_joint[()])
                        if not (
                            np.all(np.isfinite(reference_values))
                            and np.all(np.isfinite(generated_values))
                        ):
                            add_error(section, f"{location}: joint_action contains non-finite values")
                            continue
                        delta = np.abs(
                            reference_values.astype(np.float64)
                            - generated_values.astype(np.float64)
                        )
                        section["joint_vector_count"] += 1
                        section["joint_element_count"] += int(delta.size)
                        section["different_element_count"] += int(np.count_nonzero(delta != 0.0))
                        maximum = float(np.max(delta))
                        if section["max_abs_diff"] is None or maximum > section["max_abs_diff"]:
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
            add_error(section, f"{task}: failed to read comparison HDF5: {exc}")

    if section["joint_element_count"] == 0:
        add_error(section, "no joint_action elements were compared")
    section["within_max_abs_diff"] = bool(
        section["max_abs_diff"] is not None and section["max_abs_diff"] <= float(max_abs_diff)
    )
    section["passed"] = bool(section["error_count"] == 0 and section["within_max_abs_diff"])
    return section


def scope_diff(contract, comparison) -> str:
    """官方原函数与本模块适配版的逐函数最小 diff，供留档（方案 9.6）。"""
    import difflib
    import inspect

    chunks = []
    for official_fn, adapted_fn in (
        (contract.validate_generated_dataset_contract, validate_generated_subset),
        (comparison.compare_joint_actions, compare_joint_actions_subset),
    ):
        diff = difflib.unified_diff(
            inspect.getsource(official_fn).splitlines(),
            inspect.getsource(adapted_fn).splitlines(),
            fromfile=f"official/{official_fn.__name__}",
            tofile=f"adapted/{adapted_fn.__name__}",
            lineterm="",
        )
        chunks.append("\n".join(diff))
    return "\n\n".join(chunks)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="官方比较器的稀疏范围适配")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="跑 G5 离线夹具并输出 COMPARATOR_SCOPE 判定行")
    check.add_argument("--official-root", required=True, help="冻结的官方源码目录")
    check.add_argument("--output", default=None, help="夹具与结果留档目录")
    diff = sub.add_parser("diff", help="打印逐函数最小 diff")
    diff.add_argument("--official-root", required=True)
    args = parser.parse_args(argv)

    contract, comparison = load_official(args.official_root)
    if args.command == "diff":
        print(scope_diff(contract, comparison))
        return 0

    from comparator_fixtures import run_g5_fixtures  # noqa: PLC0415 夹具与本模块同目录

    result = run_g5_fixtures(contract, comparison, Path(args.output) if args.output else None)
    ok = (
        result["contiguous_mismatch"] == 0
        and result["sparse_mismatch"] == 0
        and result["invalid_accepts"] == 0
    )
    print(
        f"COMPARATOR_SCOPE={'PASS' if ok else 'FAIL'} "
        f"contiguous_mismatch={result['contiguous_mismatch']} "
        f"sparse_mismatch={result['sparse_mismatch']} "
        f"invalid_accepts={result['invalid_accepts']}"
    )
    for note in result.get("notes", []):
        print(f"# {note}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
