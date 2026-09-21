#!/usr/bin/env python3
"""轻量测试：sampling_config 的 decision／native 拆分（方案步 3，闸门 G2／G3 的离线部分）。

要点：
1. 不传配置、显式传原值（新格式）、传旧格式 {parameters, positions} 三者解析结果完全相同——
   这是 B↔C 能逐位相同的前提。
2. 原值模式下 decision 被改一个键就必须拒绝（红线 R7）。
3. 导出的快照文件与源码提取结果一致，且每个已接口化环境的 decision 键都有落点。

    uv run --no-sync python -m pytest tests/lightweight/test_sampling_config_split.py -q
"""

from __future__ import annotations

import copy
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
for extra in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

SNAPSHOT = REPO_ROOT / "scripts" / "configs" / "newtask-v3" / "native_sampling.json"


def _ready_tasks() -> tuple[str, ...]:
    """已接口化的环境取自快照，随步 3 逐环境推进自动扩展。"""
    if not SNAPSHOT.exists():
        return ()
    return tuple(json.loads(SNAPSHOT.read_text(encoding="utf-8"))["tasks_ready"])


READY_TASKS = _ready_tasks()


def _module(task: str):
    return importlib.import_module(f"robomme.robomme_env.{task}")


@pytest.mark.parametrize("task", READY_TASKS)
def test_three_ways_of_passing_native_config_are_identical(task: str) -> None:
    module = _module(task)
    cls = getattr(module, task)
    decision, native = module.native_blocks(cls)
    resolved_none = module._resolve_sampling_config(cls, None)
    resolved_new = module._resolve_sampling_config(cls, {"decision": decision, "native": native})
    resolved_old = module._resolve_sampling_config(cls, native)  # 旧格式仍受支持
    dump = lambda payload: json.dumps(payload, sort_keys=True, ensure_ascii=False)  # noqa: E731
    assert dump(resolved_none) == dump(resolved_new) == dump(resolved_old)


@pytest.mark.parametrize("task", READY_TASKS)
def test_changed_decision_is_rejected_in_native_mode(task: str) -> None:
    from robomme.robomme_env.utils.sampling_config import SamplingConfigError

    module = _module(task)
    cls = getattr(module, task)
    decision, native = module.native_blocks(cls)
    tampered = copy.deepcopy(decision)
    key = sorted(tampered)[0]
    value = tampered[key]
    tampered[key] = "TAMPERED" if not isinstance(value, dict) else {**value, "__extra__": 1}
    with pytest.raises(SamplingConfigError):
        module._resolve_sampling_config(cls, {"decision": tampered, "native": native})


def test_snapshot_matches_source() -> None:
    if not SNAPSHOT.exists():
        pytest.skip("快照缺失；先运行 train_split_config.py extract")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "train_split_config.py"), "extract", "--verify"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert document["tasks_ready"] == sorted(READY_TASKS)
    assert len(document["tasks_ready"]) + len(document["tasks_pending"]) == 16
    for task in READY_TASKS:
        block = document["tasks"][task]
        assert set(block) == {"decision", "native"}
        assert set(block["native"]) >= {"parameters", "positions"}
        assert block["decision"], f"{task} 的 decision 块不能为空"
