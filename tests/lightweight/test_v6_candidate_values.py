"""正式候选逐条取值检查的离线反例；不执行仿真。"""
import json

import pytest

from scripts.parity import v6_candidate_values as check
from scripts.parity import v6_tier_monotone as tiers
from scripts.parity.v4_specs import build_draw_header
from tests.lightweight.test_v6_tier_monotone import _write_reset_drafts


def candidates(tmp_path):
    paths = _write_reset_drafts(tmp_path, samples=10)
    document = json.loads(check.DEFAULT_CONFIG.read_text())
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
