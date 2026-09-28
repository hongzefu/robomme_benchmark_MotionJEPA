"""正式候选逐条取值检查的离线反例；不执行仿真。"""
import json

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "injection-dev" / "site"))
import site_io  # noqa: E402
import v6_candidate_values as check  # noqa: E402
import v6_tier_monotone as tiers  # noqa: E402
from tests.lightweight.test_v6_tier_monotone import _write_reset_drafts  # noqa: E402


def build_draw_header(run_id, document, tasks, difficulty, seed_rule):
    """旧 v4_specs.build_draw_header 的最小替身（drafts header 形态；源码指纹用固定占位）。"""
    header = {"record": "header", "schema": "v4-drafts/1", "run_id": run_id, "difficulty": difficulty,
              "sampling_config": {t: {"decision": document["tasks"][t]["decision"], "native": document["tasks"][t]["native"]}
                                  for t in tasks},
              "source_fingerprint": {"files": 0, "sha256": "fixture"}, "runtime": dict(site_io.RUNTIME),
              "seed_rule": dict(seed_rule), "recovery_rule": {"rule": "V4 全部不开 fail recover（用户 2026-09-22）"},
              "identity_source": "formula", "tasks": tasks}
    header["sampling_config_sha256"] = site_io._digest(header["sampling_config"])
    return header


def candidates(tmp_path):
    paths = _write_reset_drafts(tmp_path, samples=10)
    document = site_io.packaged_sampling_document()
    for path in paths:
        records = [json.loads(line) for line in path.read_text().splitlines()]
        old = records[0]
        records[0] = build_draw_header(old["run_id"], document, old["tasks"], old["difficulty"], old["seed_rule"])
        for row in records[1:]:
            if row["task"] == "ButtonUnmask":
                row["spec"]["objects"]["distractors"]["placed"] = document["tasks"]["ButtonUnmask"]["decision"][old["difficulty"]]["distractor"]["count"]
                row["spec_sha256"] = tiers._canonical_sha256(row["spec"])
        path.write_text("\n".join(json.dumps(row) for row in records) + "\n")
    return paths


def rewrite(path, mutate):
    records = [json.loads(line) for line in path.read_text().splitlines()]
    mutate(records)
    path.write_text("\n".join(json.dumps(row) for row in records) + "\n")


def test_complete_candidates_pass(tmp_path):
    report = check.check_candidates(candidates(tmp_path))
    assert report["verdict"] == "PASS", report
    assert report["candidates"] == 520


@pytest.mark.parametrize("mode", ["duplicate", "missing", "sha", "source", "config", "requested", "value"])
def test_counterexamples_fail(tmp_path, mode):
    paths = candidates(tmp_path)
    def mutate(rows):
        if mode == "duplicate":
            rows.append(rows[1])
        elif mode == "missing":
            rows.pop(1)
        elif mode == "sha":
            rows[1]["spec_sha256"] = "0" * 64
        elif mode == "source":
            rows[0]["source_fingerprint"]["sha256"] = "0" * 64
        elif mode == "config":
            rows[0]["sampling_config"]["BinFill"]["decision"]["configs"]["xhard1"]["put_in_numbers"] = [1, 99]
            rows[0]["sampling_config_sha256"] = tiers._canonical_sha256(rows[0]["sampling_config"])
        else:
            row = next(row for row in rows[1:] if row["task"] == "VideoUnmask")
            if mode == "requested":
                row["spec"]["objects"]["distractors"] = {"requested": 8}
            else:
                row["spec"]["objects"]["n_picks"] = 999
            row["spec_sha256"] = tiers._canonical_sha256(row["spec"])
    rewrite(paths[0], mutate)
    assert check.check_candidates(paths)["verdict"] == "FAIL"


def test_failed_attempt_is_counted(tmp_path):
    paths = candidates(tmp_path)
    def mutate(rows):
        row = dict(rows[1])
        row.update(attempt=1, seed=row["seed"] + 1, reset_ok=False, spec=None, spec_sha256=None)
        rows.append(row)
    rewrite(paths[0], mutate)
    report = check.check_candidates(paths)
    assert report["verdict"] == "PASS"
    assert sum(c["reset_failures"] for c in report["cells"].values()) == 1
