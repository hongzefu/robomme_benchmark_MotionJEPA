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


TEST_HARD_ROOT = REPO_ROOT / "src" / "robomme_hard" / "env_metadata" / "test-hard"
V6_FROZEN = REPO_ROOT / "scripts" / "configs" / "newtask-v6" / "v6-sampling-frozen.json"
NEWVALUE_TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")


def _packaged_header(tier: str) -> dict:
    with (TEST_HARD_ROOT / tier / "specs.jsonl").open(encoding="utf-8") as stream:
        return json.loads(stream.readline())


def test_v6_snapshot_matches_source() -> None:
    """V7 起 v6 值只存在于包内 v6 规格 header 与冻结快照 v6-sampling-frozen.json：
    冻结快照按档逐任务等于包内 xhard1..4 header 的 sampling_config（四个 header 互不相同，故按档存）。"""
    from robomme_hard.env_record_wrapper import hard_specs  # noqa: PLC0415

    frozen = json.loads(V6_FROZEN.read_text(encoding="utf-8"))
    assert frozen["schema"] == "v6-sampling-frozen/1"
    assert frozen["four_headers_identical"] is False
    assert set(frozen["sampling_config"]) == set(NEWVALUE_TIERS)
    headers = {tier: _packaged_header(tier) for tier in NEWVALUE_TIERS}
    for tier in NEWVALUE_TIERS:
        header = headers[tier]
        assert header["difficulty"] == tier
        assert frozen["sampling_config"][tier] == header["sampling_config"], tier
        assert frozen["sampling_config_sha256_by_tier"][tier] == header["sampling_config_sha256"], tier
        assert hard_specs.digest(frozen["sampling_config"][tier]) == header["sampling_config_sha256"], tier
        # 任务集合按 header 自身的 tasks（包内 v6 的 xhard1 header 含 16 任务、xhard2／3 含 13 任务）
        assert set(frozen["sampling_config"][tier]) == set(header["tasks"]), tier
    assert set(frozen["sampling_config"]["xhard4"]) == set(READY_TASKS)
    # 四个 header 确实不全相同（快照里 four_headers_identical=false 与事实一致）
    digests = {headers[tier]["sampling_config_sha256"] for tier in NEWVALUE_TIERS}
    assert len(digests) > 1


def test_v7_snapshot_matches_source(tmp_path) -> None:
    """``train_split_config.py extract --release newtask-v7`` 导出的快照：逐任务等于进程内 ``native_blocks``，
    且 13 个梯度任务读出的四档定值等于 V7 定值表（0928 方案 §3.2.2）；与冻结的 v6 快照在梯度任务上不同。"""
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
    frozen = json.loads(V6_FROZEN.read_text(encoding="utf-8"))["sampling_config"]["xhard4"]
    for task in ("PickXtimes", "SwingXtimes", "VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap",
                 "ButtonUnmaskSwap", "VideoRepick", "PatternLock", "RouteStick"):
        assert fresh["tasks"][task] != frozen[task], f"{task}：v7 定值应与 v6 xhard4 header 不同"
