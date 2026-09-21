#!/usr/bin/env python3
"""G5 离线夹具：证明范围适配器对连续范围与官方原函数同结果、对稀疏范围精确对应、对非法范围拒绝。

夹具是**离线合成**的小 HDF5，不启动仿真、不占 GPU，也不算官方 train 覆盖
（方案 9.6 末段明确：测试夹具不算 train 覆盖）。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np

import train_split_comparison as adapter

TASK = "BinFill"
SPARSE_EPISODES = (0, 1, 2, 3, 4, 6, 7, 10, 11)
STEPS = 4


def _records(episodes: Sequence[int]) -> dict[int, dict[str, Any]]:
    return {
        episode: {
            "task": TASK,
            "episode": int(episode),
            "seed": 4000 + int(episode) * 100,
            "difficulty": ("easy", "medium", "hard")[int(episode) % 3],
        }
        for episode in episodes
    }


def _joint(episode: int, timestep: int) -> np.ndarray:
    return np.arange(8, dtype=np.float64) + episode * 10 + timestep


def _write_file(
    path: Path,
    records: Mapping[int, Mapping[str, Any]],
    episodes: Sequence[int],
    *,
    steps: Mapping[int, int] | None = None,
    perturb: Mapping[int, tuple[int, int, float]] | None = None,
    joint_dtype: Mapping[int, str] | None = None,
    non_finite: Sequence[int] = (),
    completed: Sequence[int] | None = None,
) -> None:
    steps = steps or {}
    perturb = perturb or {}
    joint_dtype = joint_dtype or {}
    with h5py.File(path, "w") as handle:
        for episode in episodes:
            record = records[episode]
            group = handle.create_group(f"episode_{episode}")
            setup = group.create_group("setup")
            setup.create_dataset("seed", data=np.int64(record["seed"]))
            setup.create_dataset("difficulty", data=record["difficulty"])
            count = steps.get(episode, STEPS)
            for timestep in range(count):
                step_group = group.create_group(f"timestep_{timestep}")
                values = _joint(episode, timestep)
                if episode in perturb:
                    target_step, element, delta = perturb[episode]
                    if timestep == target_step:
                        values = values.copy()
                        values[element] += delta
                if episode in non_finite and timestep == 0:
                    values = values.copy()
                    values[0] = np.inf
                dtype = joint_dtype.get(episode, "float64")
                step_group.create_dataset(
                    "action/joint_action", data=values.astype(dtype)
                )
                is_done = timestep == count - 1
                if completed is not None and episode not in completed:
                    is_done = False
                step_group.create_dataset("info/is_completed", data=np.bool_(is_done))


def _write_metadata(path: Path, records: Mapping[int, Mapping[str, Any]], episodes: Sequence[int]) -> None:
    payload = {
        "env_id": TASK,
        "record_count": len(episodes),
        "records": [dict(records[episode]) for episode in episodes],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_case(
    root: Path,
    records: Mapping[int, Mapping[str, Any]],
    generated_episodes: Sequence[int],
    reference_episodes: Sequence[int],
    **kwargs: Any,
) -> tuple[Path, Path]:
    generated_root = root / "generated"
    reference_root = root / "reference"
    generated_root.mkdir(parents=True, exist_ok=True)
    reference_root.mkdir(parents=True, exist_ok=True)
    _write_file(reference_root / f"record_dataset_{TASK}.h5", records, reference_episodes)
    _write_file(generated_root / f"record_dataset_{TASK}.h5", records, generated_episodes, **kwargs)
    _write_metadata(
        generated_root / f"record_dataset_{TASK}_metadata.json", records, generated_episodes
    )
    return generated_root, reference_root


def _comparable(result: Mapping[str, Any]) -> dict[str, Any]:
    """取两个实现都应当一致的字段；scope 结构本身是声明过的差异，不参与比较。"""
    return {
        "passed": result["passed"],
        "metadata_error_count": result["metadata"]["error_count"],
        "generated": {k: v for k, v in result["generated"].items() if k != "audits"},
        "official": {k: v for k, v in result["official"].items() if k != "audits"},
        "acceptance": result["acceptance"],
        "generated_episodes": [
            audit["episodes"] for audit in result["generated"]["audits"]
        ],
        "generated_errors": [audit["errors"] for audit in result["generated"]["audits"]],
    }


def run_g5_fixtures(contract, comparison, output: Path | None = None) -> dict[str, Any]:
    """三组夹具：连续对齐、稀疏精确对应、非法范围拒绝。"""
    notes: list[str] = []
    contiguous_mismatch = 0
    sparse_mismatch = 0
    invalid_accepts = 0

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(output) if output else Path(temporary)
        root.mkdir(parents=True, exist_ok=True)

        # ---------------- 第一组：连续范围与官方原函数同结果 ----------------
        contiguous = list(range(3))
        records = _records(range(12))
        case_root = root / "contiguous"
        generated_root, reference_root = _build_case(case_root, records, contiguous, list(range(12)))
        official_contract = contract.validate_generated_dataset_contract(
            generated_root,
            [TASK],
            contiguous,
            records_by_task={TASK: records},
            reference_root=reference_root,
        )
        adapted_contract = adapter.validate_generated_subset(
            generated_root, {TASK: contiguous}, {TASK: records}, reference_root, contract
        )
        if _comparable(official_contract) != _comparable(adapted_contract):
            contiguous_mismatch += 1
            notes.append("连续范围：合同校验结果与官方原函数不一致")

        official_compare = comparison.compare_joint_actions(
            generated_root, reference_root, [TASK], contiguous
        )
        adapted_compare = adapter.compare_joint_actions_subset(
            generated_root, reference_root, {TASK: contiguous}, contract, comparison
        )
        if official_compare != adapted_compare:
            contiguous_mismatch += 1
            notes.append("连续范围：动作比较结果与官方原函数不一致")
        notes.append(
            f"连续范围对齐：joint_vector_count={adapted_compare['joint_vector_count']}，"
            f"passed={adapted_compare['passed']}"
        )

        # ---------------- 第二组：稀疏范围精确对应 ----------------
        sparse = list(SPARSE_EPISODES)
        case_root = root / "sparse"
        # 注入已知差异：episode 6 的 timestep 2、元素 5 差 1e-3；episode 10 少一帧。
        generated_root, reference_root = _build_case(
            case_root,
            records,
            sparse,
            list(range(12)),
            perturb={6: (2, 5, 1e-3)},
            steps={10: STEPS - 1},
        )
        # 官方原函数必须在读 HDF5 之前就拒绝稀疏范围。
        try:
            contract.validate_generated_dataset_contract(
                generated_root, [TASK], sparse, records_by_task={TASK: records},
                reference_root=reference_root,
            )
            sparse_mismatch += 1
            notes.append("官方原合同校验竟接受了稀疏范围")
        except contract.DatasetContractError:
            pass
        try:
            comparison.compare_joint_actions(generated_root, reference_root, [TASK], sparse)
            sparse_mismatch += 1
            notes.append("官方原动作比较竟接受了稀疏范围")
        except comparison.JointActionComparisonError:
            pass

        adapted = adapter.compare_joint_actions_subset(
            generated_root, reference_root, {TASK: sparse}, contract, comparison
        )
        expected_vectors = (len(sparse) - 1) * STEPS  # episode 10 因帧数不符整条跳过
        if adapted["joint_vector_count"] != expected_vectors:
            sparse_mismatch += 1
            notes.append(
                f"稀疏范围比较的向量数 {adapted['joint_vector_count']} != 期望 {expected_vectors}"
            )
        if adapted["different_element_count"] != 1:
            sparse_mismatch += 1
            notes.append(f"稀疏范围非零差异元素数 {adapted['different_element_count']} != 1")
        location = adapted["max_abs_diff_location"] or {}
        if not (
            location.get("episode") == 6
            and location.get("timestep") == 2
            and location.get("element_index") == 5
            and abs(float(adapted["max_abs_diff"]) - 1e-3) < 1e-12
        ):
            sparse_mismatch += 1
            notes.append(f"稀疏范围最大差定位不符：{location} max={adapted['max_abs_diff']}")
        if not any("episode_10" in message for message in adapted["errors"]):
            sparse_mismatch += 1
            notes.append("帧数不符的 episode 10 未被记为错误")
        if adapted["passed"] or adapted["within_max_abs_diff"]:
            sparse_mismatch += 1
            notes.append("超过 1e-8 的差异竟判为通过")
        notes.append(
            "稀疏范围：向量数 "
            f"{adapted['joint_vector_count']}、非零元素 {adapted['different_element_count']}、"
            f"最大差 {adapted['max_abs_diff']}、错误 {adapted['error_count']} 条"
        )

        # 干净的稀疏对照：同一集合、无注入差异时必须通过，且不把未选中的 episode 拉进来。
        clean_root = root / "sparse-clean"
        generated_root, reference_root = _build_case(clean_root, records, sparse, list(range(12)))
        clean_contract = adapter.validate_generated_subset(
            generated_root, {TASK: sparse}, {TASK: records}, reference_root, contract
        )
        clean_compare = adapter.compare_joint_actions_subset(
            generated_root, reference_root, {TASK: sparse}, contract, comparison
        )
        if not clean_contract["passed"] or not clean_compare["passed"]:
            sparse_mismatch += 1
            notes.append("干净稀疏夹具未通过")
        if clean_compare["joint_vector_count"] != len(sparse) * STEPS:
            sparse_mismatch += 1
            notes.append("干净稀疏夹具比较了未选中的条目")

        # ---------------- 第三组：非法范围必须拒绝 ----------------
        def _expect_reject(label: str, thunk) -> None:
            nonlocal invalid_accepts
            try:
                thunk()
            except (adapter.ComparatorScopeError, contract.DatasetContractError):
                return
            invalid_accepts += 1
            notes.append(f"非法范围被接受：{label}")

        rows = [dict(records[episode]) for episode in sparse]
        _expect_reject(
            "重复 episode",
            lambda: adapter.validate_manifest_scope(
                rows + [dict(records[0])], {TASK: records}, contract.ALL_TASKS
            ),
        )
        _expect_reject(
            "官方 metadata 里没有的 episode",
            lambda: adapter.validate_manifest_scope(
                rows + [{"task": TASK, "episode": 999, "seed": 1, "difficulty": "easy"}],
                {TASK: records},
                contract.ALL_TASKS,
            ),
        )
        bad_identity = [dict(row) for row in rows]
        bad_identity[0]["seed"] = bad_identity[0]["seed"] + 1
        _expect_reject(
            "seed 与官方不符",
            lambda: adapter.validate_manifest_scope(bad_identity, {TASK: records}, contract.ALL_TASKS),
        )
        _expect_reject(
            "未知任务名",
            lambda: adapter.validate_manifest_scope(
                [{"task": "NotATask", "episode": 0, "seed": 1, "difficulty": "easy"}],
                {TASK: records},
                contract.ALL_TASKS,
            ),
        )
        _expect_reject(
            "范围内 episode 列表有重复",
            lambda: adapter.validate_generated_subset(
                generated_root, {TASK: sparse + [6]}, {TASK: records}, reference_root, contract
            ),
        )

        # 生成文件多一条／少一条：不抛异常，但必须记成合同错误且 passed=False。
        extra_root = root / "extra-episode"
        generated_root, reference_root = _build_case(
            extra_root, records, sparse + [5], list(range(12))
        )
        result = adapter.validate_generated_subset(
            generated_root, {TASK: sparse}, {TASK: records}, reference_root, contract
        )
        if result["passed"] or result["generated"]["error_count"] == 0:
            invalid_accepts += 1
            notes.append("生成文件多出未选中的 episode 未被判错")

        missing_root = root / "missing-episode"
        generated_root, reference_root = _build_case(
            missing_root, records, [item for item in sparse if item != 7], list(range(12))
        )
        result = adapter.validate_generated_subset(
            generated_root, {TASK: sparse}, {TASK: records}, reference_root, contract
        )
        if result["passed"] or result["generated"]["error_count"] == 0:
            invalid_accepts += 1
            notes.append("生成文件缺少选中的 episode 未被判错")

        # dtype／非有限值：保留原失败结果（是正确结果，不算 invalid accept）。
        dtype_root = root / "dtype"
        generated_root, reference_root = _build_case(
            dtype_root, records, sparse, list(range(12)), joint_dtype={4: "float32"}
        )
        dtype_result = adapter.compare_joint_actions_subset(
            generated_root, reference_root, {TASK: sparse}, contract, comparison
        )
        if dtype_result["passed"] or not any(
            "shape/dtype mismatch" in message for message in dtype_result["errors"]
        ):
            sparse_mismatch += 1
            notes.append("dtype 变化未被原字段检查抓到")

        nonfinite_root = root / "nonfinite"
        generated_root, reference_root = _build_case(
            nonfinite_root, records, sparse, list(range(12)), non_finite=(1,)
        )
        nonfinite_result = adapter.compare_joint_actions_subset(
            generated_root, reference_root, {TASK: sparse}, contract, comparison
        )
        if nonfinite_result["passed"] or not any(
            "non-finite" in message for message in nonfinite_result["errors"]
        ):
            sparse_mismatch += 1
            notes.append("非有限值未被原字段检查抓到")

        summary = {
            "contiguous_mismatch": contiguous_mismatch,
            "sparse_mismatch": sparse_mismatch,
            "invalid_accepts": invalid_accepts,
            "notes": notes,
        }
        if output:
            (root / "g5_result.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return summary
