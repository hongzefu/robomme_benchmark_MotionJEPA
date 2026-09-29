#!/usr/bin/env python3
"""轻量测试：V7 规格封签 ``hard-specs/3``（0928 方案第二部分 §1.1）。

* ``_freeze.freeze`` 带 ``layout_rule`` 时封成 /3：header 多 ``layout_rule``、行多 ``layout_parent``（母布局为 null），
  ``validate_specs`` 接受；/3 只认 v7 seed 规则、``layout_rule`` 形态与 ``layout_parent`` 形态不符即拒；
* 身份键按 schema 分表：/3 的 ``identity_sha256`` 覆盖 ``layout_rule``／``layout_parent``；/2 的身份键与摘要算法不变，
  包内 v6 规格（xhard1..4，/2）照旧通过 ``load_specs``；
* ``load_specs_v7`` 的跨文件核对：派生行指向 xhard4 同候选且摘要／seed 相同；
* ``parse_select("0..19")``；``freeze_equiv`` 已删。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_freeze_schema.py -q
"""

from __future__ import annotations

import copy
import json
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared import v7_specs_fixture as F  # noqa: E402

import _freeze  # noqa: E402  （路径由夹具模块加入）
from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

TASKS = ("BinFill", "StopCube")


def _rehash(header, rows):
    header = dict(header)
    header["identity_sha256"] = hard_specs.identity_sha256(header, rows)
    header["delivery_sha256"] = hard_specs.delivery_sha256(rows)
    return header


def test_freeze带layout_rule封成v3():
    header, rows = F.freeze_parent(TASKS, candidates=5, per_cell=3)
    assert header["schema"] == hard_specs.SCHEMA_V7 == "hard-specs/3"
    assert header["layout_rule"] == F.LAYOUT_RULE
    assert header["seed_rule"] == hard_specs.seed_rule_for("xhard4", "v7")
    assert header["delivery_per_cell"] == 3
    assert all(row["layout_parent"] is None for row in rows)
    assert sorted(r["candidate"] for r in rows if r["task"] == "BinFill" and r["initial_selected"]) == [0, 1, 2]
    hard_specs.validate_specs(header, rows)
    # 身份覆盖 layout_rule：改白名单摘要后旧 identity 不再成立
    changed = copy.deepcopy(header)
    changed["layout_rule"]["whitelist_sha256"] = "1" * 64
    with pytest.raises(hard_specs.SpecsError, match="identity_sha256"):
        hard_specs.validate_specs(changed, rows)
    assert hard_specs.identity_sha256(changed, rows) != header["identity_sha256"]


def test_freeze不带layout_rule仍是v2且身份键不变():
    drafts = F.parent_drafts(TASKS, 4, difficulty="xhard1", profile="v6")
    header, rows = _freeze.freeze(drafts, F.header_parts(TASKS, difficulty="xhard1", layout_rule=None, profile="v6"),
                                  (0, 1), 4)
    assert header["schema"] == hard_specs.SCHEMA == "hard-specs/2"
    assert "layout_rule" not in header and all("layout_parent" not in r for r in rows)
    # /2 身份摘要按原键集合（与 V7 前逐字相同）
    ordered = sorted(rows, key=lambda r: (r["task"], int(r["candidate"])))
    expected = hard_specs.digest({
        "header": {k: header[k] for k in hard_specs.IDENTITY_HEADER_KEYS},
        "rows": [{k: r[k] for k in hard_specs.IDENTITY_ROW_KEYS} for r in ordered],
    })
    assert header["identity_sha256"] == expected
    assert hard_specs.IDENTITY_KEYS_BY_SCHEMA[hard_specs.SCHEMA] == (hard_specs.IDENTITY_HEADER_KEYS,
                                                                    hard_specs.IDENTITY_ROW_KEYS)
    header_keys, row_keys = hard_specs.IDENTITY_KEYS_BY_SCHEMA[hard_specs.SCHEMA_V7]
    assert header_keys == hard_specs.IDENTITY_HEADER_KEYS + ("layout_rule",)
    assert row_keys == hard_specs.IDENTITY_ROW_KEYS + ("layout_parent",)


def test_v3只认v7种子规则与合法layout_rule():
    drafts = F.parent_drafts(TASKS, 3, profile="v6")
    with pytest.raises(hard_specs.SpecsError, match="v7 seed"):
        _freeze.freeze(drafts, F.header_parts(TASKS, profile="v6"), (0,), 3)
    drafts = F.parent_drafts(TASKS, 3)
    for bad in ({"mode": "independent", "parent_tier": "xhard4", "whitelist_sha256": "0"},
                {"mode": "shared", "parent_tier": "xhard3", "whitelist_sha256": "0"},
                {"mode": "shared", "parent_tier": "xhard4"}):
        with pytest.raises(hard_specs.SpecsError, match="layout_rule"):
            _freeze.freeze(drafts, F.header_parts(TASKS, layout_rule=bad), (0,), 3)


