"""只读取已提交的轻量证据，复核完整对象动作冻结交付；不读 artifacts 或使用 GPU。"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2] / "docs/validation/newtask-v2/20260909-actions-v3"
LABELS = {"A1", "A2", "B", "C"}
PAIRS = {"A1-A2", "A1-B", "A1-C", "B-C"}
pytestmark = pytest.mark.lightweight


def read(name):
    return json.loads((ROOT / name).read_text())


def test_delivery_files_and_raw_parity_are_self_contained():
    bundle = read("bundle_manifest.json")
    assert bundle["files"]
    for name, expected in bundle["files"].items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    cases = {item["cell"] for item in read("cases.json")["cases"]}
    result = read("result.json")
    assert len(cases) == 15 and set(result["cells"]) == cases and result["passed"]
    runner = read("runner_report.json")
    assert len(runner["results"]) == 60 and not runner["failed"]
    assert all(item["ok"] and not item["skipped"] for item in runner["results"])
    execution = read("execution_records.json")
    assert set(execution) == cases and all(set(item) == LABELS for item in execution.values())
    for cell in execution.values():
        for item in cell.values():
            assert item["result"]["ok"] and item["result"]["attempt"] == 0
            assert item["result"]["bound"]["gpu"] == "0"
            assert item["parameters"]["workers"] == item["parameters"]["episodes"] == 1
    for cell in result["cells"].values():
        assert cell["status"] == "通过" and cell["rrt_fallback_count"] == {"A1": 0, "A2": 0}
        assert set(cell["paths"]) == LABELS and set(cell["comparisons"]) == PAIRS
        for field in ("evidence_ref", "h5_fingerprint_ref"):
            refs = {item[field] for item in cell["paths"].values()}
            assert len(refs) == 1
            ref = refs.pop()
            body = (ROOT / "evidence" / f"{ref}.json").read_bytes()
            assert hashlib.sha256(body).hexdigest()[:16] == ref
        assert all(item["h5"]["passed"] and item["evidence"]["passed"] for item in cell["comparisons"].values())
    assert read("observer_calibration.json")["passed"]


def test_delivery_actions_merges_and_continuous_workers():
    result = read("result.json")
    actions = read("action_bindings.json")
    merged = read("merged_comparison.json")
    assert set(actions) == set(merged) == set(result["cells"])
    for cell, entry in actions.items():
        assert entry["passed"] and set(entry["paths"]) == LABELS
        for label, action in entry["paths"].items():
            assert action == entry["paths"]["A1"]
            coverage = action["runtime_coverage"]
            assert coverage["both_rng_states_recorded"]
            assert coverage["rng_count"] == result["cells"][cell]["paths"][label]["sections"]["rng"]
        assert merged[cell]["passed"] and set(merged[cell]["differences"]) == PAIRS
        assert not any(merged[cell]["differences"].values())
        assert set(merged[cell]["fingerprints"]) == LABELS
        assert all(value == merged[cell]["fingerprints"]["A1"] for value in merged[cell]["fingerprints"].values())
    isolation = read("worker_isolation_complete.json")
    assert set(isolation) == {"S-baseline", "S-default", "S-config"}
    for item in isolation.values():
        execution = item["execution"]
        assert item["passed"] and execution["success_count"] == 3 and execution["exhausted_count"] == 0
        assert execution["same_worker"] and len(execution["worker_pids"]) == 1
        assert execution["class_config_hash_before"] == execution["class_config_hash_after"]
        assert execution["parent_config_hash_before"] == execution["parent_config_hash_after"]
        assert execution["worker_class_config_unchanged"]
        assert [entry["task"] for entry in execution["plan"]["order"]] == ["BinFill", "VideoRepick", "BinFill"]
        assert len(item["slots"]) == 3 and all(slot["passed"] and slot["cache_empty"] for slot in item["slots"].values())
        for slot in item["slots"].values():
            assert slot["h5_fingerprints"]["independent"] == slot["h5_fingerprints"]["continuous"]
            assert slot["evidence_digests"]["independent"] == slot["evidence_digests"]["continuous"]


def test_delivery_retry_all_tasks_and_every_reviewed_image():
    retry = read("retry_comparison.json")
    assert retry["passed"] and not any(retry["differences"].values())
    for run in retry["runs"].values():
        assert [item["seed"] for item in run["attempts"]] == [4000, 4001]
        assert [item["ok"] for item in run["attempts"]] == [False, True]
    all_tasks = read("all16_summary.json")
    assert all_tasks["requested_count"] == all_tasks["success_count"] == 16
    assert all_tasks["exhausted_count"] == 0 and len(set(all_tasks["parameters"]["tasks"])) == 16
    visual, index = read("visual_inspection.json"), read("keyframe_index.json")
    assert visual["passed"] and visual["cell_count"] == 15
    assert set(visual["cells"]) == set(index["cells"]) == set(read("result.json")["cells"])
    assert hashlib.sha256((ROOT / "keyframe_index.json").read_bytes()).hexdigest() == visual["keyframe_index_sha256"]
    assert visual["image_count"] == sum(len(cell["montages"]) for cell in index["cells"].values())
    for cell, images in index["cells"].items():
        assert images["status"] == "通过" and not images.get("not_rendered")
        mappings = images["event_record_mapping"]
        assert set(mappings) == {"A1", "B", "C"}
        assert all(item["unrecorded_events"] == mappings["A1"]["unrecorded_events"] for item in mappings.values())
        reviewed = visual["cells"][cell]["images"]
        assert set(images["montages"]) == set(reviewed)
        for frame, image in images["montages"].items():
            assert reviewed[frame]["passed"] and reviewed[frame]["montage_sha256"] == image["montage_sha256"]
            assert all(diff["max_abs"] == diff["nonzero_pixels"] == 0 for diff in image["difference"].values())


def test_offline_delivery_check_rejects_modified_report(tmp_path, monkeypatch):
    target = tmp_path / "package"
    shutil.copytree(ROOT, target)
    result = json.loads((target / "result.json").read_text())
    result["passed"] = False
    (target / "result.json").write_text(json.dumps(result))
    monkeypatch.setattr(sys.modules[__name__], "ROOT", target)
    with pytest.raises(AssertionError, match="result.json"):
        test_delivery_files_and_raw_parity_are_self_contained()
