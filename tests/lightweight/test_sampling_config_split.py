# robomme_hard：本测试测新值档／改动行为，阶段 3 起 src/robomme 回到官方 1fadc0ec，故改测 robomme_hard（0927 计划 R8 第③类）
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
for extra in (REPO_ROOT / "src", REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "parity"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

PACKAGED_XHARD4 = REPO_ROOT / "src" / "robomme_hard" / "env_metadata" / "test-hard" / "xhard4" / "specs.jsonl"


def _ready_tasks() -> tuple[str, ...]:
    """已接口化的环境取自包内 xhard4 header 的 sampling_config（16 任务；原 V6 快照已随拆包阶段 2 删除）。"""
    header = json.loads(PACKAGED_XHARD4.open(encoding="utf-8").readline())
    return tuple(sorted(header["sampling_config"]))


READY_TASKS = _ready_tasks()


def _module(task: str):
    return importlib.import_module(f"robomme_hard.robomme_env.{task}")


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
    from robomme_hard.robomme_env.utils.sampling_config import SamplingConfigError

    module = _module(task)
    cls = getattr(module, task)
    decision, native = module.native_blocks(cls)
    tampered = copy.deepcopy(decision)
    key = sorted(tampered)[0]
    value = tampered[key]
    tampered[key] = "TAMPERED" if not isinstance(value, dict) else {**value, "__extra__": 1}
    with pytest.raises(SamplingConfigError):
        module._resolve_sampling_config(cls, {"decision": tampered, "native": native})


def test_v7_snapshot_matches_source(tmp_path) -> None:
    """``train_split_config.py extract --release newtask-v7`` 导出的快照：逐任务等于进程内 ``native_blocks``，
    且梯度任务读出的定值等于 tests/_shared/v7_tier_values.py 的定值表（v8 阶段 1 起为 v8 取值）。
    原尾部「与冻结 v6 快照不同」的比较随 V6 删除移除（v8 方案第一部分 §2.4）。"""
    from tests._shared.v7_tier_values import V7_TIER_VALUES, summarize  # noqa: PLC0415

    out = tmp_path / "sampling_config.json"
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "parity" / "train_split_config.py"), "extract",
         "--release", "newtask-v7", "--pkg", "robomme_hard", "--output", str(out)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    fresh = json.loads(out.read_text(encoding="utf-8"))
    assert len(fresh["tasks_ready"]) == 16 and fresh["tasks_pending"] == []
    assert fresh["tasks_ready"] == sorted(READY_TASKS)
    for task in READY_TASKS:
        block = fresh["tasks"][task]
        assert set(block) == {"decision", "native"}
        assert set(block["native"]) >= {"parameters", "positions"}
        assert block["decision"], f"{task} 的 decision 块不能为空"
        module = _module(task)
        decision, native = module.native_blocks(getattr(module, task))
        dump = lambda payload: json.dumps(payload, sort_keys=True, ensure_ascii=False)  # noqa: E731
        assert dump(block) == dump({"decision": decision, "native": native}), task
    got = {task: summarize(task, fresh["tasks"][task]["decision"]) for task in V7_TIER_VALUES}
    assert got == V7_TIER_VALUES
