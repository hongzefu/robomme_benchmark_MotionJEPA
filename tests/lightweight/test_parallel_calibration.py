"""并行校准的反例测试：不依赖仿真或 GPU。"""

import copy
import gzip
import json
from pathlib import Path
import sys

import h5py
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared import parallel_calibration as calibration
from tests._shared import parity_observer as observer

pytestmark = pytest.mark.lightweight


def test_fixed_matrix_and_commands(tmp_path):
    cases = calibration.cases()
    assert len(cases) == len({calibration.key(case) for case in cases}) == 16
    assert {case["episode"] for case in cases} == {0, 1, 2, 3}
    assert not any(case["task"] == "VideoRepick" and case["difficulty"] == "hard" for case in cases)
    assert all(case["attempt"] == 0 for case in cases)
    for mode, (gpus, workers) in calibration.MODES.items():
        for task, difficulty in calibration.TASKS:
            command = calibration.command_for(tmp_path, mode, task, difficulty)
            assert command[:4] == ["uv", "run", "--no-sync", "python"]
            for option, value in (("--gpus", ",".join(gpus)), ("--workers", str(workers)),
                                  ("--episodes", "4"), ("--max-attempts", "1"),
                                  ("--episode-start", "0"), ("--difficulty", "010" if difficulty == "medium" else "001")):
                assert command[command.index(option) + 1] == value


def test_association_ignores_completion_order_and_rejects_duplicates():
    expected = calibration.cases()
    indexed, errors = calibration.associate(list(reversed(expected)), expected)
    assert not errors and len(indexed) == 16
    _, errors = calibration.associate(expected + [expected[0]], expected)
    assert errors
    _, errors = calibration.associate(expected[1:] + [{"task": "未知任务"}], expected)
    assert len(errors) >= 2


