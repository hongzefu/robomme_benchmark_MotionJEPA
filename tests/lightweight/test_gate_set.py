"""``scripts/parity/gate_set.py``（固定检查集：V9 43 格 × 3 = 129；xhard0 16 任务 × 1 档 × 3 = 48）的纯 CPU 测试。

只读包内 V9 规格与仓库内冻结文件，不读 ``artifacts/``、不起仿真（builder 构造只读元数据，不 ``gym.make``）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from scripts.parity import gate_set as G

REPO = Path(__file__).resolve().parents[2]
FROZEN = REPO / "scripts" / "configs" / "gate-set-v9-129.json"
FROZEN_X0 = REPO / "scripts" / "configs" / "gate-set-xhard0-48.json"
X0_MANIFEST = REPO / "scripts" / "configs" / "newtask-v7" / "xhard0_manifest.json"


@pytest.fixture(scope="module")
def rows():
    return G.build_gate_set()


@pytest.fixture(scope="module")
def index():
    hs = G._hs()
    return G._delivery_index(str(hs.PACKAGED_SPECS_ROOT))


@pytest.fixture(scope="module")
def x0_rows():
    return G.load_xhard0_set(FROZEN_X0)


# ── V9 ─────────────────────────────────────────────────────────────────────


def test_两次构建完全相同(rows):
    assert G.build_gate_set() == rows
    assert G.build_payload() == G.build_payload()


def test_规模为43格乘3局_每个交付格恰3局(rows, index):
    table = G.allocation_table(rows)
    cells = {(t, tier) for (t, tier, _s) in index}
    assert len(cells) == 43
    assert {(t, tier) for t, cell in table.items() for tier in cell} == cells
    assert all(n == G.PER_CELL == 3 for cell in table.values() for n in cell.values())
    assert len(rows) == 129 and len(table) == 16
    assert all(set(r) == set(G.ROW_KEYS) for r in rows)
    assert len({(r["task"], r["tier"], r["seed"]) for r in rows}) == 129


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


def test_每格取候选号最小的3个(rows, index):
    table = G.allocation_table(rows)
    for task, cell in table.items():
        for tier in cell:
            pool = sorted(int(h["row"]["candidate"]) for (t, tr, _s), h in index.items() if t == task and tr == tier)
            got = [r["candidate"] for r in rows if r["task"] == task and r["tier"] == tier]
            assert got == pool[:3], (task, tier)
    assert table["InsertPeg"] == {"xhard4": 3} and table["MoveCube"] == {"xhard4": 3}
    assert table["StopCube"] == {f"xhard{i}": 3 for i in range(1, 6)}


def test_冻结文件与重算逐字节一致(rows):
    assert FROZEN.read_text(encoding="utf-8") == G.dumps_payload(G.build_payload())
    assert G.load_gate_set(FROZEN) == rows
    assert json.loads(FROZEN.read_text())["schema"] == "gate-set-v9/2"
    ok, line = G.check(FROZEN)
    assert ok, line
    assert line.startswith("GATE_SET=PASS cells=43 per_cell=3 total=129 in_delivery=129 sha=")


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
    assert len(keys) == 129 and f"{rows[0]['task']}_{rows[0]['tier']}_{rows[0]['seed']}" in keys
    with pytest.raises(G.GateSetError):
        G.to_legacy_identities(rows)  # legacy 只适用 xhard0
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


def test_cli_check_与_export(tmp_path, capsys):
    assert G.main(["check", "--path", str(FROZEN)]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("GATE_SET=PASS cells=43 per_cell=3 total=129")
    out = tmp_path / "g9.jsonl"
    assert G.main(["export", "--set", "v9", "--kind", "generate", "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 129


# ── xhard0 ─────────────────────────────────────────────────────────────────


def test_xhard0_冻结文件自洽_16任务乘3局(x0_rows):
    obj = json.loads(FROZEN_X0.read_text(encoding="utf-8"))
    assert obj["schema"] == "gate-set-xhard0/1"
    assert obj["source"]["file"] == "identities-small48.json" and len(obj["source"]["sha256"]) == 64
    assert obj["sha256"] == G.payload_sha256(obj)
    assert FROZEN_X0.read_text(encoding="utf-8") == G.dumps_payload(obj)
    assert len(x0_rows) == 48
    counts: dict[str, int] = {}
    for r in x0_rows:
        assert set(r) == set(G.XHARD0_ROW_KEYS) and r["tier"] == "xhard0"
        assert r["builder_episode"] == (r["source_episode"] - 3) // 4
        counts[r["task"]] = counts.get(r["task"], 0) + 1
    hs = G._hs()
    assert set(counts) == set(hs.ALL_TASKS) and set(counts.values()) == {3}
    order = {t: i for i, t in enumerate(hs.ALL_TASKS)}
    keys = [(order[r["task"]], r["source_episode"]) for r in x0_rows]
    assert keys == sorted(keys)
    ok, line = G.check_xhard0(FROZEN_X0)
    assert ok, line
    assert line.startswith("GATE_SET_XHARD0=PASS tasks=16 per_task=3 total=48 sha=")


def test_xhard0_每行都在官方_xhard0_清单内(x0_rows):
    manifest = json.loads(X0_MANIFEST.read_text(encoding="utf-8"))["rows"]
    official = {(r["task"], int(r["episode"]), int(r["seed"])) for r in manifest}
    assert all((r["task"], r["source_episode"], r["seed"]) in official for r in x0_rows)


def test_xhard0_篡改即报错(tmp_path):
    obj = json.loads(FROZEN_X0.read_text(encoding="utf-8"))
    obj["rows"][7]["seed"] += 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(G.GateSetError):
        G.load_xhard0_set(bad)
    ok, line = G.check_xhard0(bad)
    assert not ok and line.startswith("GATE_SET_XHARD0=FAIL")


def test_xhard0_从源格式构建与冻结文件一致(x0_rows, tmp_path):
    """按 small48 的源格式（含 e0_* 字段、按 task 分组的原序）还原一份源文件，build 出的行与冻结行相同。"""
    src = [{"builder_episode": r["builder_episode"], "e0_mme_order": 0, "e0_shard": i, "e0_smvla_order": 0,
            "seed": r["seed"], "source_episode": r["source_episode"], "task": r["task"]}
           for i, r in enumerate(reversed(x0_rows))]
    path = tmp_path / "identities-small48.json"
    path.write_text(json.dumps(src), encoding="utf-8")
    assert G.build_xhard0_set(path) == x0_rows
    payload = G.build_xhard0_payload(path)
    assert payload["rows"] == x0_rows and payload["source"]["file"] == "identities-small48.json"
    out = tmp_path / "x0.json"
    assert G.main(["build-xhard0", "--source", str(path), "--out", str(out)]) == 0
    ok, _line = G.check_xhard0(out, path)
    assert ok
    # 少一个任务即拒
    path.write_text(json.dumps([s for s in src if s["task"] != "MoveCube"]), encoding="utf-8")
    with pytest.raises(G.GateSetError):
        G.build_xhard0_set(path)


def test_xhard0_三种导出(x0_rows, tmp_path):
    gen = G.to_generate_identities(x0_rows)
    assert all(set(g) == {"task", "tier", "seed"} and g["tier"] == "xhard0" for g in gen)
    from scripts.parity import hard_parity

    path = G.write_generate_identities(x0_rows, tmp_path / "x0.jsonl")
    assert hard_parity.read_identity_subset(path) == {(r["task"], "xhard0", r["seed"]) for r in x0_rows}
    dig = G.to_env_digest_identities(x0_rows)
    assert [d["source_episode"] for d in dig] == [r["source_episode"] for r in x0_rows]
    assert all(d["source_episode"] >= 3 for d in dig)
    legacy = G.to_legacy_identities(x0_rows)
    assert legacy == [{"task": r["task"], "source_episode": r["source_episode"], "seed": r["seed"],
                       "builder_episode": r["builder_episode"]} for r in x0_rows]
    out = tmp_path / "legacy.json"
    assert G.main(["export", "--set", "xhard0", "--kind", "legacy", "--out", str(out)]) == 0
    assert json.loads(out.read_text()) == legacy
    # noise_gate.load_identities 对 gate-set* schema 调 load_gate_set：xhard0 冻结文件经转交可读
    assert G.load_gate_set(FROZEN_X0) == x0_rows


def test_xhard0_builder_episode_与开关为1的_builder_一致(x0_rows, monkeypatch):
    """开关为 1 时 test-hard builder 的前 12 条是 xhard0；只在本测试子进程里核对，避免污染已加载的 hard_specs。"""
    import subprocess

    code = (
        "import json,sys\n"
        "from robomme_hard.env_record_wrapper import hard_builder as B\n"
        "assert B.hard_specs.XHARD0_IN_TEST_HARD is True\n"
        "rows=json.loads(sys.argv[1]); cache={}\n"
        "for r in rows:\n"
        "    b=cache.get(r['task']) or cache.setdefault(r['task'], B.BenchmarkEnvBuilder(env_id=r['task'], dataset='test-hard'))\n"
        "    i=b.resolve_identity(r['builder_episode'])\n"
        "    assert (i['tier'], int(i['seed']), int(i.get('source_episode', -1))) == ('xhard0', r['seed'], r['source_episode']), (i, r)\n"
        "print('OK', len(rows))\n"
    )
    env = dict(__import__("os").environ, **{G.XHARD0_ENV: "1"})
    proc = subprocess.run([sys.executable, "-c", code, json.dumps(x0_rows)], env=env, capture_output=True, text=True,
                          timeout=240)
    if proc.returncode != 0 and "ModuleNotFoundError" in proc.stderr:
        pytest.skip("子进程导入 robomme_hard 失败")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().endswith("OK 48")
