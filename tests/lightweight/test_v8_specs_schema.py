#!/usr/bin/env python3
"""轻量测试：v8 规格 schema ``hard-specs/4`` 与 ``load_specs_v8``（v8 方案第二部分 §2.2 第 2～4 条，R6／R9／R10）。

纯 CPU 合成夹具：本文件自带最小 /4 builder（不依赖 ``scripts/injection-dev/_freeze``），在 tmp_path 里写
``<root>/<tier>/specs.jsonl``，覆盖：

* ``V8_CELLS`` 为表 2 的 43 格、合计 1070；``TIERS``／``BUILDER_TIERS``／``EXPECTED_CELLS``／``TIER_MAX_STEPS`` 仍是 v7 值（R10）；
* ``load_specs_v8`` 对完整 43 格根、冒烟 7 格根、分片子集根三种往返；
* 任务集合、每格 selected 数、跨档 seed 不交、schema 不符、缺档文件的拒绝；
* schema/4 篡改（改配额、exec_cap、seed 规则而不重签）必失败；重签后仍违反取值约束的也失败。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_specs_schema.py -q
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.env_record_wrapper import hard_specs as H  # noqa: E402

#: 2b 冒烟 7 格（v8 方案 §2.12 S2-A 行）：每格 1 局
SMOKE_CELLS = {("StopCube", "xhard1"): 1, ("StopCube", "xhard5"): 1, ("SwingXtimes", "xhard5"): 1,
               ("VideoUnmask", "xhard1"): 1, ("RouteStick", "xhard2"): 1, ("PatternLock", "xhard3"): 1,
               ("PickXtimes", "xhard3"): 1}
#: 分片子集：跨三档的几个任务，局数取 V8_CELLS 原值
SHARD_CELLS = {key: H.V8_CELLS[key] for key in (
    ("PickXtimes", "xhard1"), ("PickXtimes", "xhard2"), ("PickXtimes", "xhard3"),
    ("MoveCube", "xhard4"), ("InsertPeg", "xhard4"))}


# ── 最小 /4 builder ─────────────────────────────────────────────────────


def build_tier(tier: str, quotas: dict[str, int], *, spare: int = 2, profile: str = "v8",
               exec_cap: int = H.V8_EXEC_CAP) -> tuple[dict, list[dict]]:
    """合成一份 /4：每任务候选 ``quota + spare`` 个（episode＝candidate，attempt 0），前 ``quota`` 个 selected。"""
    rule = H.seed_rule_for(tier, profile)
    tasks = list(quotas)
    rows = []
    for task in tasks:
        for cand in range(quotas[task] + spare):
            spec = {"spec_kind": "native-newvalue/2", "task": task, "tier": tier, "layout": {"x": cand}}
            flag = cand < quotas[task]
            rows.append({"record": "spec", "task": task, "tier": tier, "candidate": cand, "episode": cand,
                         "seed": H.seed_for(task, cand, 0, rule), "attempt": 0,
                         "spec": spec, "spec_sha256": H.spec_sha256(spec),
                         "selected": flag, "tried": False, "initial_selected": flag, "rollout": None,
                         "layout_parent": None})
    sampling = {t: {"decision": {"k": t}, "native": {}} for t in tasks}
    header = {
        "record": "header", "schema": H.SCHEMA_V8, "difficulty": tier, "tasks": tasks,
        "per_env": {t: quotas[t] + spare for t in tasks},
        "runtime": dict(H.RUNTIME), "seed_rule": rule,
        "select_rule": {t: list(range(quotas[t])) for t in tasks},
        "sampling_config": sampling, "sampling_config_sha256": H.digest(sampling),
        "recovery_rule": {"rule": "off"}, "identity_source": "formula",
        "layout_rule": {"mode": "independent"}, "exec_cap": exec_cap,
        "delivery_per_cell": dict(quotas),
        "run_id": f"v8-fixture-{tier}", "draw_stats": {}, "provenance": {},
    }
    return _resign(header, rows), rows


def _resign(header: dict, rows: list[dict]) -> dict:
    header = dict(header)
    header["identity_sha256"] = H.identity_sha256(header, rows)
    header["delivery_sha256"] = H.delivery_sha256(rows)
    return header


def write_tier(root: Path, header: dict, rows: list[dict]) -> Path:
    path = root / header["difficulty"] / "specs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(H.canonical_json(r) + "\n" for r in (header, *rows)), encoding="utf-8")
    return path


def build_root(root: Path, cells: dict[tuple[str, str], int]) -> Path:
    """按格表写出 ``<root>/<tier>/specs.jsonl``（每档一份，任务集合＝格表在该档的任务）。"""
    by_tier: dict[str, dict[str, int]] = {}
    for (task, tier), n in cells.items():
        by_tier.setdefault(tier, {})[task] = n
    for tier, quotas in by_tier.items():
        write_tier(root, *build_tier(tier, quotas))
    return root


def _load(root, cells):
    return H.load_specs_v8(root, cells, check_fingerprint=False)


# ── 常量 ─────────────────────────────────────────────────────────────


def test_v8常量与表2一致():
    assert H.V8_TIERS == ("xhard1", "xhard2", "xhard3", "xhard4", "xhard5")
    assert H.V8_EXEC_CAP == 1600
    assert H.SCHEMA_V8 == "hard-specs/4" and H.SCHEMA_V8 in H.SCHEMAS
    assert len(H.V8_CELLS) == 43 and sum(H.V8_CELLS.values()) == 1070
    per_tier = {tier: sum(n for (_, t), n in H.V8_CELLS.items() if t == tier) for tier in H.V8_TIERS}
    assert per_tier == {"xhard1": 411, "xhard2": 411, "xhard3": 128, "xhard4": 100, "xhard5": 20}
    per_task = {}
    for (task, _), n in H.V8_CELLS.items():
        per_task[task] = per_task.get(task, 0) + n
    assert per_task == {"PickXtimes": 50, "SwingXtimes": 50, "StopCube": 50, "VideoUnmask": 80, "ButtonUnmask": 80,
                        "BinFill": 80, "VideoUnmaskSwap": 80, "ButtonUnmaskSwap": 80, "VideoPlaceButton": 80,
                        "VideoPlaceOrder": 80, "PickHighlight": 80, "VideoRepick": 80, "RouteStick": 80,
                        "PatternLock": 80, "MoveCube": 20, "InsertPeg": 20}
    assert [H.V8_CELLS[("PickXtimes", t)] for t in ("xhard1", "xhard2", "xhard3")] == [17, 17, 16]
    assert [H.V8_CELLS[("RouteStick", t)] for t in ("xhard1", "xhard2", "xhard3")] == [27, 27, 26]
    assert H.V8_SEED_OFFSETS == {"xhard1": 16_000_000, "xhard2": 18_000_000, "xhard3": 20_000_000,
                                 "xhard4": 22_000_000, "xhard5": 24_000_000}
    header_keys, row_keys = H.IDENTITY_KEYS_BY_SCHEMA[H.SCHEMA_V8]
    v7_header, v7_row = H.IDENTITY_KEYS_BY_SCHEMA[H.SCHEMA_V7]
    assert header_keys == v7_header + ("exec_cap", "delivery_per_cell")
    assert row_keys == v7_row


def test_v7档位常量未动_R10():
    assert H.TIERS == ("xhard1", "xhard2", "xhard3", "xhard4")
    assert H.BUILDER_TIERS == ("xhard0", "xhard1", "xhard2", "xhard3", "xhard4")
    assert H.TIER_MAX_STEPS == {"xhard0": 1300, "xhard1": 1500, "xhard2": 2400, "xhard3": 2900, "xhard4": 3800}
    assert H.XHARD4_ONLY == ("StopCube", "InsertPeg", "MoveCube")
    assert len(H.EXPECTED_CELLS) == 55
    assert H.EXPECTED_CELLS == frozenset(
        (task, tier) for tier in H.V7_TIERS for task in H.ALL_TASKS
        if tier == "xhard4" or task not in H.V7_XHARD4_ONLY)


# ── load_specs_v8 往返 ─────────────────────────────────────────────────


def test_完整43格根往返(tmp_path):
    build_root(tmp_path, H.V8_CELLS)
    out = _load(tmp_path, H.V8_CELLS)
    assert list(out) == list(H.V8_TIERS)
    total = 0
    for tier, (header, rows) in out.items():
        assert header["schema"] == H.SCHEMA_V8 and header["difficulty"] == tier
        for row in rows:
            if row["selected"]:
                total += 1
    assert total == 1070


def test_冒烟7格根往返(tmp_path):
    build_root(tmp_path, SMOKE_CELLS)
    out = _load(tmp_path, SMOKE_CELLS)
    assert list(out) == ["xhard1", "xhard2", "xhard3", "xhard5"]  # 7 格不涉及 xhard4，不读该档
    assert set(out["xhard5"][0]["tasks"]) == {"StopCube", "SwingXtimes"}
    selected = {(r["task"], r["tier"]) for _, rows in out.values() for r in rows if r["selected"]}
    assert selected == set(SMOKE_CELLS)
    # 冒烟根不能当完整根读
    with pytest.raises(H.SpecsError):
        _load(tmp_path, H.V8_CELLS)


def test_分片子集根往返且只读涉及的档(tmp_path):
    build_root(tmp_path, SHARD_CELLS)
    # 不涉及的档放一份坏文件，验证不会被读
    (tmp_path / "xhard5").mkdir()
    (tmp_path / "xhard5" / "specs.jsonl").write_text("not json\n", encoding="utf-8")
    out = _load(tmp_path, SHARD_CELLS)
    assert list(out) == ["xhard1", "xhard2", "xhard3", "xhard4"]
    assert set(out["xhard4"][0]["tasks"]) == {"MoveCube", "InsertPeg"}
    # 只传 xhard4 一档的子集
    only4 = {k: v for k, v in SHARD_CELLS.items() if k[1] == "xhard4"}
    assert list(_load(tmp_path, only4)) == ["xhard4"]


def test_格表本身非法即拒(tmp_path):
    build_root(tmp_path, SMOKE_CELLS)
    for bad in ({}, {("PickXtimes", "xhard4"): 1}, {("StopCube", "xhard0"): 1}, {("StopCube", "xhard1"): 0},
                {("StopCube", "xhard1"): True}):
        with pytest.raises(H.SpecsError, match="expected_cells"):
            _load(tmp_path, bad)


def test_任务集合与每格局数必须相等(tmp_path):
    build_root(tmp_path, SMOKE_CELLS)
    # 格表少一个 xhard5 任务：文件里多出任务
    fewer = {k: v for k, v in SMOKE_CELLS.items() if k != ("SwingXtimes", "xhard5")}
    with pytest.raises(H.SpecsError, match="任务集合"):
        _load(tmp_path, fewer)
    # 格表要 2 局、文件只 selected 1 局（相等，不是 ≤）
    more = {**SMOKE_CELLS, ("StopCube", "xhard1"): 2}
    with pytest.raises(H.SpecsError, match="selected 行数"):
        _load(tmp_path, more)
    # 缺档文件
    (tmp_path / "xhard3" / "specs.jsonl").unlink()
    with pytest.raises(H.SpecsError, match="缺少"):
        _load(tmp_path, SMOKE_CELLS)


def test_非schema4文件不被v8加载器接受(tmp_path):
    header, rows = build_tier("xhard1", {"StopCube": 1})
    header = {k: v for k, v in header.items() if k not in ("exec_cap",)}
    header["schema"] = H.SCHEMA_V7  # /3 校验会先在 seed 规则／layout_rule 上拒绝
    write_tier(tmp_path, _resign(header, rows), rows)
    with pytest.raises(H.SpecsError):
        _load(tmp_path, {("StopCube", "xhard1"): 1})


def test_跨档seed相交即拒(tmp_path, monkeypatch):
    build_root(tmp_path, {("StopCube", "xhard1"): 1})
    # 人为让 xhard2 与 xhard1 同 offset，写一份「合法签名」的 xhard2 文件，加载器跨文件检查必须拒绝
    monkeypatch.setitem(H.V8_SEED_OFFSETS, "xhard2", H.V8_SEED_OFFSETS["xhard1"])
    write_tier(tmp_path, *build_tier("xhard2", {"StopCube": 1}))
    with pytest.raises(H.SpecsError, match="seed 相交"):
        _load(tmp_path, {("StopCube", "xhard1"): 1, ("StopCube", "xhard2"): 1})


# ── schema/4 篡改 ─────────────────────────────────────────────────────


def _tier():
    return build_tier("xhard5", {"StopCube": 2, "SwingXtimes": 3})


def test_schema4合法文件通过校验():
    header, rows = _tier()
    H.validate_specs(header, rows)


@pytest.mark.parametrize("mutate", [
    lambda h: h["delivery_per_cell"].__setitem__("StopCube", 5),          # 改配额（放宽也不行）
    lambda h: h.__setitem__("exec_cap", 1800),                           # 改 exec_cap
    lambda h: h.__setitem__("seed_rule", H.seed_rule_for("xhard4", "v8")),  # 改 seed 规则
    lambda h: h["seed_rule"].__setitem__("offset", 30_000_000),
    lambda h: h.__setitem__("layout_rule", {"mode": "shared"}),
], ids=["配额", "exec_cap", "seed规则换档", "seed规则offset", "layout_rule"])
def test_schema4篡改不重签必失败(mutate):
    header, rows = _tier()
    header = copy.deepcopy(header)
    mutate(header)
    with pytest.raises(H.SpecsError):
        H.validate_specs(header, rows)


def test_配额进签_放宽配额只因签名失败():
    header, rows = _tier()
    header = copy.deepcopy(header)
    header["delivery_per_cell"]["StopCube"] = 5
    with pytest.raises(H.SpecsError, match="identity_sha256"):
        H.validate_specs(header, rows)
    H.validate_specs(_resign(header, rows), rows)  # 重签后取值本身合法


@pytest.mark.parametrize("mutate,match", [
    (lambda h: h.__setitem__("exec_cap", 1800), "exec_cap"),
    (lambda h: h.__setitem__("seed_rule", H.seed_rule_for("xhard4", "v8")), "v8"),
    (lambda h: h.__setitem__("layout_rule", {"mode": "shared"}), "layout_rule"),
    (lambda h: h["delivery_per_cell"].__setitem__("StopCube", 1), "超过 delivery_per_cell"),
    (lambda h: h["delivery_per_cell"].pop("StopCube"), "delivery_per_cell"),
    (lambda h: h["per_env"].__setitem__("StopCube", "4"), "per_env"),
    (lambda h: h["select_rule"].__setitem__("StopCube", [0, 0]), "select_rule"),
    (lambda h: h.__setitem__("tasks", [*h["tasks"], "BinFill"]), "交付格"),
], ids=["exec_cap", "seed规则", "layout_rule", "配额低于selected", "配额缺任务", "per_env类型", "select_rule重复", "非交付格任务"])
def test_schema4重签后取值违规仍失败(mutate, match):
    header, rows = _tier()
    header = copy.deepcopy(header)
    mutate(header)
    with pytest.raises(H.SpecsError, match=match):
        H.validate_specs(_resign(header, rows), rows)


def test_schema4行约束():
    header, rows = _tier()
    for mutate in (lambda r: r.__setitem__("layout_parent", {"tier": "xhard4", "candidate": 0, "spec_sha256": "x"}),
                   lambda r: (r["spec"].__setitem__("spec_kind", "native-layered/3"),
                              r.__setitem__("spec_sha256", H.spec_sha256(r["spec"])))):
        bad = copy.deepcopy(rows)
        mutate(bad[0])
        with pytest.raises(H.SpecsError, match="native-newvalue/2"):
            H.validate_specs(_resign(header, bad), bad)
    # 行 seed 不按本档 v8 规则
    bad = copy.deepcopy(rows)
    bad[0]["seed"] += 1
    with pytest.raises(H.SpecsError, match="seed"):
        H.validate_specs(_resign(header, bad), bad)


def test_schema4经load_specs读回(tmp_path):
    header, rows = _tier()
    path = write_tier(tmp_path, header, rows)
    got_header, got_rows = H.load_specs(path, check_fingerprint=False)
    assert got_header == json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert len(got_rows) == len(rows)