def windows():
    return [{"episode": index, "bound": {"gpu": str(index // 2), "pid": 100 + index,
             "pci": f"0000:0{index // 2 + 1}:00.0", "can_render": True},
             "timing": {"pid": 100 + index, "reset_ns": 10, "first_step_ns": 20 + index,
                        "last_step_ns": 80 + index, "close_ns": 100}} for index in range(4)]


GPU_MAP = {"0": "00000000:01:00.0", "1": "00000000:02:00.0"}


def test_dual_gpu_requires_four_distinct_overlapping_workers():
    rows = windows()
    assert calibration.concurrency("P01", rows, GPU_MAP)["passed"]
    rows[1]["bound"]["pid"] = rows[1]["timing"]["pid"] = rows[0]["bound"]["pid"]
    assert not calibration.concurrency("P01", rows, GPU_MAP)["passed"]


@pytest.mark.parametrize("mutation", [
    lambda rows: rows[0]["bound"].update(pci="0000:02:00.0"),
    lambda rows: rows[0]["timing"].update(close_ns=None),
    lambda rows: rows[0]["timing"].update(pid=999),
    lambda rows: rows[0]["timing"].update(first_step_ns=101),
    lambda rows: rows[0]["bound"].update(error="初始化失败"),
])
def test_bad_binding_or_timing_is_rejected(mutation):
    rows = windows()
    mutation(rows)
    assert not calibration.concurrency("P01", rows, GPU_MAP)["passed"]


def test_encoding_overlap_is_not_simulation_overlap():
    rows = windows()
    for index, row in enumerate(rows):
        row["timing"].update(first_step_ns=20 + index * 100, last_step_ns=70 + index * 100, close_ns=1000)
    assert not calibration.concurrency("P01", rows, GPU_MAP)["passed"]
    for row in rows:
        row["bound"].update(gpu="0", pci=GPU_MAP["0"])
    assert calibration.concurrency("S0a", rows, GPU_MAP)["passed"]
    assert not calibration.concurrency("P0", rows, GPU_MAP)["passed"]


def test_single_gpu_parallel_and_serial_are_distinguished():
    rows = windows()
    for row in rows:
        row["bound"].update(gpu="0", pci=GPU_MAP["0"])
    assert calibration.concurrency("P0", rows, GPU_MAP)["passed"]
    assert not calibration.concurrency("S0a", rows, GPU_MAP)["passed"]


def payload():
    return {"task": "BinFill", "seed": 4000, "difficulty": "hard", "evidence_version": 3,
            "rng": [{"value": 1}], "rng_total": 1, "rng_recorded": 1,
            "events": [{"swap": [0, 1]}], "event_count": 1,
            "boundaries": [{"stage": "reset"}], "steps": [{"actor": 0}], "step_count": 1,
            "recordings": [{"step": 0}], "rrt_fallback_count": 0,
            "initial_obs": {"value": {"hash": "abc"}, "rgb": {"front_rgb": {}, "wrist_rgb": {}}}}


def test_missing_observer_fields_and_truncated_rng_are_rejected():
    good = payload()
    assert not calibration.validate_evidence(good, calibration.cases()[0])
    for field in ("events", "rrt_fallback_count", "initial_obs", "rng_total"):
        bad = copy.deepcopy(good)
        bad.pop(field)
        assert calibration.validate_evidence(bad, calibration.cases()[0])


def pair_files(tmp_path):
    rows = []
    for name in ("left", "right"):
        h5 = tmp_path / f"{name}.h5"
        with h5py.File(h5, "w") as handle:
            handle.create_dataset("values", data=[1.0, 2.0])
        evidence = tmp_path / f"{name}.json.gz"
        with gzip.open(evidence, "wt") as handle:
            json.dump(payload(), handle)
        rows.append({"valid": True, "h5_path": str(h5), "evidence_path": str(evidence), "rrt_fallback_count": 0})
    return rows


def test_one_h5_value_change_reports_first_difference(tmp_path):
    left, right = pair_files(tmp_path)
    assert calibration.compare_pair(left, right)["passed"]
    with h5py.File(right["h5_path"], "r+") as handle:
        handle["values"][1] = 2.5
    result = calibration.compare_pair(left, right)
    assert not result["passed"] and "values" in result["h5_differences"][0]


def test_swap_identity_change_and_fallback_are_rejected(tmp_path):
    left, right = pair_files(tmp_path)
    changed = payload()
    changed["events"][0]["swap"] = [0, 2]
    with gzip.open(right["evidence_path"], "wt") as handle:
        json.dump(changed, handle)
    result = calibration.compare_pair(left, right)
    assert not result["passed"]
    assert result["evidence"]["sections"]["events"]["first_divergence"]["index"] == 0
    left["rrt_fallback_count"] = 1
    assert not calibration.compare_pair(left, left)["passed"]
    left["valid"] = False
    assert not calibration.compare_pair(left, right)["passed"]


def test_mode_cannot_pass_with_missing_case_or_failed_reference():
    reference = {str(index): {"passed": True} for index in range(16)}
    comparisons = {mode: copy.deepcopy(reference) for mode in ("S1", "P0", "P01")}
    batches = {mode: {task: {"passed": True} for task, _ in calibration.TASKS} for mode in comparisons}
    assert all(result["passed"] for result in calibration.decide(reference, comparisons, batches).values())
    reference["0"]["passed"] = False
    assert not any(result["passed"] for result in calibration.decide(reference, comparisons, batches).values())
    reference["0"]["passed"] = True
    comparisons["P01"].pop("0")
    assert not calibration.decide(reference, comparisons, batches)["P01"]["passed"]


def test_timeout_is_recorded_and_process_group_terminated(tmp_path, monkeypatch):
    monkeypatch.setattr(calibration, "resource_sample", lambda pgid: {"pgid": pgid})
    result = calibration.execute(["bash", "-c", "sleep 30 & wait"], dict(__import__("os").environ), tmp_path / "timeout", 0.2)
    assert result["timed_out"] and result["returncode"] != 0
    assert result["elapsed_s"] < 8


def test_timing_sidecar_does_not_change_comparison_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("PARITY_TIMING", "1")
    monkeypatch.setitem(observer._state, "root", str(tmp_path))
    monkeypatch.setitem(observer._state, "label", "test")
    monkeypatch.setitem(observer._state, "sequence", 0)
    episode = observer._EpisodeEvidence("BinFill", 4000, "hard")
    monkeypatch.setitem(observer._state, "episode", episode)
    before = copy.deepcopy(episode.payload())
    episode.timing.update(reset_ns=1, first_step_ns=2, last_step_ns=3, close_ns=4)
    observer._write_timing(episode)
    assert episode.payload() == before
    files = list(tmp_path.rglob("*.timing.json"))
    assert len(files) == 1 and json.loads(files[0].read_text())["close_ns"] == 4
    monkeypatch.delenv("PARITY_TIMING")
    assert observer._EpisodeEvidence("BinFill", 4000, "hard").timing is None


def test_failed_episode_does_not_hide_other_successful_comparisons(tmp_path):
    root = tmp_path
    directory = root / "runs/S0a/BinFill"
    calibration.write_json(root / "logs/S0a/BinFill/execution.json", {"returncode": 1, "timed_out": False})
    calibration.write_json(directory / "run_parameters.json", {
        "tasks": ["BinFill"], "episodes": 4, "episode_start": 0, "workers": 1,
        "gpus": ["0"], "seed_layout": "train", "difficulty_ratio": "001",
        "max_attempts": 1, "max_tasks_per_child": 8, "limit_threads": True, "affinity": "none"})
    snapshot = calibration.read_json(calibration.CONFIG)
    calibration.write_json(directory / "sampling_config_used.json", {
        task: {block: snapshot[block][task] for block in ("parameters", "positions")}
        for task, _ in calibration.TASKS})
    records = []
    for case in calibration.cases()[:4]:
        index = case["episode"]
        row = {**case, "ok": index != 3, "bound": {"gpu": "0", "pid": 100,
               "pci": GPU_MAP["0"], "can_render": True}}
        if index != 3:
            h5 = directory / "hdf5_files" / f"BinFill_ep{index}_seed{case['seed']}.h5"
            h5.parent.mkdir(exist_ok=True)
            with h5py.File(h5, "w") as handle:
                handle.create_dataset(f"episode_{index}/timestep_0/info/is_completed", data=True)
            row["h5_path"] = str(h5)
        evidence = root / "evidence/BinFill/S0a" / f"BinFill_seed{case['seed']}"
        evidence.mkdir(parents=True)
        data = payload()
        data.update(task=case["task"], seed=case["seed"], difficulty=case["difficulty"], pid=100)
        with gzip.open(evidence / "pid100-00.json.gz", "wt") as handle:
            json.dump(data, handle)
        calibration.write_json(evidence / "pid100-00.timing.json", {
            "task": case["task"], "seed": case["seed"], "difficulty": case["difficulty"], "pid": 100,
            "reset_ns": 1 + index * 100, "first_step_ns": 10 + index * 100,
            "last_step_ns": 20 + index * 100, "close_ns": 30 + index * 100})
        records.append(row)
    (directory / "episode_results.jsonl").write_text("\n".join(json.dumps(row) for row in records))
    result = calibration.collect_batch(root, "S0a", "BinFill", GPU_MAP, snapshot)
    assert not result["passed"]
    assert [row["valid"] for row in result["rows"]] == [True, True, True, False]
    assert result["concurrency"]["passed"]
    assert result["rows"][3]["timing"]["close_ns"] == 330
    assert "h5_path" not in result["rows"][3]
    calibration.write_json(evidence / "pid100-01.timing.json", {})
    duplicate = calibration.collect_batch(root, "S0a", "BinFill", GPU_MAP, snapshot)
    assert not duplicate["concurrency"]["passed"]
    assert any("应恰好一份" in error for error in duplicate["rows"][3]["errors"])


def test_resource_summary_uses_observed_maximum_and_keeps_errors(tmp_path):
    path = tmp_path / "resources.jsonl"
    samples = [{"processes": [{"pid": 1, "rss_kib": 10}, {"pid": 2, "rss_kib": 20}],
                "gpus": [{"gpu": "0", "used_mib": "50"}]},
               {"processes": [{"pid": 1, "rss_kib": 25}],
                "gpus": [{"gpu": "0", "used_mib": "60"}], "error": "采样缺口"}]
    path.write_text("\n".join(json.dumps(row) for row in samples))
    result = calibration.resource_summary(path)
    assert result["sample_count"] == 2
    assert result["max_process_group_rss_kib"] == 30
    assert result["max_gpu_used_mib"] == {"0": 60}
    assert result["errors"] == ["采样缺口"]


def test_identical_failure_is_only_a_diagnostic():
    indexed = {mode: {calibration.key(case): {**case, "ok": True} for case in calibration.cases()} for mode in calibration.MODES}
    identity = calibration.key(calibration.cases()[3])
    for rows in indexed.values():
        rows[identity].update(ok=False, failure_class="task", error_type="DatasetGenerationError", error="环境失败", rrt_fallback_count=0)
    result = calibration.failure_diagnostics(indexed)
    assert len(result) == 1 and next(iter(result.values()))["same_failure_signature"]
    indexed["P01"][identity]["error"] = "另一错误"
    assert not next(iter(calibration.failure_diagnostics(indexed).values()))["same_failure_signature"]
