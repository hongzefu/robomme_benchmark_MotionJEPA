#!/usr/bin/env python3
"""轻量测试：``robomme_hard`` 评估构建器 ``dataset="test-hard"`` 的 xhard0 前缀（0928 方案第二部分 §1.1）。

* 每任务局数＝xhard0 12 + 交付格表 ``EXPECTED_CELLS`` 该任务合计（由格表推出，不写死）：v8 包为
  PickXtimes／SwingXtimes／StopCube 62、MoveCube／InsertPeg 32、其余 92（合计 1262）；v9 阶段 3b 换包后每任务
  12 + 50 = 62（合计 992）；
* episode 0..11 为 xhard0，seed 逐条等于官方 test 元数据 difficulty=="hard" 子集（原 episode 升序）；
  之后按 xhard1→xhard5 只排该任务在交付格表里的档（xhard5 只有 SwingXtimes、StopCube），档内候选升序；
* 覆盖规格根：v7 ``hard-specs/3`` 文件拒绝；局部根（只含部分档）只发存在的档；
* xhard0 的 ``_hard_env_kwargs`` 恰为 ``{"seed", "difficulty": "hard"}``（无 sampling_config、无规格）；
  ``resolve_identity`` 带 source_dataset／source_episode、candidate 与 spec_sha256 为 None；
* ``override_metadata_path`` 与 test-hard 同用即拒绝；``specs_root`` 参数与环境变量 ``ROBOMME_HARD_SPECS_ROOT``。

只构建 builder（读元数据与包内 jsonl），不 ``gym.make``、不起仿真。

    uv run --no-sync python -m pytest tests/lightweight/test_hard_builder_xhard0.py -q
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, hard_specs as V  # noqa: E402
from robomme_hard.env_record_wrapper import hard_builder as HB  # noqa: E402

TEST_META = REPO_ROOT / "src" / "robomme" / "env_metadata" / "test"


def _official_hard(task):
    payload = json.loads((TEST_META / f"record_dataset_{task}_metadata.json").read_text(encoding="utf-8"))
    return sorted((r for r in payload["records"] if r.get("difficulty") == "hard"), key=lambda r: int(r["episode"]))


def _builder(task, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 包内 v6 规格的源码指纹与当前源码不符只警告
        return BenchmarkEnvBuilder(task, dataset="test-hard", **kwargs)


@pytest.fixture(scope="module")
def builders():
    return {task: _builder(task) for task in V.ALL_TASKS}


def _episodes_per_task(cells) -> dict:
    """逐任务局数（含 xhard0 12 局）＝ 12 + 格表该任务合计。"""
    return {task: V.XHARD0_PER_TASK + sum(n for (t, _), n in cells.items() if t == task) for task in V.ALL_TASKS}


#: 包内交付格表推出的逐任务合计（含 xhard0 12 局）：v8 包 62／32／92（合计 1262），v9 包每任务 62（合计 992）
V8_EPISODES = _episodes_per_task(V.EXPECTED_CELLS)


def test_逐任务局数常量合计1262():
    """函数名沿用 v8；合计由格表推出：v8 表 1262、v9 表 992，包内取哪张随 ``EXPECTED_CELLS``。"""
    assert _episodes_per_task(V.V8_CELLS) == {task: 92 for task in V.ALL_TASKS} | {
        "PickXtimes": 62, "SwingXtimes": 62, "StopCube": 62, "MoveCube": 32, "InsertPeg": 32}
    assert sum(_episodes_per_task(V.V8_CELLS).values()) == 16 * 12 + 1070 == 1262
    assert _episodes_per_task(V.V9_CELLS) == {task: 62 for task in V.ALL_TASKS}
    assert sum(_episodes_per_task(V.V9_CELLS).values()) == 16 * 12 + 800 == 992
    assert sum(V8_EPISODES.values()) == 16 * 12 + sum(V.EXPECTED_CELLS.values())
    for task in V.ALL_TASKS:
        assert V8_EPISODES[task] == V.XHARD0_PER_TASK + sum(n for (t, _), n in V.EXPECTED_CELLS.items() if t == task)
    assert {t for (t, tier) in V.EXPECTED_CELLS if tier == "xhard5"} == {"SwingXtimes", "StopCube"}
    assert {t for t in V.ALL_TASKS if {tier for (n, tier) in V.EXPECTED_CELLS if n == t} == {"xhard4"}} \
        == set(V.XHARD4_ONLY) == {"InsertPeg", "MoveCube"}


@pytest.mark.parametrize("task", V.ALL_TASKS)
def test_每任务局数与档序(task, builders):
    b = builders[task]
    assert b.get_episode_num() == V8_EPISODES[task]
    tiers = [b.resolve_episode(ep)[1] for ep in range(b.get_episode_num())]
    expected = ["xhard0"] * 12 + [t for t in V.TIERS for _ in range(V.EXPECTED_CELLS.get((task, t), 0))]
    assert tiers == expected
    # 档内候选升序
    for tier in V.TIERS:
        cands = [b.resolve_identity(ep)["candidate"] for ep in range(b.get_episode_num()) if tiers[ep] == tier]
        assert cands == sorted(cands)


@pytest.mark.parametrize("task", V.ALL_TASKS)
def test_xhard0种子等于官方test元数据hard子集(task, builders):
    b = builders[task]
    official = _official_hard(task)
    assert len(official) == 12
    for ep, record in enumerate(official):
        assert b.resolve_episode(ep) == (int(record["seed"]), "xhard0")
        identity = b.resolve_identity(ep)
        assert identity == {"episode": ep, "tier": "xhard0", "candidate": None, "seed": int(record["seed"]),
                            "source_dataset": "test", "source_episode": int(record["episode"]),
                            "spec_sha256": None, "source_run": None}
        assert b._hard_env_kwargs(ep) == {"seed": int(record["seed"]), "difficulty": "hard"}


def test_新值档条目仍带规格与配置(builders):
    b = builders["BinFill"]
    kwargs = b._hard_env_kwargs(12)
    assert kwargs["difficulty"] == "xhard1"
    assert set(kwargs) == {"seed", "difficulty", "sampling_config", "native_episode_spec"}
    identity = b.resolve_identity(12)
    assert identity["tier"] == "xhard1" and isinstance(identity["candidate"], int)
    assert identity["spec_sha256"] == V.spec_sha256(kwargs["native_episode_spec"])
    assert "source_episode" not in identity and "specs_root" not in identity
    with pytest.raises(KeyError):
        b.resolve_episode(V8_EPISODES["BinFill"])
    # xhard5 档条目：只有 SwingXtimes、StopCube
    stop = builders["StopCube"]
    last = stop.get_episode_num() - 1
    assert stop._hard_env_kwargs(last)["difficulty"] == "xhard5" and stop.resolve_identity(last)["tier"] == "xhard5"


def test_test_hard拒绝override_metadata_path():
    with pytest.raises(ValueError, match="override_metadata_path"):
        BenchmarkEnvBuilder("BinFill", dataset="test-hard",
                            override_metadata_path=TEST_META / "record_dataset_BinFill_metadata.json")


def test_官方hard子集不符即拒绝():
    b = _builder("PickXtimes")
    index = {("PickXtimes", r["episode"]): dict(r) for r in _official_hard("PickXtimes")}
    entries = HB._xhard0_entries("PickXtimes", index)
    assert [e["row"]["source_episode"] for e in entries] == list(V.XHARD0_EPISODES)
    assert all(e["tier"] == "xhard0" and e["sampling_config"] is None and e["row"]["spec"] is None for e in entries)
    missing = dict(index)
    missing.pop(("PickXtimes", 47))
    with pytest.raises(ValueError, match="xhard0"):
        HB._xhard0_entries("PickXtimes", missing)
    dup = {k: dict(v) for k, v in index.items()}
    dup[("PickXtimes", 7)]["seed"] = dup[("PickXtimes", 3)]["seed"]
    with pytest.raises(ValueError, match="seed 唯一"):
        HB._xhard0_entries("PickXtimes", dup)
    # 其它难度的记录不混进来
    assert b.get_episode_num() == V8_EPISODES["PickXtimes"]


def _linked_root(tmp_path: Path) -> Path:
    root = tmp_path / "specs-root"
    root.mkdir()
    for tier in V.TIERS:
        (root / tier).symlink_to(V.PACKAGED_SPECS_ROOT / tier, target_is_directory=True)
    return root


def test_specs_root参数_身份带规格根(tmp_path, capsys):
    root = _linked_root(tmp_path)
    b = _builder("VideoRepick", specs_root=root)
    out = capsys.readouterr().out
    assert f"SPECS_ROOT={root.resolve()}" in out
    assert b.get_episode_num() == V8_EPISODES["VideoRepick"]
    assert b.resolve_identity(0)["specs_root"] == str(root.resolve())
    assert b.resolve_identity(40)["specs_root"] == str(root.resolve())
    # 显式给包内路径等同缺省：身份不带 specs_root
    packaged = _builder("VideoRepick", specs_root=V.PACKAGED_SPECS_ROOT)
    assert "specs_root" not in packaged.resolve_identity(0)


def test_specs_root环境变量与packaged_specs_path(tmp_path, monkeypatch):
    root = _linked_root(tmp_path)
    monkeypatch.delenv(V.SPECS_ROOT_ENV, raising=False)
    assert V.specs_root() == V.PACKAGED_SPECS_ROOT
    assert V.packaged_specs_path("xhard2") == V.PACKAGED_SPECS_ROOT / "xhard2" / "specs.jsonl"
    monkeypatch.setenv(V.SPECS_ROOT_ENV, str(root))
    assert V.specs_root() == root.resolve()
    assert V.packaged_specs_path("xhard3") == root.resolve() / "xhard3" / "specs.jsonl"
    # 显式参数优先于环境变量
    assert V.specs_root(V.PACKAGED_SPECS_ROOT) == V.PACKAGED_SPECS_ROOT
    with pytest.raises(V.SpecsError):
        V.packaged_specs_path("xhard0")  # xhard0 没有规格文件
    b = _builder("StopCube")
    assert b.resolve_identity(12)["specs_root"] == str(root.resolve())


def test_覆盖根_局部根只发存在的档(tmp_path):
    """局部根（只含 xhard5）：只发 xhard5 局，与 hard_regression.delivery_index 的跳过口径一致。"""
    root = tmp_path / "partial"
    root.mkdir()
    (root / "xhard5").symlink_to(V.PACKAGED_SPECS_ROOT / "xhard5", target_is_directory=True)
    b = _builder("SwingXtimes", specs_root=root)
    assert [b.resolve_episode(ep)[1] for ep in range(b.get_episode_num())] == \
        ["xhard0"] * 12 + ["xhard5"] * V.EXPECTED_CELLS[("SwingXtimes", "xhard5")]
    assert _builder("BinFill", specs_root=root).get_episode_num() == 12


def test_覆盖根_v7规格拒绝(tmp_path):
    """换包后 builder 只读 hard-specs/4：覆盖根里出现 /3 文件即拒绝（v7 由标签 parity-anchor-v7 复现）。"""
    root = tmp_path / "v7root"
    (root / "xhard1").mkdir(parents=True)
    (root / "xhard1" / "specs.jsonl").write_text(json.dumps({"record": "header", "schema": V.SCHEMA_V7}) + "\n")
    with pytest.raises(V.SpecsError, match="parity-anchor-v7"):
        _builder("BinFill", specs_root=root)


def test_覆盖根_空根拒绝(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(V.SpecsError, match="没有任何"):
        _builder("BinFill", specs_root=tmp_path / "empty")


def test_交付格表外的格有正式局即拒绝(monkeypatch):
    """(任务, 档) 不在交付格表内却有正式局 → 拒绝（v8 方案第一部分 §2.1 difficulty.py 行的 3b 断言）。"""
    shrunk = {k: v for k, v in V.EXPECTED_CELLS.items() if k != ("StopCube", "xhard5")}
    monkeypatch.setattr(V, "EXPECTED_CELLS", shrunk)
    HB._root_specs.cache_clear()
    try:
        with pytest.raises(ValueError):
            _builder("StopCube")
    finally:
        HB._root_specs.cache_clear()
