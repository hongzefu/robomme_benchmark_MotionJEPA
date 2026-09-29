#!/usr/bin/env python3
"""轻量测试：V6 档位单调性检查器（scripts/parity/v6_tier_monotone.py，计划 S2 / TIER_MONOTONE）。

    uv run --no-sync python -m pytest tests/lightweight/test_v6_tier_monotone.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
sys.path.insert(0, str(REPO_ROOT / "scripts" / "injection-dev"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "injection-dev" / "site"))
import v6_tier_monotone as M  # noqa: E402


def _midpoint(value):
    if isinstance(value, (list, tuple)):
        return int((value[0] + value[1]) // 2)
    return int(value)


def _sample_spec(task, tier, episode, seed, overrides=None):
    if task not in M.PLAN_TIERS:
        identity = {"task": task, "difficulty": tier, "episode": episode, "seed": seed,
                    "recovery_mode": None}
        return {"task": task, "identity": identity, "spec_kind": "native-newvalue/2",
                "objects": {}, "actions": {}}
    overrides = overrides or {}
    dims = {
        key: _midpoint(value)
        for key, value in M.PLAN_TIERS[task][tier].items()
    }
    for dim in dims:
        override = overrides.get((task, tier, dim))
        if override is not None:
            dims[dim] = int(override[episode])
    objects, actions = {}, {}
    if task == "BinFill":
        objects["target_numbers"] = [dims["put_in"]]
    elif task in ("PickXtimes", "SwingXtimes"):
        objects.update(num_repeats=dims["times" if task == "PickXtimes" else "rounds"],
                       distractor_count={"actual": dims["distractors"], "requested": dims["distractors"]})
    elif task == "PickHighlight":
        objects.update(highlight_count=dims["pick"], n_cubes_spawned=dims["total"])
    elif task in ("VideoUnmask", "ButtonUnmask"):
        objects.update(distractors={"placed": dims["distractors"]}, n_picks=dims["pick"])
    elif task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        objects.update(n_swaps=dims["swap"], n_picks=dims["pick"],
                       distractors={"placed": dims["outer_distractors"]})
    elif task == "VideoRepick":
        objects.update(cube_count={"actual": dims["cubes"]}, n_swaps=dims["swap"],
                       num_repeats=dims["repick"])
    elif task == "PatternLock":
        actions["path_nodes"] = list(range(dims["nodes"]))
    elif task == "RouteStick":
        objects["L"] = dims["segments"]
    elif task in ("VideoPlaceButton", "VideoPlaceOrder"):
        actions["target_placement_count"] = dims["placements"]
    identity = {"task": task, "difficulty": tier, "episode": episode, "seed": seed,
                "recovery_mode": None}
    return {"task": task, "identity": identity, "spec_kind": "native-newvalue/2",
            "objects": objects, "actions": actions}


def _write_reset_drafts(tmp_path, samples=2, missing=None, overrides=None, bad_spec_hash=None):
    from seed_layout import env_code

    tmp_path.mkdir(parents=True, exist_ok=True)
    configs = {task: {"decision": {tier: {} for tier in M.NEWVALUE_TIERS}, "native": {}}
               for task in M.GRADIENT_ENVS}
    paths = []
    for tier in M.NEWVALUE_TIERS:
        tasks = list(M.GRADIENT_ENVS)
        if tier == "xhard4":
            tasks.extend(sorted(M.XHARD4_EXTRA_TASKS))
        task_configs = {task: configs.get(task, {"decision": {"xhard4": {}}, "native": {}})
                        for task in tasks}
        header = {
            "record": "header", "schema": "v4-drafts/1", "run_id": f"test-{tier}",
            "difficulty": tier, "sampling_config": task_configs,
            "sampling_config_sha256": M._canonical_sha256(task_configs),
            "source_fingerprint": {"files": 1, "sha256": "fixture"},
            "runtime": M.V6_RUNTIME,
            "seed_rule": {**M.SEED_RULE_SHAPE, "offset": M.V6_SEED_OFFSETS[tier]},
            "recovery_rule": {"rule": "fixture"}, "identity_source": "formula",
            "tasks": tasks,
        }
        rows = []
        for task in tasks:
            for episode in range(samples):
                seed = M.V6_SEED_OFFSETS[tier] + env_code(task) * 100_000 + episode * 100
                if missing == (task, tier, episode):
                    rows.append({"record": "draft", "task": task, "difficulty": tier,
                                 "episode": episode, "attempt": 0, "seed": seed,
                                 "reset_ok": False, "fail_class": "ResetError", "error": "fixture",
                                 "spec": None, "spec_sha256": None, "wall_s": 0.1})
                    continue
                spec = _sample_spec(task, tier, episode, seed, overrides)
                spec_sha = M._canonical_sha256(spec)
                if bad_spec_hash == (task, tier, episode):
                    spec_sha = "0" * 64
                rows.append({"record": "draft", "task": task, "difficulty": tier,
                             "episode": episode, "attempt": 0, "seed": seed,
                             "reset_ok": True, "fail_class": None, "error": None,
                             "spec": spec, "spec_sha256": spec_sha, "wall_s": 0.1})
        path = tmp_path / f"{tier}.drafts.jsonl"
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in [header, *rows]) + "\n",
                        encoding="utf-8")
        paths.append(path)
    return paths


def test_value_mean_forms() -> None:
    assert M.value_mean(3) == 3.0
    assert M.value_mean([4, 7]) == 5.5
    assert M.value_mean({"samples": [1, 2, 3, 6]}) == 3.0
    assert M.value_interval([4, 7]) == (4.0, 7.0)
    assert M.value_interval({"samples": [2, 4, 6]}) == (2.0, 6.0)
    assert M.value_mean(None) is None
    with pytest.raises(ValueError):
        M.value_mean([5, 4])


def test_chain_detects_decrease_and_flat_step() -> None:
    tiers = {"hard": {"a": 1, "b": 1}, "xhard1": {"a": 2, "b": 1}, "xhard2": {"a": 2, "b": 1},
             "xhard3": {"a": 1.5, "b": 3}, "xhard4": {"a": 3, "b": 3}}
    result = M.check_chain("X", tiers)
    kinds = {(v["step"], v["kind"], v["dim"]) for v in result["violations"]}
    assert ("xhard1->xhard2", "flat_step", None) in kinds
    assert ("xhard2->xhard3", "decrease", "a") in kinds
    assert len(kinds) == 2


def test_none_dimension_skipped() -> None:
    tiers = {"hard": {"cubes": None, "swap": 0}, "xhard1": {"cubes": 4, "swap": 1}}
    assert M.check_chain("VR", tiers)["violations"] == []


def test_overlap_is_rejected_between_newvalue_tiers() -> None:
    tiers = {"hard": {"x": [1, 2]}, "xhard1": {"x": [3, 4]}, "xhard2": {"x": [4, 5]},
             "xhard3": {"x": [6, 7]}, "xhard4": {"x": [8, 9]}}
    result = M.check_chain("X", tiers)
    assert [(v["step"], v["kind"]) for v in result["violations"]] == [("xhard1->xhard2", "overlap")]


def test_check_all_rejects_missing_tiers() -> None:
    table = {env: dict(tiers) for env, tiers in M.PLAN_TIERS.items()}
    del table["VideoPlaceButton"]["xhard3"]
    result = M.check_all(table)
    assert any(v["env"] == "VideoPlaceButton" and v["kind"] == "missing_tier"
               and v["tier"] == "xhard3" for v in result["violations"])


def test_final_plan_table_passes() -> None:
    """主仓 V6 定稿表的全部 13 环境与四个新值档均应齐全、递增且区间互斥。"""
    result = M.check_all(M.PLAN_TIERS)
    assert len(result["envs"]) == 13
    assert result["violations"] == []
    assert M.format_report(result, label="TIER_PLAN_TABLE")[-1] == "TIER_PLAN_TABLE=PASS envs=13 violations=0"


@pytest.mark.parametrize("tier,count", [("xhard1", 8), ("xhard2", 10)])
def test_button_unmask_plan_matches_approved_snapshot(tier, count) -> None:
    """递增检查挡不住错抄值，须逐档核对批准定值与冻结配置。"""
    # v7 换包后包内 header 已是 v7 定值；v6 批准定值改读冻结快照 scripts/configs/newtask-v6/v6-sampling-frozen.json
    frozen = json.loads((REPO_ROOT / "scripts/configs/newtask-v6/v6-sampling-frozen.json").read_text(encoding="utf-8"))
    document = {"tasks": frozen["sampling_config"]["xhard4"]}
    assert document["tasks"]["ButtonUnmask"]["decision"][tier]["distractor"]["count"] == count
    assert M.PLAN_TIERS["ButtonUnmask"][tier]["distractors"] == count


def test_dims_from_xhard_decision_vp() -> None:
    vpb = {"xhard3": {"demo_object_count": 2, "demo_return_policy": "return_to_origin",
                       "extra_place_before": 1, "extra_place_after": 0}}
    assert M.dims_from_xhard_decision("VideoPlaceButton", vpb, "xhard3") == {"placements": 5}
    vpo = {"xhard1": {"demo_object_count": 2, "demo_return_policy": "return_to_origin",
                       "visit_counts": [2, 3]}}
    assert M.dims_from_xhard_decision("VideoPlaceOrder", vpo, "xhard1") == {"placements": 5}


def test_tiers_from_vp_decisions_uses_target_visits_only() -> None:
    vpb = {
        "xhard1": {"demo_object_count": 1, "extra_place_before": 0, "extra_place_after": 1},
        "xhard2": {"demo_object_count": 1, "extra_place_before": 1, "extra_place_after": 1},
        "xhard3": {"demo_object_count": 2, "extra_place_before": 1, "extra_place_after": 0},
        "xhard4": {"demo_object_count": 2, "extra_place_before": 1, "extra_place_after": 1},
    }
    vpo = {
        "xhard1": {"visit_counts": [2, 3]}, "xhard2": {"visit_counts": [3, 3]},
        "xhard3": {"visit_counts": [3, 4]}, "xhard4": {"visit_counts": [4, 4]},
    }
    vpb_result = M.tiers_from_decisions("VideoPlaceButton", vpb)
    vpo_result = M.tiers_from_decisions("VideoPlaceOrder", vpo)
    assert [vpb_result[tier]["placements"] for tier in M.NEWVALUE_TIERS] == [3, 4, 5, 6]
    assert [vpo_result[tier]["placements"] for tier in M.NEWVALUE_TIERS] == [5, 6, 7, 8]
    with pytest.raises(ValueError, match="缺少新值档 xhard4"):
        M.tiers_from_decisions("VideoPlaceButton", {key: value for key, value in vpb.items()
                                                     if key != "xhard4"})


def test_v4_specs_reset_drafts_require_all_13_by_4_cells(tmp_path) -> None:
    paths = _write_reset_drafts(tmp_path, samples=2)
    report = M.check_reset_drafts(paths, samples=2)
    assert report["expected_cells"] == 13 * 4
    assert report["covered_cells"] == 13 * 4
    assert report["check"]["verdict"] == "PASS"
    assert report["check"]["violations"] == []
    assert report["sample_source"] == "v4_specs draw/freeze EpisodeSpec"
    assert report["xhard4_non_gradient_validation"] == {
        task: {"valid_success_specs": 2, "reset_failures": 0}
        for task in sorted(M.XHARD4_EXTRA_TASKS)
    }


def test_xhard4_extra_tasks_validate_specs_but_do_not_affect_coverage(tmp_path) -> None:
    extra_task = sorted(M.XHARD4_EXTRA_TASKS)[0]
    paths = _write_reset_drafts(tmp_path, samples=2, missing=(extra_task, "xhard4", 1))
    report = M.check_reset_drafts(paths, samples=2)
    assert report["covered_cells"] == report["expected_cells"] == 52
    assert report["xhard4_non_gradient_validation"][extra_task] == {
        "valid_success_specs": 1, "reset_failures": 1,
    }
    assert report["check"]["verdict"] == "PASS"


def test_reset_all_cli_writes_measured_gate_report(tmp_path, monkeypatch, capsys) -> None:
    paths = _write_reset_drafts(tmp_path, samples=2)
    monkeypatch.setattr(M, "REPO_ROOT", tmp_path)
    output = tmp_path / "report.json"
    argv = ["--reset-all"]
    for path in paths:
        argv.extend(("--drafts", str(path)))
    argv.extend(("--samples", "2", "--out", str(output)))
    assert M.main(argv) == 0
    assert "TIER_MONOTONE=PASS envs=13 violations=0" in capsys.readouterr().out
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["expected_cells"] == saved["covered_cells"] == 52


def test_v4_specs_reset_drafts_report_cell_shortfall(tmp_path) -> None:
    missing = ("RouteStick", "xhard2", 1)
    paths = _write_reset_drafts(tmp_path, samples=2, missing=missing)
    report = M.check_reset_drafts(paths, samples=2)
    cell = report["coverage"]["RouteStick/xhard2"]
    assert cell["valid_successes"] == 1
    assert cell["missing_episodes"] == [1]
    assert cell["reset_failures"] == 1
    assert report["check"]["verdict"] == "FAIL"
    assert any(v["kind"] == "sample_shortfall" and v["env"] == "RouteStick"
               for v in report["check"]["violations"])


def test_v4_specs_reset_drafts_reject_tampered_spec_hash(tmp_path) -> None:
    paths = _write_reset_drafts(tmp_path, samples=2,
                                bad_spec_hash=("VideoPlaceButton", "xhard4", 0))
    report = M.check_reset_drafts(paths, samples=2)
    assert any("spec 缺失或散列不符" in error["error"] for error in report["input_errors"])
    assert report["check"]["verdict"] == "FAIL"


def test_v4_specs_reset_drafts_check_observed_mean_and_interval(tmp_path) -> None:
    overrides = {
        ("VideoPlaceButton", "xhard1", "placements"): [3, 4],
        ("VideoPlaceButton", "xhard2", "placements"): [4, 4],
    }
    report = M.check_reset_drafts(_write_reset_drafts(tmp_path, samples=2, overrides=overrides), samples=2)
    vp_steps = report["check"]["envs"]["VideoPlaceButton"]["gate"]["steps"]
    assert vp_steps[0]["step"] == "hard->xhard1"
    assert vp_steps[1]["step"] == "xhard1->xhard2"
    assert "placements" in vp_steps[1]["overlaps"]
    assert any(v["env"] == "VideoPlaceButton" and v["kind"] == "overlap"
               for v in report["check"]["violations"])

    decrease = {
        ("VideoPlaceButton", "xhard1", "placements"): [5, 5],
        ("VideoPlaceButton", "xhard2", "placements"): [4, 4],
    }
    report = M.check_reset_drafts(_write_reset_drafts(tmp_path / "decrease", samples=2,
                                                       overrides=decrease), samples=2)
    assert any(v["env"] == "VideoPlaceButton" and v["step"] == "xhard1->xhard2"
               and v["kind"] == "decrease" for v in report["check"]["violations"])
