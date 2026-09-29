#!/usr/bin/env python3
"""轻量测试：v7 gen1 的候选池（``scripts/injection-dev/_rollout.py``，0928 方案第二部分 §2）。

* ``initial_pool``：``derive_ok``＝本任务各档规格都有的候选；初选＝xhard4 的 initial_selected ∩ derive_ok，
  不足按候选号升序补齐；只有 xhard4 的任务只有一档；
* ``sync_drop_and_backfill``：某档失败 → 该候选四档一起退选，按候选号递补下一个从未试过的 spare；
  递补上限 ``V7_BACKFILL_CAP``；
* ``delivery_rows``：每格恰好 per_cell 局且各档交付集合相同 → ``V7_DELIVERY_SET=PASS``，否则 FAIL；
* ``run_continue_v7`` 端到端（注入假 batch_runner，不起仿真）：同步作废、递补、回写四档规格结果段、delivery.json。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_candidate_pool.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared import v7_specs_fixture as F  # noqa: E402

import _rollout  # noqa: E402  （路径由夹具模块加入）
from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

TIERS = hard_specs.TIERS


def _row(task, tier, candidate, initial=False):
    return {"task": task, "tier": tier, "candidate": candidate, "episode": candidate,
            "seed": 14_000_000 + candidate, "spec_sha256": f"{task}-{tier}-{candidate}", "initial_selected": initial}


def _loaded(candidates=6, per_cell=3, missing=None):
    """合成 ``{tier: (header, rows)}``：BinFill 四档、StopCube 只有 xhard4；``missing`` 为派生失败的 (tier, task, cand)。"""
    missing = missing or set()
    loaded = {}
    for tier in TIERS:
        tasks = ["BinFill", "StopCube"] if tier == "xhard4" else ["BinFill"]
        rows = [_row(t, tier, c, initial=c < per_cell) for t in tasks for c in range(candidates)
                if (tier, t, c) not in missing]
        loaded[tier] = ({"tasks": tasks, "delivery_per_cell": per_cell}, rows)
    return loaded


def _selected(pool, task):
    return sorted(int(c) for c, s in pool["tasks"][task]["state"].items() if s["status"] == "selected")


def _mark_ok(pool, task, candidate, tiers, output):
    for tier in tiers:
        pool["tasks"][task]["state"][str(candidate)]["tiers"][tier] = {
            "status": "ok", "h5_sha256": f"sha-{task}-{tier}-{candidate}", "frames": 10,
            "h5_path": str(output / "episodes" / tier / f"{task}_{candidate}.h5"), "env_module": f"robomme_hard.x.{task}"}


# ── initial_pool ─────────────────────────────────────────────────────────────
def test_初选取xhard4初选与派生齐全的交集并按号补齐():
    loaded = _loaded(missing={("xhard2", "BinFill", 1)})
    pool = _rollout.initial_pool(loaded, 3)
    assert pool["schema"] == "v7-candidate-pool/1" and pool["per_cell"] == 3
    binfill = pool["tasks"]["BinFill"]
    assert binfill["tiers"] == list(TIERS)
    assert binfill["derive_ok"] == [0, 2, 3, 4, 5]  # 候选 1 在 xhard2 派生失败
    assert _selected(pool, "BinFill") == [0, 2, 3]
    assert {c: s["status"] for c, s in binfill["state"].items()} == \
        {"0": "selected", "2": "selected", "3": "selected", "4": "spare", "5": "spare"}
    assert binfill["backfills"] == 0 and binfill["sync_dropped"] == []


def test_只有xhard4的任务只有一档():
    pool = _rollout.initial_pool(_loaded(), 3)
    stop = pool["tasks"]["StopCube"]
    assert stop["tiers"] == ["xhard4"] and stop["derive_ok"] == list(range(6))
    assert _selected(pool, "StopCube") == [0, 1, 2]


# ── sync_drop_and_backfill ────────────────────────────────────────────────────
def test_同步作废并按号递补():
    pool = _rollout.initial_pool(_loaded(), 3)
    assert _rollout.sync_drop_and_backfill(pool, "BinFill", 1, "xhard3:ScrewPlanFailure") == 3
    entry = pool["tasks"]["BinFill"]
    assert entry["state"]["1"]["status"] == "dropped"
    assert entry["sync_dropped"] == [{"candidate": 1, "reason": "xhard3:ScrewPlanFailure"}]
    assert entry["backfills"] == 1 and _selected(pool, "BinFill") == [0, 2, 3]
    # 非 selected 的候选（已退选或 spare）再报失败不动池
    assert _rollout.sync_drop_and_backfill(pool, "BinFill", 1, "again") is None
    assert _rollout.sync_drop_and_backfill(pool, "BinFill", 5, "spare") is None
    assert entry["backfills"] == 1 and len(entry["sync_dropped"]) == 1


def test_递补跳过已试过的spare():
    pool = _rollout.initial_pool(_loaded(), 3)
    entry = pool["tasks"]["BinFill"]
    entry["state"]["3"]["tiers"]["xhard1"] = {"status": "failed"}  # 3 已被试过（不应再被递补）
    assert _rollout.sync_drop_and_backfill(pool, "BinFill", 0, "x") == 4
    assert _rollout.sync_drop_and_backfill(pool, "BinFill", 2, "x") == 5
    assert _rollout.sync_drop_and_backfill(pool, "BinFill", 4, "x") is None  # 无可递补
    assert _selected(pool, "BinFill") == [1, 5]


def test_递补上限():
    pool = _rollout.initial_pool(_loaded(candidates=30), 3)
    entry = pool["tasks"]["BinFill"]
    assert _rollout.V7_BACKFILL_CAP == 10
    got = []
    for _ in range(_rollout.V7_BACKFILL_CAP + 2):
        victim = _selected(pool, "BinFill")[0]
        got.append(_rollout.sync_drop_and_backfill(pool, "BinFill", victim, "x"))
    assert got[: _rollout.V7_BACKFILL_CAP] == list(range(3, 3 + _rollout.V7_BACKFILL_CAP))
    assert got[_rollout.V7_BACKFILL_CAP:] == [None, None]
    assert entry["backfills"] == _rollout.V7_BACKFILL_CAP
    assert len(entry["sync_dropped"]) == _rollout.V7_BACKFILL_CAP + 2


# ── delivery_rows ────────────────────────────────────────────────────────────
def test_交付集合PASS(tmp_path):
    loaded = _loaded()
    pool = _rollout.initial_pool(loaded, 3)
    for task in ("BinFill", "StopCube"):
        for c in _selected(pool, task):
            _mark_ok(pool, task, c, pool["tasks"][task]["tiers"], tmp_path)
    rows, line = _rollout.delivery_rows(pool, loaded, tmp_path)
    assert line == "V7_DELIVERY_SET=PASS cells=5 per_cell=3 tier_set_equal=1"
    assert len(rows) == 3 * 4 + 3
    for tier in TIERS:
        assert sorted(r["candidate"] for r in rows if r["task"] == "BinFill" and r["tier"] == tier) == [0, 1, 2]
    stop = [r for r in rows if r["task"] == "StopCube"]
    assert {r["tier"] for r in stop} == {"xhard4"}
    first = next(r for r in rows if r["task"] == "BinFill" and r["tier"] == "xhard2" and r["candidate"] == 1)
    assert first["seed"] == 14_000_001 and first["spec_sha256"] == "BinFill-xhard2-1"
    assert first["h5_sha256"] == "sha-BinFill-xhard2-1" and first["path"] == "episodes/xhard2/BinFill_1.h5"
    assert first["recovery_mode"] is None


def test_交付不足或某档未成功FAIL(tmp_path):
    loaded = _loaded()
    pool = _rollout.initial_pool(loaded, 3)
    for task in ("BinFill", "StopCube"):
        for c in _selected(pool, task):
            tiers = pool["tasks"][task]["tiers"]
            _mark_ok(pool, task, c, [t for t in tiers if not (task == "BinFill" and c == 2 and t == "xhard3")], tmp_path)
    rows, line = _rollout.delivery_rows(pool, loaded, tmp_path)
    assert line.startswith("V7_DELIVERY_SET=FAIL") and "BinFill 交付 2/3" in line
    assert not any(r["task"] == "BinFill" and r["candidate"] == 2 for r in rows)  # 缺一档即四档都不交付


# ── run_continue_v7 端到端（假 runner）──────────────────────────────────────────
def _fake_runner(fail, calls):
    def run(batch, header, round_index):
        calls.append((header["difficulty"], [(r["task"], r["candidate"]) for r in batch]))
        out = []
        for row in batch:
            ok = (row["task"], header["difficulty"], row["candidate"]) not in fail
            out.append({"task": row["task"], "tier": row["tier"], "candidate": row["candidate"], "episode": row["episode"],
                        "seed": row["seed"], "attempt": row["attempt"], "spec_sha256": row["spec_sha256"], "ok": ok,
                        "error_type": None if ok else "ScrewPlanFailure", "error": None if ok else "规划失败",
                        "round": round_index, "role": row.get("_role", "selected"),
                        "h5": f"/fake/{row['tier']}/{row['task']}_{row['candidate']}.h5" if ok else None,
                        "h5_sha256": f"sha-{row['tier']}-{row['task']}-{row['candidate']}" if ok else None,
                        "bytes": 1 if ok else None, "frames": 1 if ok else None,
                        "env_module": f"robomme_hard.robomme_env.{row['task']}",
                        "spec_binding": {"layout_drift": 0}})
        return out
    return run


def test_run_continue_v7同步作废递补与回写(tmp_path):
    root = F.build_root(tmp_path / "specs", candidates=6, per_cell=3, missing={"xhard1": {("BinFill", 1)}})
    out = tmp_path / "out"
    calls = []
    summary = _rollout.run_continue_v7(root, out, src_root=tmp_path, workers=1, gpu="0", pkg="robomme_hard",
                                       code_baseline="test", batch_runner=_fake_runner({("BinFill", "xhard2", 0)}, calls))
    assert summary["delivery_set"].startswith("V7_DELIVERY_SET=PASS")
    assert summary["sync_dropped"] == 1 and summary["backfills"] == 1
    pool = json.loads((root / _rollout.POOL_NAME).read_text())
    # 初选 [0,2,3]（1 派生失败），0 在 xhard2 失败 → 四档一起退选，递补 4
    assert _selected(pool, "BinFill") == [2, 3, 4] and pool["tasks"]["BinFill"]["state"]["0"]["status"] == "dropped"
    assert _selected(pool, "StopCube") == [0, 1, 2]
    delivery = json.loads((out / "delivery.json").read_text())
    assert delivery["schema"] == "v7-delivery/1" and len(delivery["rows"]) == 3 * 4 + 3
    for tier in TIERS:
        assert sorted(r["candidate"] for r in delivery["rows"] if r["task"] == "BinFill" and r["tier"] == tier) == [2, 3, 4]
    # 回写后四档规格仍通过跨文件核对，selected 恰为交付集合，身份不变
    loaded = hard_specs.load_specs_v7(root, check_fingerprint=False)
    for tier in TIERS:
        header, rows = loaded[tier]
        sel = sorted((r["task"], r["candidate"]) for r in rows if hard_specs.delivered(r))
        want = [("BinFill", c) for c in (2, 3, 4)] + ([("StopCube", c) for c in (0, 1, 2)] if tier == "xhard4" else [])
        assert sel == sorted(want), tier
        tried0 = next(r for r in rows if r["task"] == "BinFill" and r["candidate"] == 0)
        assert tried0["selected"] is False
    # 已退选的 0 不再在后续轮次里被跑
    later = [c for tier, batch in calls[4:] for c in batch]
    assert ("BinFill", 0) not in later
