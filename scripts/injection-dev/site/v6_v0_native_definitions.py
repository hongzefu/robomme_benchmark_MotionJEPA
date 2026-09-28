#!/usr/bin/env python3
"""只读比较 V5 与 V6 快照中冻结的原三档定义。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
# 两份快照已随拆包阶段 2 删除，只能从 git 历史取回（如 git show 7a6cee35:scripts/configs/newtask-v5/sampling_config.json），
# 调用时须显式传路径。
DEFAULT_V5 = None
DEFAULT_V6 = None

V5_TIER_KEYS = frozenset({"xhard"})
V6_TIER_KEYS = frozenset({"xhard1", "xhard2", "xhard3", "xhard4"})
EXPECTED_V6_NATIVE_CONFIGS_TASKS = frozenset(
    {"ButtonUnmaskSwap", "VideoRepick", "VideoUnmaskSwap"}
)
EXPECTED_V6_NATIVE_CONFIG_KEYS = frozenset({"easy", "medium", "hard"}) | V6_TIER_KEYS
EXPECTED_TASK_COUNT = 16
# V6 语义审查修复（0926-v6-audit-fix-plan.md §8.2 第 4 项与 N15，2026-09-27 实施）后**有意**偏离 V5 快照的原值键：
# ButtonUnmaskSwap 按钮命名对齐机器人坐标系（用户 K4「所有的左右都是机器人坐标系」；建构顺序、位置、随机数消费不变）
# 与 StopCube 的 motion_segments 说明字段（用户「n15 a」，描述值、代码不读）。除此 6 键外原三档定义仍须逐字相同。
DECLARED_V6_NATIVE_DELTAS = frozenset({
    "/tasks/ButtonUnmaskSwap/native/parameters/button_order/0",
    "/tasks/ButtonUnmaskSwap/native/parameters/button_order/1",
    "/tasks/ButtonUnmaskSwap/native/parameters/pick_rule",
    "/tasks/ButtonUnmaskSwap/native/positions/buttons/0/name",
    "/tasks/ButtonUnmaskSwap/native/positions/buttons/1/name",
    "/tasks/StopCube/native/parameters/motion_segments_note",
})


def _strip_tier_keys(value: Any, keys: frozenset[str]) -> Any:
    """递归剥离指定快照版本的新值档位键，保留其余结构和值。"""
    if isinstance(value, dict):
        return {
            key: _strip_tier_keys(child, keys)
            for key, child in value.items()
            if key not in keys
        }
    if isinstance(value, list):
        return [_strip_tier_keys(child, keys) for child in value]
    return value


def _at_native_configs(block: Any) -> bool:
    """判断环境快照是否包含 `native.parameters.configs` 字段。"""
    if not isinstance(block, dict):
        return False
    native = block.get("native")
    if not isinstance(native, dict):
        return False
    parameters = native.get("parameters")
    return isinstance(parameters, dict) and "configs" in parameters


def _native_configs(block: Any) -> Any:
    """返回 `native.parameters.configs` 的原值，不存在时返回 `None`。"""
    if not isinstance(block, dict):
        return None
    native = block.get("native")
    if not isinstance(native, dict):
        return None
    parameters = native.get("parameters")
    if not isinstance(parameters, dict):
        return None
    return parameters.get("configs")


def _diff_paths(left: Any, right: Any, path: str) -> set[str]:
    """返回两个 JSON 值所有不一致的 JSON Pointer 路径。"""
    if type(left) is not type(right):
        return {path}
    if isinstance(left, dict):
        differences: set[str] = set()
        for key in sorted(left.keys() | right.keys()):
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            child_path = f"{path}/{escaped}"
            if key not in left or key not in right:
                differences.add(child_path)
            else:
                differences.update(_diff_paths(left[key], right[key], child_path))
        return differences
    if isinstance(left, list):
        differences = set()
        if len(left) != len(right):
            differences.add(f"{path}/length")
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            differences.update(_diff_paths(left_item, right_item, f"{path}/{index}"))
        return differences
    return set() if left == right else {path}


def _snapshot_tasks(document: Any, label: str, differences: set[str]) -> dict[str, Any]:
    """校验快照的任务索引完整，并返回任务表。"""
    if not isinstance(document, dict) or not isinstance(document.get("tasks"), dict):
        differences.add(f"/{label}/tasks")
        return {}

    tasks = document["tasks"]
    task_names = set(tasks)
    ready = document.get("tasks_ready")
    pending = document.get("tasks_pending")
    ready_is_valid = (
        isinstance(ready, list)
        and all(isinstance(task, str) for task in ready)
        and len(ready) == len(set(ready))
        and set(ready) == task_names
    )
    if not ready_is_valid:
        differences.add(f"/{label}/tasks_ready")
    if pending != []:
        differences.add(f"/{label}/tasks_pending")
    if len(task_names) != EXPECTED_TASK_COUNT:
        differences.add(f"/{label}/tasks (expected {EXPECTED_TASK_COUNT} tasks, found {len(task_names)})")
    return tasks


def compare_snapshots(v5: Any, v6: Any) -> list[str]:
    """返回所有冻结原值差异路径；空列表表示 V0 通过。"""
    differences: set[str] = set()
    v5_tasks = _snapshot_tasks(v5, "v5", differences)
    v6_tasks = _snapshot_tasks(v6, "v6", differences)

    if set(v5_tasks) != set(v6_tasks):
        for task in sorted(set(v5_tasks) ^ set(v6_tasks)):
            differences.add(f"/tasks/{task}")

    v6_configs_tasks = {
        task for task, block in v6_tasks.items() if _at_native_configs(block)
    }
    for task in sorted(v6_configs_tasks ^ EXPECTED_V6_NATIVE_CONFIGS_TASKS):
        differences.add(f"/tasks/{task}/native/parameters/configs (unexpected exception scope)")

    valid_configs_exception_tasks: set[str] = set()
    for task in sorted(v6_configs_tasks & EXPECTED_V6_NATIVE_CONFIGS_TASKS):
        configs = _native_configs(v6_tasks[task])
        configs_path = f"/tasks/{task}/native/parameters/configs"
        if not isinstance(configs, dict):
            differences.add(f"{configs_path} (expected an object)")
            continue
        actual_keys = set(configs)
        for key in sorted(EXPECTED_V6_NATIVE_CONFIG_KEYS - actual_keys):
            differences.add(f"{configs_path}/{key} (missing expected tier key)")
        for key in sorted(actual_keys - EXPECTED_V6_NATIVE_CONFIG_KEYS):
            differences.add(f"{configs_path}/{key} (unexpected tier key)")
        if actual_keys == EXPECTED_V6_NATIVE_CONFIG_KEYS:
            valid_configs_exception_tasks.add(task)

    for task in sorted(set(v5_tasks) & set(v6_tasks)):
        v5_block = v5_tasks[task]
        v6_block = v6_tasks[task]
        if not isinstance(v5_block, dict) or not isinstance(v6_block, dict):
            differences.add(f"/tasks/{task}")
            continue

        block_is_valid = True
        for label, block in (("v5", v5_block), ("v6", v6_block)):
            for section in ("decision", "native"):
                if not isinstance(block.get(section), dict):
                    differences.add(f"/{label}/tasks/{task}/{section}")
                    block_is_valid = False
        if not block_is_valid:
            continue

        v5_decision = _strip_tier_keys(v5_block.get("decision"), V5_TIER_KEYS)
        v6_decision = _strip_tier_keys(v6_block.get("decision"), V6_TIER_KEYS)
        differences.update(
            _diff_paths(v5_decision, v6_decision, f"/tasks/{task}/decision")
        )

        v5_native = _strip_tier_keys(v5_block.get("native"), V5_TIER_KEYS)
        v6_native = _strip_tier_keys(v6_block.get("native"), V6_TIER_KEYS)
        if task in valid_configs_exception_tasks and isinstance(v6_native, dict):
            parameters = v6_native.get("parameters")
            if isinstance(parameters, dict):
                parameters.pop("configs", None)
        differences.update(_diff_paths(v5_native, v6_native, f"/tasks/{task}/native"))

    return sorted(differences - DECLARED_V6_NATIVE_DELTAS)


def main(argv: list[str] | None = None) -> int:
    """打印可复核的 V0 判定行与差异路径。"""
    parser = argparse.ArgumentParser(description="只读核对 V5/V6 原三档冻结值")
    parser.add_argument("--v5", type=Path, required=True, help="V5 sampling_config 快照（已删，须从 git 历史取回）")
    parser.add_argument("--v6", type=Path, required=True, help="V6 sampling_config 快照（已删，须从 git 历史取回）")
    args = parser.parse_args(argv)

    try:
        v5 = json.loads(args.v5.read_text(encoding="utf-8"))
        v6 = json.loads(args.v6.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"NATIVE_DEFS_UNCHANGED=FAIL envs=0 changed_keys=1")
        print(f"/snapshot: {exc}")
        return 2

    differences = compare_snapshots(v5, v6)
    if differences:
        count = len(differences)
        v5_count = len(v5.get("tasks", {})) if isinstance(v5, dict) and isinstance(v5.get("tasks"), dict) else 0
        v6_count = len(v6.get("tasks", {})) if isinstance(v6, dict) and isinstance(v6.get("tasks"), dict) else 0
        print(f"NATIVE_DEFS_UNCHANGED=FAIL envs={min(v5_count, v6_count)} changed_keys={count}")
        for path in differences:
            print(path)
        return 1

    print(f"NATIVE_DEFS_UNCHANGED=PASS envs={EXPECTED_TASK_COUNT} changed_keys=0 "
          f"declared_deltas={len(DECLARED_V6_NATIVE_DELTAS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
