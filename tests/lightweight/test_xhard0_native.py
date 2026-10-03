#!/usr/bin/env python3
"""轻量测试：xhard0（官方 test 元数据 difficulty=="hard" 的 12 局，0928 方案第二部分 §1.1、§1.5）。

* ``hard_specs`` 的 xhard0 常量：``XHARD0``／``BUILDER_TIERS``／``XHARD0_PER_TASK``／``XHARD0_EPISODES``、
  ``TIER_MAX_STEPS`` 六档（xhard0 1300、xhard1～5 均 1600）；v8 阶段 3b 起 ``TIERS`` 为新值五档、
  ``BUILDER_TIERS`` 六项、``EXPECTED_CELLS`` 为 43 格逐格表（v8 包＝``V8_CELLS``，v9 阶段 3b 换包后＝``V9_CELLS``）；
* 清单 ``scripts/configs/newtask-v7/xhard0_manifest.json``：16 任务 × 12 局 = 192 行，逐条等于官方 test 元数据，
  recovery_mode 只有原 episode 3 为 ``xy``（官方 ≤2 z、≤5 xy、其余 off），摘要与源文件散列自洽；
* ``hard_parity.check_xhard0`` 的判定：合规 PASS、改 seed／缺行／多行／builder 不符 FAIL。

纯 CPU、不起仿真。

    uv run --no-sync python -m pytest tests/lightweight/test_xhard0_native.py -q
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.env_record_wrapper import hard_specs as V  # noqa: E402
from scripts.parity import hard_parity as H  # noqa: E402

MANIFEST = REPO_ROOT / "scripts" / "configs" / "newtask-v7" / "xhard0_manifest.json"
TEST_META = REPO_ROOT / "src" / "robomme" / "env_metadata" / "test"


def _official_hard(task):
    payload = json.loads((TEST_META / f"record_dataset_{task}_metadata.json").read_text(encoding="utf-8"))
    return sorted((r for r in payload["records"] if r.get("difficulty") == "hard"), key=lambda r: int(r["episode"]))


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ── hard_specs 常量 ────────────────────────────────────────────────────────
def test_xhard0常量与档序():
    assert V.XHARD0 == "xhard0"
    assert V.TIERS == ("xhard1", "xhard2", "xhard3", "xhard4", "xhard5") == V.V8_TIERS
    assert V.BUILDER_TIERS == ("xhard0", "xhard1", "xhard2", "xhard3", "xhard4", "xhard5")
    assert V.XHARD0_PER_TASK == 12
    assert V.XHARD0_EPISODES == (3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47)
    assert len(V.XHARD0_EPISODES) == V.XHARD0_PER_TASK
    # xhard0 不属于交付格表（EXPECTED_CELLS 只管新值五档规格）；v8 为 43 格逐格局数、合计 1070，v9 阶段 3b 换包后
    # 为 V9_CELLS（43 格、合计 800）——合计由格表推出，切换前后都成立
    assert all(tier != V.XHARD0 for table in (V.EXPECTED_CELLS, V.V8_CELLS, V.V9_CELLS) for _task, tier in table)
    assert V.EXPECTED_CELLS in (V.V8_CELLS, V.V9_CELLS)
    assert len(V.EXPECTED_CELLS) == 43 and sum(V.EXPECTED_CELLS.values()) in (1070, 800)
    assert V.XHARD4_ONLY == ("InsertPeg", "MoveCube")


def test_TIER_MAX_STEPS六档且xhard0为1300():
    from robomme_hard.env_record_wrapper import BUILDER_TIERS, TIER_MAX_STEPS  # noqa: PLC0415

    assert TIER_MAX_STEPS is V.TIER_MAX_STEPS and BUILDER_TIERS == V.BUILDER_TIERS
    assert TIER_MAX_STEPS == {"xhard0": 1300, "xhard1": 1600, "xhard2": 1600, "xhard3": 1600, "xhard4": 1600,
                              "xhard5": 1600}  # v8：新值五档定死 1600（＝V8_EXEC_CAP）
    assert all(TIER_MAX_STEPS[tier] == V.V8_EXEC_CAP for tier in V.TIERS)
    assert tuple(TIER_MAX_STEPS) == V.BUILDER_TIERS
    steps = [TIER_MAX_STEPS[tier] for tier in V.BUILDER_TIERS]
    assert steps == sorted(steps)


def test_官方test元数据每任务恰好12局hard():
    for task in V.ALL_TASKS:
        hard = _official_hard(task)
        assert tuple(int(r["episode"]) for r in hard) == V.XHARD0_EPISODES, task
        seeds = [int(r["seed"]) for r in hard]
        assert len(set(seeds)) == len(seeds), task


# ── 清单 ────────────────────────────────────────────────────────────────
def test_清单192行逐条等于官方元数据(manifest):
    rows = manifest["rows"]
    assert manifest["kind"] == "xhard0" and manifest["source_dataset"] == "test" and manifest["source_ref"] == "1fadc0ec"
    assert manifest["per_cell"] == 12 and manifest["rows_total"] == len(rows) == 192
    assert manifest["tasks"] == list(V.ALL_TASKS)
    assert [r["task"] for r in rows] == [t for t in V.ALL_TASKS for _ in range(12)]
    for task in V.ALL_TASKS:
        mine = [r for r in rows if r["task"] == task]
        official = _official_hard(task)
        assert [(r["episode"], r["seed"]) for r in mine] == [(int(o["episode"]), int(o["seed"])) for o in official], task
        assert all(r["difficulty"] == "hard" for r in mine)


def test_清单recovery_mode只有episode3为xy(manifest):
    rows = manifest["rows"]
    for r in rows:
        assert r["recovery_mode"] == ("xy" if r["episode"] == 3 else "off"), r
        assert r["recovery_mode"] == H.official_recovery_mode(r["episode"])
    assert manifest["recovery_config_counts"] == {"z": 0, "xy": 16, "off": 176}
    assert [H.official_recovery_mode(e) for e in (0, 2, 3, 5, 6, 47)] == ["z", "z", "xy", "xy", "off", "off"]


def test_清单摘要与源文件散列自洽(manifest):
    rows = manifest["rows"]
    assert manifest["records_sha256"] == hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    assert len(manifest["source_files"]) == 16
    for rel, digest in manifest["source_files"].items():
        assert hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == digest, rel


def test_xhard0_records重导出等于清单(manifest):
    rows, sources = H.xhard0_records(REPO_ROOT)
    assert rows == manifest["rows"]
    assert sources == manifest["source_files"]


# ── check_xhard0 ──────────────────────────────────────────────────────────
def test_check_xhard0合规PASS(manifest):
    rows = copy.deepcopy(manifest["rows"])
    ok, line = H.check_xhard0(rows, manifest, [{"task": r["task"], "episode": r["episode"], "seed": r["seed"]}
                                               for r in rows])
    assert ok, line
    assert line.startswith("XHARD0_IDENTITY=PASS shape=16x1x12 identities=192 missing=0 extra=0")


def test_check_xhard0改seed缺行多行均FAIL(manifest):
    rows = copy.deepcopy(manifest["rows"])
    # 清单里某局 seed 被改：与元数据不符
    bad_manifest = copy.deepcopy(manifest)
    bad_manifest["rows"][5]["seed"] += 1
    ok, line = H.check_xhard0(rows, bad_manifest)
    assert not ok and "missing=1 extra=1" in line
    # 元数据侧少一局：episode 号序列不对、总数不是 192
    ok, line = H.check_xhard0(rows[:-1])
    assert not ok and "XHARD0_IDENTITY=FAIL" in line
    # 任务内 seed 重复
    dup = copy.deepcopy(rows)
    dup[1]["seed"] = dup[0]["seed"]
    ok, line = H.check_xhard0(dup)
    assert not ok and "seed 重复" in line
    # builder 条目多一局
    builder = [{"task": r["task"], "episode": r["episode"], "seed": r["seed"]} for r in rows]
    builder.append({"task": "BinFill", "episode": 51, "seed": 1})
    ok, line = H.check_xhard0(rows, manifest, builder)
    assert not ok and "extra=1" in line


def test_hard_parity的xhard0常量与包内一致():
    assert H.XHARD0_PER_TASK == V.XHARD0_PER_TASK
    assert H.XHARD0_EPISODES == V.XHARD0_EPISODES
    assert "xhard0" in H.TIERS and "v8" in H.TIERS and "H2" in H.SIDES and "H:H2" in H.PAIRS
    assert H.SHAPES["xhard0"] == "16x1x12"
    assert H.XHARD0_MANIFEST == MANIFEST
