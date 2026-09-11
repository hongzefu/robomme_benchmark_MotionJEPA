"""xhard 扩展的脚本侧前置：取值域散列按难度作用域、组列表常量、发起者循环校验。

2026-09-11 给三个任务加 ``config_xhard`` 之前必须先钉死：
* ``operand_sha256`` 只算本次消费到的难度档，源码加档不改变 05 与 v1/v2 契约的依据身份；
* ``GROUPS`` 保持 11 组，``GROUPS_V3`` = 11 + 3，两个模块的副本一致；
* ``_static_problems`` 的「第 k 段发起者 = swap_initiators[k mod 3]」对旧 05 规格恒成立。

    uv run --no-sync python -m pytest tests/lightweight/test_operand_scope.py -q
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.injection import campaign, contract_build, specs  # noqa: E402

pytestmark = pytest.mark.lightweight

SAMPLING_PATH = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
SAMPLING = json.loads(SAMPLING_PATH.read_text(encoding="utf-8"))
#: 05 清单 ``sampling_operands_sha256``、v1/v2 契约 ``derives_from_operands_sha256`` 的冻结值
FROZEN_THREE_TIER_SHA = "124e49f80daf6c359254b9a20e69ba61ae3741b213418bd81b8cd17609e29988"
RUN_05 = REPO_ROOT / "artifacts" / "injection" / "20260911-contract-v2-05"


def _with_fake_xhard() -> dict:
    payload = copy.deepcopy(SAMPLING)
    payload["parameters"]["RouteStick"]["configs"]["xhard"] = {"length": [8, 10], "backtrack": True}
    payload["parameters"]["VideoUnmaskSwap"]["configs"]["xhard"] = {"bin": 4, "swap_min": 4, "swap_max": 5, "pick_min": 2, "pick_max": 2}
    payload["parameters"]["VideoRepick"]["configs"]["xhard"] = {"cube": 3, "swap_min": 4, "swap_max": 5}
    return payload


def test_三档作用域散列等于05冻结值():
    three = {"easy", "medium", "hard"}
    assert specs.operand_sha256(SAMPLING, three) == FROZEN_THREE_TIER_SHA
    # 快照里只有三档时，作用域散列与全量散列相同
    if all("xhard" not in SAMPLING["parameters"][t]["configs"] for t in ("RouteStick", "VideoUnmaskSwap", "VideoRepick")):
        assert specs.operand_sha256(SAMPLING) == FROZEN_THREE_TIER_SHA


def test_加xhard后三档作用域散列不变而全量散列改变():
    payload = _with_fake_xhard()
    assert specs.operand_sha256(payload, {"easy", "medium", "hard"}) == FROZEN_THREE_TIER_SHA
    assert specs.operand_sha256(payload) != FROZEN_THREE_TIER_SHA
    assert specs.operand_sha256(payload, {"easy", "medium", "hard", "xhard"}) == specs.operand_sha256(payload)
    # 作用域过滤不改入参
    assert "xhard" in payload["parameters"]["RouteStick"]["configs"]


def test_difficulties_of_与组列表常量():
    assert specs.difficulties_of(specs.GROUPS) == {"easy", "medium", "hard"}
    assert specs.difficulties_of(specs.GROUPS_V3) == {"easy", "medium", "hard", "xhard"}
    assert len(specs.GROUPS) == 11 and len(specs.GROUPS_V3) == 14
    assert specs.GROUPS_V3[:11] == specs.GROUPS
    assert specs.XHARD_GROUPS == (("RouteStick", "xhard"), ("VideoUnmaskSwap", "xhard"), ("VideoRepick", "xhard"))
    # 两个模块各留一份常量，必须逐项相同
    assert tuple(contract_build.GROUPS) == specs.GROUPS
    assert tuple(contract_build.GROUPS_V3) == specs.GROUPS_V3
    assert tuple(contract_build.XHARD_GROUPS) == specs.XHARD_GROUPS


@pytest.mark.skipif(not RUN_05.is_dir(), reason="05 运行的冻结规格不在工作区")
@pytest.mark.parametrize(("task", "difficulty"), [g for g in specs.GROUPS if g[0] in ("VideoUnmaskSwap", "VideoRepick")])
def test_发起者循环校验对05旧规格恒成立(task, difficulty):
    doc = json.loads((RUN_05 / "specs" / task / f"{difficulty}.json").read_text(encoding="utf-8"))
    parameters = SAMPLING["parameters"][task]
    positions = SAMPLING["positions"][task]
    config = parameters["configs"][difficulty]
    for record in doc["episodes"]:
        problems = campaign._static_problems(task, difficulty, f"{task}/{difficulty}/ep{record['episode']}", record, config, parameters, positions)
        assert problems == [], problems


def test_发起者不按循环基取用时被静态检查抓住():
    task, difficulty = "VideoRepick", "medium"
    doc_path = RUN_05 / "specs" / task / f"{difficulty}.json"
    if not doc_path.is_file():
        pytest.skip("05 运行的冻结规格不在工作区")
    record = copy.deepcopy(json.loads(doc_path.read_text(encoding="utf-8"))["episodes"][0])
    parameters = SAMPLING["parameters"][task]
    record["objects"]["swap_initiators"] = list(reversed(record["objects"]["swap_initiators"]))
    problems = campaign._static_problems(task, difficulty, "tag", record, parameters["configs"][difficulty], parameters, SAMPLING["positions"][task])
    assert any("swap_initiators[" in p for p in problems)