def test_v3的layout_parent形态核对():
    header4, rows4 = F.freeze_parent(TASKS, candidates=4, per_cell=2)
    # 母布局行规格必须是 native-newvalue/2
    bad = copy.deepcopy(rows4)
    bad[0]["spec"]["spec_kind"] = "native-layered/3"
    bad[0]["spec_sha256"] = hard_specs.spec_sha256(bad[0]["spec"])
    with pytest.raises(hard_specs.SpecsError, match="母布局行"):
        hard_specs.validate_specs(_rehash(header4, bad), bad)
    # 母布局行 layout_parent 必须为 null
    bad = copy.deepcopy(rows4)
    bad[0]["layout_parent"] = {"tier": "xhard4", "candidate": 0, "spec_sha256": "x"}
    with pytest.raises(hard_specs.SpecsError, match="母布局行"):
        hard_specs.validate_specs(_rehash(header4, bad), bad)
    header1, rows1 = F.derive_tier(header4, rows4, "xhard1")
    hard_specs.validate_specs(header1, rows1)
    for mutate, match in (
        (lambda r: r.__setitem__("layout_parent", None), "layout_parent"),
        (lambda r: r["layout_parent"].__setitem__("candidate", r["candidate"] + 1), "layout_parent"),
        (lambda r: r["layout_parent"].__setitem__("tier", "xhard3"), "layout_parent"),
        (lambda r: r["layout_parent"].__setitem__("extra", 1), "layout_parent"),
    ):
        bad = copy.deepcopy(rows1)
        mutate(bad[0])
        with pytest.raises(hard_specs.SpecsError, match=match):
            hard_specs.validate_specs(_rehash(header1, bad), bad)
    bad = copy.deepcopy(rows1)
    bad[0]["spec"]["spec_kind"] = "native-newvalue/2"
    bad[0]["spec_sha256"] = hard_specs.spec_sha256(bad[0]["spec"])
    with pytest.raises(hard_specs.SpecsError, match="native-layered/3"):
        hard_specs.validate_specs(_rehash(header1, bad), bad)
    # /3 行缺 layout_parent 键：字段集合不符
    bad = copy.deepcopy(rows1)
    del bad[0]["layout_parent"]
    with pytest.raises(hard_specs.SpecsError, match="字段集合"):
        hard_specs.validate_specs(header1, bad)


def test_load_specs_v7跨文件核对(tmp_path):
    root = F.build_root(tmp_path / "ok", candidates=4, per_cell=2)
    loaded = hard_specs.load_specs_v7(root, check_fingerprint=False)
    assert set(loaded) == set(hard_specs.TIERS)
    assert all(loaded[t][0]["schema"] == hard_specs.SCHEMA_V7 for t in hard_specs.TIERS)
    assert {r["task"] for r in loaded["xhard1"][1]} == {"BinFill"}  # 只有 xhard4 的任务不派生
    # 派生行指向的母摘要被换（自洽地重签）：单文件校验通过，跨文件核对拒绝
    bad_root = F.build_root(tmp_path / "bad", candidates=4, per_cell=2)
    path = bad_root / "xhard2" / "specs.jsonl"
    records = [json.loads(t) for t in path.read_text().splitlines() if t.strip()]
    header, rows = records[0], records[1:]
    rows[0]["layout_parent"]["spec_sha256"] = "f" * 64
    header = _rehash(header, rows)
    hard_specs.validate_specs(header, rows)
    path.write_text("".join(hard_specs.canonical_json(r) + "\n" for r in [header, *rows]))
    with pytest.raises(hard_specs.SpecsError, match="母布局"):
        hard_specs.load_specs_v7(bad_root, check_fingerprint=False)


def test_load_specs_v7拒绝混入v2文件(tmp_path):
    root = F.build_root(tmp_path / "mix", candidates=3, per_cell=1)
    v2 = tmp_path / "v2.jsonl"
    drafts = F.parent_drafts(("BinFill",), 3, difficulty="xhard3", profile="v6")
    header, rows = _freeze.freeze(drafts, F.header_parts(("BinFill",), difficulty="xhard3", layout_rule=None,
                                                         profile="v6"), (0,), 3)
    _freeze.write_jsonl_exclusive(v2, [header, *rows])
    (root / "xhard3" / "specs.jsonl").unlink()
    (root / "xhard3" / "specs.jsonl").write_text(v2.read_text())
    with pytest.raises(hard_specs.SpecsError, match="hard-specs/3"):
        hard_specs.load_specs_v7(root, check_fingerprint=False)


@pytest.mark.parametrize("tier", hard_specs.TIERS)
def test_包内v6规格仍按v2通过(tier):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 源码指纹不符只警告
        header, rows = hard_specs.load_specs(hard_specs.PACKAGED_SPECS_ROOT / tier / "specs.jsonl")
    assert header["schema"] == hard_specs.SCHEMA
    assert header["seed_rule"] == hard_specs.seed_rule_for(tier, "v6")
    assert hard_specs.identity_sha256(header, rows) == header["identity_sha256"]
    assert all("layout_parent" not in r for r in rows)


def test_parse_select与freeze_equiv已删():
    assert _freeze.parse_select("0..19") == tuple(range(20))
    assert _freeze.parse_select("default") == (0, 3, 6)
    assert _freeze.parse_select("1,4,7") == (1, 4, 7)
    assert not hasattr(_freeze, "freeze_equiv")
    header, rows = F.freeze_parent(TASKS, candidates=20, per_cell=20)
    assert header["delivery_per_cell"] == 20 and header["select_rule"]["indices"] == list(range(20))
    assert sum(r["selected"] for r in rows if r["task"] == "StopCube") == 20
