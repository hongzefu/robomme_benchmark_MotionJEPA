"""``scripts/parity/gate_set.py``（G9 固定检查集，16 任务 × 12 局 = 192）的纯 CPU 测试。

只读包内 V9 规格与仓库内冻结文件，不读 ``artifacts/``、不起仿真（builder 构造只读元数据，不 ``gym.make``）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from scripts.parity import gate_set as G

REPO = Path(__file__).resolve().parents[2]
FROZEN = REPO / "scripts" / "configs" / "gate-set-v9-192.json"


@pytest.fixture(scope="module")
def rows():
    return G.build_gate_set()


@pytest.fixture(scope="module")
def index():
    hs = G._hs()
    return G._delivery_index(str(hs.PACKAGED_SPECS_ROOT))


def test_两次构建完全相同(rows):
    assert G.build_gate_set() == rows
    assert G.build_payload() == G.build_payload()


def test_规模为16任务乘12局(rows):
    table = G.allocation_table(rows)
    assert len(rows) == 192
    assert len(table) == 16
    assert all(sum(cell.values()) == 12 for cell in table.values())
    assert all(set(r) == set(G.ROW_KEYS) for r in rows)
    assert len({(r["task"], r["tier"], r["seed"]) for r in rows}) == 192


def test_任务规范序与_seed_layout_相同_且行按规范序排列(rows):
    spec = importlib.util.spec_from_file_location("_seed_layout", REPO / "scripts" / "injection-dev" / "seed_layout.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_seed_layout"] = module  # dataclass 解析注解需要模块已登记
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_seed_layout", None)
    hs = G._hs()
    assert tuple(module.ALL_TASKS) == tuple(hs.ALL_TASKS)
    order = {t: i for i, t in enumerate(hs.ALL_TASKS)}
    keys = [(order[r["task"]], r["tier"], r["candidate"]) for r in rows]
    assert keys == sorted(keys)


def test_每行都是交付行且字段与规格一致(rows, index):
    hs = G._hs()
    for r in rows:
        hit = index[(r["task"], r["tier"], r["seed"])]
        assert hs.delivered(hit["row"])
        assert int(hit["row"]["candidate"]) == r["candidate"]
        assert hit["row"]["spec_sha256"] == r["spec_sha256"]
        assert hit["builder_episode"] == r["builder_episode"]
        assert 0 <= r["builder_episode"] < 50


def test_档位分配符合最大余数法(rows, index):
    counts: dict[str, dict[str, int]] = {}
    for (task, tier, _seed) in index:
        counts.setdefault(task, {}).setdefault(tier, 0)
        counts[task][tier] += 1
    table = G.allocation_table(rows)
    for task, cell in counts.items():
        whole = sum(cell.values())
        tiers = sorted(cell)
        shares = {t: Fraction(12 * cell[t], whole) for t in tiers}
        floors = {t: int(shares[t]) for t in tiers}
        bonus = sorted(tiers, key=lambda t: (-(shares[t] - floors[t]), t))[: 12 - sum(floors.values())]
        want = {t: floors[t] + (t in bonus) for t in tiers}
        assert table[task] == {t: n for t, n in want.items() if n}, task
    # 计划里预期的分布
    assert table["PickXtimes"] == {"xhard1": 4, "xhard2": 4, "xhard3": 4}
    assert table["ButtonUnmask"] == {"xhard1": 3, "xhard2": 3, "xhard3": 3, "xhard4": 3}
    assert table["StopCube"] == {"xhard1": 3, "xhard2": 3, "xhard3": 2, "xhard4": 2, "xhard5": 2}
    assert table["InsertPeg"] == {"xhard4": 12} and table["MoveCube"] == {"xhard4": 12}
    assert table["BinFill"] == {"xhard1": 6, "xhard2": 6}


def test_每格取候选号最小的N个(rows, index):
    table = G.allocation_table(rows)
    for task, cell in table.items():
        for tier, n in cell.items():
            pool = sorted(int(h["row"]["candidate"]) for (t, tr, _s), h in index.items() if t == task and tr == tier)
            got = [r["candidate"] for r in rows if r["task"] == task and r["tier"] == tier]
            assert got == pool[:n], (task, tier)


def test_allocate_余数相同按档位升序():
    assert G.allocate({"xhard1": 10, "xhard2": 10, "xhard3": 10, "xhard4": 10, "xhard5": 10}) == \
        {"xhard1": 3, "xhard2": 3, "xhard3": 2, "xhard4": 2, "xhard5": 2}
    assert G.allocate({"xhard2": 13, "xhard1": 13, "xhard4": 12, "xhard3": 12}) == \
        {"xhard1": 3, "xhard2": 3, "xhard3": 3, "xhard4": 3}
    with pytest.raises(G.GateSetError):
        G.allocate({"xhard1": 5})


def test_冻结文件与重算逐字节一致(rows):
    assert FROZEN.read_text(encoding="utf-8") == G.dumps_payload(G.build_payload())
    assert G.load_gate_set(FROZEN) == rows
    ok, line = G.check(FROZEN)
    assert ok, line
    assert line.startswith("GATE_SET=PASS tasks=16 per_task=12 total=192 in_delivery=192 sha=")


def test_篡改冻结文件一个值即报错(tmp_path):
    obj = json.loads(FROZEN.read_text(encoding="utf-8"))
    obj["rows"][5]["seed"] += 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(G.GateSetError):
        G.load_gate_set(bad)
    ok, line = G.check(bad)
    assert not ok and line.startswith("GATE_SET=FAIL")


def test_导出格式(rows, tmp_path):
    gen = G.to_generate_identities(rows)
    assert gen[0] == {"task": rows[0]["task"], "tier": rows[0]["tier"], "seed": rows[0]["seed"]}
    dig = G.to_env_digest_identities(rows)
    assert all(d["source_episode"] == -1 and set(d) == {"task", "source_episode", "seed", "builder_episode"} for d in dig)
    keys = G.to_eval_keys(rows)
    assert len(keys) == 192 and f"{rows[0]['task']}_{rows[0]['tier']}_{rows[0]['seed']}" in keys
    # generate 身份文件能被 hard_parity 的读取函数读回同一集合
    from scripts.parity import hard_parity

    path = G.write_generate_identities(rows, tmp_path / "g9.jsonl")
    assert hard_parity.read_identity_subset(path) == {(r["task"], r["tier"], r["seed"]) for r in rows}
    with pytest.raises(G.GateSetError):
        G.write_generate_identities(rows, tmp_path / "g9.json")
    digest_path = G.write_env_digest_identities(rows, tmp_path / "g9.env.json")
    assert json.loads(digest_path.read_text()) == dig


def test_开关为1时拒绝(monkeypatch):
    monkeypatch.setenv(G.XHARD0_ENV, "1")
    with pytest.raises(G.GateSetError):
        G.build_gate_set()
    assert G._hs().XHARD0_IN_TEST_HARD is False  # 本测试进程默认开关为 0


def test_builder_episode_与_builder_resolve_identity_一致(rows):
    """真 builder（test-hard，开关为 0）逐行核对；只构造、读元数据，不建环境。"""
    builder_mod = pytest.importorskip("robomme_hard.env_record_wrapper.hard_builder")
    assert builder_mod.hard_specs.XHARD0_IN_TEST_HARD is False
    builders: dict[str, object] = {}
    for r in rows:
        builder = builders.get(r["task"])
        if builder is None:
            builder = builders[r["task"]] = builder_mod.BenchmarkEnvBuilder(env_id=r["task"], dataset="test-hard")
            assert builder.get_episode_num() == 50
        ident = builder.resolve_identity(r["builder_episode"])
        assert (ident["tier"], ident["candidate"], ident["seed"], ident["spec_sha256"]) == \
            (r["tier"], r["candidate"], r["seed"], r["spec_sha256"]), r
