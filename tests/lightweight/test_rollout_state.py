"""唯一结果归并、角色恢复与部分 scope 的反例测试。"""
import copy
import json
import tempfile
from pathlib import Path

import pytest

from scripts.injection.candidates.io import load_candidates, write_candidates
from scripts.injection.rollout.state import ROOT, RunStore, StateError, assign_roles, unique_rows, read_rows


@pytest.fixture
def store():
    directory = ROOT / "artifacts/test-tmp"
    directory.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="rollout-state-", dir=directory))
    header, candidates = load_candidates(ROOT / "artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl")
    header.pop("roles", None)
    for row in candidates:
        row.update(role="pending", error_type=None)
    write_candidates(root / "candidates/candidates.jsonl", header, candidates)
    return RunStore(root)


def record(candidate, kind="h5", ok=True):
    return {"kind": kind, "task": candidate["task"], "difficulty": candidate["difficulty"],
            "episode": candidate["episode"], "seed": candidate["seed"], "spec_sha256": candidate["spec_sha256"],
            "split": candidate["split"], "ok": ok, "error_type": None if ok else "测试失败",
            "h5_path": "/成品.h5" if kind == "h5" and ok else None,
            "h5_sha256": "1" * 64 if kind == "h5" and ok else None, "h5_bytes": 10 if kind == "h5" and ok else None,
            **({"outcome": "通过" if ok else "规划失败"} if kind == "reset" else {})}


def test_interrupted_candidate_rewrite_recovers_without_losing_results(store):
    with store.locked():
        _, candidates, _ = store.load()
        row = record(candidates[0])
        with pytest.raises(InterruptedError):
            store.publish([row], interrupt_after_results=True)
        with pytest.raises(StateError):
            store.audit()
        store.publish(read_rows(store.results_path))
        assert store.audit()["pending"] == 3399


def test_duplicate_table_and_conflicting_terminal_are_rejected(store):
    with store.locked():
        _, candidates, _ = store.load()
        row = record(candidates[0])
        with pytest.raises(StateError, match="重复"):
            unique_rows([row, copy.deepcopy(row)])
        store.merge([row])
        store.merge([copy.deepcopy(row)])
        changed = {**row, "h5_bytes": 20}
        with pytest.raises(StateError, match="冲突"):
            store.merge([changed])


def test_unused_only_after_full_reset_quota(store):
    header, candidates, _ = store.load()
    test = [r for r in candidates if r["task"] == "RouteStick" and r["difficulty"] == "easy" and r["split"] == "test"]
    rows = [record(r, "reset") for r in test[:1]]
    store.publish(rows, completed_groups=["RouteStick/easy"])
    assert store.audit()["unused"] == 0
    rows = [record(r, "reset") for r in test[:50]]
    store.publish(rows, completed_groups=["RouteStick/easy"])
    assert store.audit()["unused"] == 35
    previous = {r["episode"] for r in store.load()[2] if r["role"] == "primary"}
    store.publish(rows + [record(r, "reset", ok=(r["episode"] % 2 == 0)) for r in test[50:]])
    assert store.audit()["unused"] == 0
    assert {r["episode"] for r in store.load()[2] if r["role"] == "primary"} == previous


def test_partial_tail_never_becomes_terminal(store):
    path = store.logs / "attempt.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'{"ok":true}\n{"ok":')
    assert read_rows(path, incomplete_tail=True) == [{"ok": True}]
    assert path.read_bytes().endswith(b'{"ok":')
    assert path.with_suffix(".jsonl.interrupted.json").exists()


def test_wrong_split_or_reset_outcome_rejected(store):
    header, candidates, _ = store.load()
    row = record(candidates[0], "reset")
    with pytest.raises(StateError):
        assign_roles(header, candidates, [row])
    candidate = next(r for r in candidates if r["split"] == "test")
    row = record(candidate, "reset")
    row["outcome"] = "规划失败"
    with pytest.raises(StateError, match="冲突"):
        assign_roles(header, candidates, [row])
