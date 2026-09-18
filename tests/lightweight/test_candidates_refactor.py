"""候选封套与真实生成路径的回归；不启动环境，也不覆盖环境行为。"""
from __future__ import annotations

import copy
import io
import json
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.injection.candidates import __main__ as entry
from scripts.injection.candidates.contract import load_contract
from scripts.injection.candidates.io import (
    CandidateError, canonical_json, identity_sha256, load_candidates,
    project_spec, record_sha256, validate_candidates, write_candidates,
)
from scripts.injection.candidates.screen import ObservationCollector
from scripts.injection.candidates.specs import build_group
from tests._shared.frozen_injection import load as frozen_load
legacy_build_group = frozen_load("specs").build_group
legacy_load_contract = frozen_load("contract").load_contract

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "scripts/configs/newtask-v2"


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    root = tmp_path_factory.mktemp("candidates")
    logs = root / "candidates/logs"
    logs.mkdir(parents=True)
    args = Namespace(run_id="candidate-test", sampling_config=str(CONFIG / "native_sampling.json"),
                     contract=str(CONFIG / "injection_contract_v3.json"),
                     delivery_config=str(CONFIG / "delivery_400.json"), seed=20260909,
                     purpose="smoke", groups=["RouteStick/easy"], blocks=2, reconstruct_run=None)
    assert entry.generate(args, root, root / "candidates", logs) == 0
    return load_candidates(root / "candidates/candidates.jsonl", repo_root=ROOT)


def test_end_to_end_and_role_rewrite(frozen, tmp_path):
    header, rows = copy.deepcopy(frozen)
    assert len(rows) == 200
    assert sum(r["split"] == "test" for r in rows) == 85
    previous = [canonical_json(project_spec(row)) for row in rows]
    rows[0]["role"] = "primary"
    rows[115]["role"] = "spare"
    header["roles"] = {"primary": 1, "spare": 1, "pending": 198}
    assert identity_sha256(header, rows) == header["identity_sha256"]
    path = tmp_path / "candidates.jsonl"
    write_candidates(path, header, rows)
    loaded_header, loaded = load_candidates(path, repo_root=ROOT)
    assert loaded_header == header
    assert [canonical_json(project_spec(row)) for row in loaded] == previous
    with pytest.raises(FileExistsError):
        write_candidates(path, header, rows)


@pytest.mark.parametrize("change", ["snapshot", "seed", "key", "split", "unknown", "spec", "collision", "missing", "duplicate"])
def test_tampering_rejected(frozen, change):
    header, rows = copy.deepcopy(frozen)
    if change == "snapshot":
        header["sampling_config"]["sources"]["RouteStick"]["sha256"] = "bad"
    elif change == "seed":
        rows[0]["seed"] += 1
    elif change == "key":
        rows[0]["episode"] = 1
    elif change == "split":
        rows[0]["split"] = "test"
    elif change == "unknown":
        rows[0]["ignored"] = True
    elif change == "spec":
        rows[0]["spec"]["unexpected"] = True
    elif change == "collision":
        rows[0]["spec"]["collision"] = {}
    elif change == "missing":
        rows.pop()
        header["candidates"] -= 1
    else:
        rows[-1] = rows[0]
    with pytest.raises(CandidateError):
        validate_candidates(header, rows)


def test_projection_deep_copy(frozen):
    _, rows = frozen
    projected = project_spec(rows[0])
    projected["layout"]["rotation_deg"] += 1
    assert projected != rows[0]["spec"]
    assert record_sha256(rows[0]["spec"]) == rows[0]["spec_sha256"]


def test_source_fingerprint_checked_even_after_resealing(frozen):
    header, rows = copy.deepcopy(frozen)
    header["sampling_config"]["sources"]["RouteStick"]["sha256"] = "0" * 64
    header["identity_sha256"] = identity_sha256(header, rows)
    with pytest.raises(CandidateError, match="源码指纹"):
        validate_candidates(header, rows, repo_root=ROOT)


def test_run_id_and_frozen_state_guard(tmp_path, monkeypatch):
    for value in ("..", "../escape", "/absolute", "hidden/child"):
        with pytest.raises(CandidateError):
            entry.checked_root(value)
    stage = tmp_path / "candidates/logs"
    stage.mkdir(parents=True)
    (stage / "plan_meta.json").write_text('{"state":"running"}')
    monkeypatch.setattr(entry, "checked_root", lambda _: tmp_path)
    with pytest.raises(CandidateError, match="禁止覆盖"):
        entry.execute(Namespace(run_id="existing"))


@pytest.mark.parametrize("task", ["BinFill", "RouteStick", "VideoRepick", "VideoUnmaskSwap"])
def test_observation_matches_old_random_stream(task):
    sampling = json.loads((CONFIG / "native_sampling.json").read_text())
    path = CONFIG / "injection_contract_v3.json"
    expected = legacy_build_group(task, "easy", sampling, legacy_load_contract(path))
    stream = io.StringIO()
    observer = ObservationCollector(stream)
    actual = build_group(task, "easy", sampling, load_contract(path), observer=observer)
    assert canonical_json(actual.as_document("test")) == canonical_json(expected.as_document("test"))
    assert actual.stats == expected.stats
    observer.check_stats(actual)
    screens = [observer.screening(record, "generated") for record in actual.episodes]
    if task == "RouteStick":
        assert all(row["candidates_tried"] is None for row in screens)
    else:
        assert sum(row["candidates_tried"] for row in screens) == actual.stats["candidates_tried"]
        rejections = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert len(rejections) == sum(actual.stats[f"rejected_{r}"] for r in ("geometry", "contact", "numerical_boundary", "uncertified"))
        assert all(event["proposal"] and event["trial"] > 0 for event in rejections)


def test_duplicate_json_field_rejected(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"record":"header","record":"candidate"}\n')
    with pytest.raises(CandidateError, match="重复字段"):
        load_candidates(path)
