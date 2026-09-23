#!/usr/bin/env python3
"""轻量测试：V4 规格封套（``scripts/parity/v4_specs.py``，计划 3.3②、3.4）。

纯 CPU、不起环境：用真实的 v4 采样快照与当前源码指纹拼一份合成 drafts，走 freeze → load。
覆盖 Codex 审计 #6/#7 要求的反例：
* 改 ``selected`` 身份散列不变；改任一规格值身份散列必变；
* 封存来源与当前磁盘不一致即拒绝冻结；已存在拒绝覆盖；字段多一个少一个都报错。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_specs.py -q
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
for extra in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.parity import v4_specs as V  # noqa: E402
from scripts.injection.candidates.io import canonical_json  # noqa: E402

TASKS = ["PatternLock", "RouteStick"]


def _drafts(tmp_path: Path, n: int = 7, mutate_header=None) -> Path:
    sampling = json.loads(V.DEFAULT_SAMPLING.read_text(encoding="utf-8"))
    header = {
        "record": "header", "schema": V.DRAFT_SCHEMA, "run_id": "t", "difficulty": "xhard",
        "sampling_config": {t: V.task_sampling(sampling, t) for t in TASKS},
        "source_fingerprint": V.source_fingerprint(), "runtime": dict(V.RUNTIME),
        "seed_rule": dict(V.SEED_RULE), "recovery_rule": dict(V.RECOVERY_RULE), "identity_source": "formula", "tasks": TASKS,
    }
    header["sampling_config_sha256"] = V.digest(header["sampling_config"])
    if mutate_header:
        mutate_header(header)
    rows = []
    for task in TASKS:
        # 第 1 条候选先失败一次再成功：episode 编号只算成功的
        rows.append({"record": "draft", "task": task, "difficulty": "xhard", "episode": 1, "attempt": 0,
                     "seed": V.seed_for(task, 1, 0), "reset_ok": False, "fail_class": "RuntimeError",
                     "error": "x", "spec": None, "spec_sha256": None, "wall_s": 1.0})
        for ep in range(n):
            attempt = 1 if ep == 1 else 0
            spec = {"spec_kind": "native-newvalue/1", "task": task, "objects": {"v": ep * 10}}
            rows.append({"record": "draft", "task": task, "difficulty": "xhard", "episode": ep,
                         "attempt": attempt, "seed": V.seed_for(task, ep, attempt), "reset_ok": True,
                         "fail_class": None, "error": None, "spec": spec, "spec_sha256": V.spec_sha256(spec),
                         "wall_s": 1.0})
    path = tmp_path / "drafts.jsonl"
    path.write_text("".join(canonical_json(r) + "\n" for r in [header, *rows]), encoding="utf-8")
    return path


def _freeze(tmp_path: Path, **kw) -> Path:
    out = tmp_path / "specs.jsonl"
    V.freeze(_drafts(tmp_path, **kw), V.DEFAULT_SAMPLING, out, candidates_per_env=10)
    return out


def _records(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_freeze_selects_0_3_6_and_reports_shortfall(tmp_path: Path) -> None:
    out = _freeze(tmp_path)
    header, sampling, specs = V.load_specs(out)
    assert sorted(specs) == [f"{t}/{e}" for t in TASKS for e in (0, 3, 6)]
    assert header["per_env"]["PatternLock"] == {"candidates": 7, "attempted": 8,
                                               "candidate_shortfall": 3, "selected": [0, 3, 6]}
    assert set(sampling) == set(TASKS)


def test_selected_does_not_change_identity_but_spec_does(tmp_path: Path) -> None:
    records = _records(_freeze(tmp_path))
    header, rows = records[0], records[1:]
    flipped = copy.deepcopy(rows)
    flipped[1]["selected"] = not flipped[1]["selected"]
    assert V.identity_sha256(header, flipped) == header["identity_sha256"]
    V.validate_specs(header, flipped)  # 只改选择仍然合法
    changed = copy.deepcopy(rows)
    changed[0]["spec"]["objects"]["v"] = 999
    changed[0]["spec_sha256"] = V.spec_sha256(changed[0]["spec"])  # 连散列一起改也逃不过身份散列
    assert V.identity_sha256(header, changed) != header["identity_sha256"]
    with pytest.raises(V.SpecsError):
        V.validate_specs(header, changed)


def test_tampered_spec_without_hash_update_rejected(tmp_path: Path) -> None:
    records = _records(_freeze(tmp_path))
    records[1]["spec"]["objects"]["v"] = 1
    with pytest.raises(V.SpecsError):
        V.validate_specs(records[0], records[1:])


def test_source_mismatch_refuses_freeze(tmp_path: Path) -> None:
    def bad_fingerprint(h):
        h["source_fingerprint"] = {"files": 0, "sha256": "0" * 64}
    with pytest.raises(V.SpecsError, match="source_fingerprint"):
        _freeze(tmp_path, mutate_header=bad_fingerprint)

    def bad_config(h):
        h["sampling_config"]["RouteStick"]["decision"]["demonstration_duration_policy"] = "changed"
        h["sampling_config_sha256"] = V.digest(h["sampling_config"])
    other = tmp_path / "b"
    other.mkdir()
    with pytest.raises(V.SpecsError, match="sampling_config"):
        _freeze(other, mutate_header=bad_config)


def test_refuse_overwrite_and_exact_keys(tmp_path: Path) -> None:
    out = _freeze(tmp_path)
    with pytest.raises(V.SpecsError, match="禁止覆盖"):
        V.freeze(tmp_path / "drafts.jsonl", V.DEFAULT_SAMPLING, out)
    records = _records(out)
    extra = copy.deepcopy(records)
    extra[1]["unexpected"] = 1
    with pytest.raises(V.SpecsError, match="字段集合"):
        V.validate_specs(extra[0], extra[1:])
    missing = copy.deepcopy(records)
    missing[0].pop("per_env")
    with pytest.raises(V.SpecsError, match="字段集合"):
        V.validate_specs(missing[0], missing[1:])


def test_seed_rule_disjoint_from_existing_layouts() -> None:
    from seed_layout import LAYOUTS, ALL_TASKS
    v4 = {V.seed_for(t, e, a) for t in ALL_TASKS for e in range(10) for a in range(30)}
    for layout in LAYOUTS.values():
        old = {layout.seed(t, e, a) for t in ALL_TASKS for e in range(100) for a in range(100)}
        assert not (v4 & old)


def test_v4_never_enables_recovery() -> None:
    """用户 2026-09-22 定：V4 全部不开 recover，抽签 kwargs 里不得出现 recover 开关。"""
    for episode in range(12):
        assert V.recovery_mode(episode) is None
        assert "robomme_failure_recovery" not in V.env_kwargs(V.seed_for("BinFill", episode, 0), episode)
    assert set(V.RECOVERY_RULE) == {"rule"}


def test_reselect_keeps_identity_and_follows_results(tmp_path: Path) -> None:
    """H4 递补后按实跑结果重标 selected：身份散列不变、原文件不改、只标成功局。"""
    out = _freeze(tmp_path)
    before = out.read_bytes()
    results = tmp_path / "results.jsonl"
    rows = [{"task": "PatternLock", "episode": e, "ok": e in (0, 4, 5)} for e in (0, 3, 6, 1, 2, 4, 5)]
    rows += [{"task": "RouteStick", "episode": e, "ok": True} for e in (0, 3, 6)]
    results.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    new = tmp_path / "specs.selected.jsonl"
    result = V.reselect(out, results, new)
    assert out.read_bytes() == before
    header, _, specs = V.load_specs(new)
    assert header["identity_sha256"] == V.load_specs(out)[0]["identity_sha256"]
    assert sorted(specs) == ["PatternLock/0", "PatternLock/4", "PatternLock/5",
                             "RouteStick/0", "RouteStick/3", "RouteStick/6"]
    assert result["per_env"]["PatternLock"] == [0, 4, 5]
    with pytest.raises(V.SpecsError, match="禁止覆盖"):
        V.reselect(out, results, new)
