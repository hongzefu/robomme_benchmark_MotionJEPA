#!/usr/bin/env python3
"""轻量测试：官方比较器的稀疏范围适配（闸门 G5，不加载仿真、不占 GPU）。

对应 NEWTASK_RELEASE_V3_PLAN.md 第二部分 9.6：连续范围与官方原函数同结果、
稀疏范围精确对应、重复／缺失／额外／身份不符必须拒绝，dtype 变化与非有限值
保留原失败结果。夹具是离线合成的小 HDF5，不算官方 train 覆盖。

    uv run --no-sync python -m pytest tests/lightweight/test_comparator_scope.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import train_split_comparison as adapter  # noqa: E402
import train_split_parity as parity  # noqa: E402


@pytest.fixture(scope="session")
def official_modules(tmp_path_factory):
    """把官方固定提交导出到临时目录并导入两个原比较器（整棵树约 7.5 MB）。"""
    root = tmp_path_factory.mktemp("official") / "src-tree"
    parity.materialize_official_source(parity.DEFAULT_SOURCE_REF, root)
    return adapter.load_official(root)


def test_official_functions_reject_sparse_range(official_modules) -> None:
    """守卫仍在原处：官方原函数照旧拒绝稀疏 episode，这正是要适配的原因。"""
    contract, comparison = official_modules
    sparse = [0, 1, 2, 3, 4, 6, 7, 10, 11]
    with pytest.raises(contract.DatasetContractError):
        contract.validate_generated_dataset_contract(
            REPO_ROOT, ["BinFill"], sparse, records_by_task={"BinFill": {}}
        )
    with pytest.raises(comparison.JointActionComparisonError):
        comparison.compare_joint_actions(REPO_ROOT, REPO_ROOT, ["BinFill"], sparse)


def test_g5_fixtures_pass(official_modules, tmp_path) -> None:
    """G5 三组夹具全过，等价于 COMPARATOR_SCOPE=PASS。"""
    from comparator_fixtures import run_g5_fixtures

    contract, comparison = official_modules
    result = run_g5_fixtures(contract, comparison, tmp_path / "g5")
    assert result["contiguous_mismatch"] == 0, result["notes"]
    assert result["sparse_mismatch"] == 0, result["notes"]
    assert result["invalid_accepts"] == 0, result["notes"]


def test_manifest_scope_accepts_real_subset(official_modules) -> None:
    """用冻结的 144 条子集与官方 metadata 实跑一次范围校验。"""
    import json

    contract, _ = official_modules
    subset_path = REPO_ROOT / "scripts" / "configs" / "newtask-v3" / "subset_manifest.json"
    if not subset_path.exists():
        pytest.skip("子集 manifest 缺失；先运行 freeze-identities")
    rows = json.loads(subset_path.read_text(encoding="utf-8"))["rows"]
    records = contract.read_train_metadata(
        REPO_ROOT / "scripts" / "configs" / "newtask-v3" / "official_train"
    )
    grouped = adapter.validate_manifest_scope(rows, records, contract.ALL_TASKS)
    assert len(grouped) == 16
    assert all(episodes == [0, 1, 2, 3, 4, 6, 7, 10, 11] for episodes in grouped.values())


def test_scope_diff_is_limited_to_range_handling(official_modules) -> None:
    """逐函数最小 diff 必须留得下来，且确实改掉了连续范围守卫。"""
    contract, comparison = official_modules
    diff = adapter.scope_diff(contract, comparison)
    assert "must be a contiguous range starting at 0" in diff
    assert "episodes_by_task" in diff
