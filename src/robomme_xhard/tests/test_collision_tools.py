"""阶段 E 工具契约：官方母清单、多 rank 与失败证据统计，只跑 CPU。"""

import json

import pytest

from robomme_xhard import jobs
from robomme_xhard.configs import DIFFICULTIES
from robomme_xhard.tools import layout, mother_seeds, summarize


TASKS = ["VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick"]


def test_all_limit_official_order_and_180_cards(tmp_path, capsys):
    out = tmp_path / "mother.json"
    assert mother_seeds.main(["--all", "--limit", "10", "--no-verify", "--tasks", ",".join(reversed(TASKS)), "--out", str(out)]) == 0
    manifest = json.loads(out.read_text())
    assert list(manifest["tasks"]) == TASKS
    assert manifest["mode"] == "all" and manifest["limit"] == 10
    for task, entries in manifest["tasks"].items():
        records = mother_seeds.load_records(mother_seeds.DEFAULT_METADATA_DIR, task)
        expected = sorted(r["episode"] for r in records if r["difficulty"] == mother_seeds.SOURCE_DIFFICULTY[task] and 6 <= r["episode"] <= 99)[:10]
        assert [e["episode"] for e in entries] == expected
        assert [e["rank"] for e in entries] == list(range(10))
        assert all(e["verify"] == "unverified" for e in entries)
    validated = jobs.validate_manifest(manifest)
    cards = jobs.expand_cards(validated, DIFFICULTIES, with_mother=True)
    assert len(cards) == 180 and all(c.attempt == 0 for c in cards)
    assert len(jobs.expand_cards(validated, DIFFICULTIES, mother_rank=9)) == 15
    assert "XHARD_MOTHER_ALL=PASS tasks=3 seeds=30 limit=10" in capsys.readouterr().out


@pytest.mark.parametrize("episode", [-1, 100, True])
def test_all_rejects_unofficial_episode_before_limit(episode):
    records = [{"episode": 7, "seed": 1, "difficulty": "hard"}, {"episode": episode, "seed": 2, "difficulty": "easy"}]
    with pytest.raises(mother_seeds.MotherSeedError, match="0–99"):
        mother_seeds.select_task("VideoUnmaskSwap", records, all_seeds=True, limit=1)


def test_any_nonnegative_unique_rank():
    entry = {"episode": 7, "seed": 1, "source_difficulty": "hard", "rank": 300}
    manifest = {"version": 1, "tasks": {"VideoUnmaskSwap": [entry]}}
    validated = jobs.validate_manifest(manifest)
    assert len(jobs.expand_cards(validated, ["xhard12"], mother_rank=300)) == 1
    manifest["tasks"]["VideoUnmaskSwap"].append({**entry, "episode": 11})
    with pytest.raises(jobs.XHardJobError, match="重复"):
        jobs.validate_manifest(manifest)


@pytest.mark.parametrize("summary", [True, False])
def test_failure_evidence_and_net_identity_aggregate(tmp_path, summary):
    plan = {"pairs": [[0, 1, 0.2, 0.01], [0, 1, 0.2, 0.01]], "usage": [2, 2, 0], "initiator_usage": [1, 1, 0], "partner_usage": [1, 1, 0]}
    evidence = {"error_type": "SwapCollisionError", "stage": "segment_start", "rejection": {"reason": "contact"}, "detail": {"k": 1}, "swap_plan": plan, "runtime_checks": [{"gap_lower_bound": 0.01}]}
    cards = [{"task": "VideoRepick", "seed": 1, "role": "xhard", "mother_episode": 6, "difficulty": "xhard12", "ok": False, "task_success": 0, "failure_class": "task", **evidence},
             {"task": "VideoRepick", "seed": 2, "role": "xhard", "mother_episode": 10, "difficulty": "xhard12", "ok": True, "task_success": 1, "swap_plan": {**plan, "pairs": [[0, 1, 0.2, 0.01]]}},
             {"task": "VideoRepick", "seed": 3, "role": "xhard", "mother_episode": 14, "difficulty": "xhard12", "ok": False, "task_success": 0}]
    if summary:
        (tmp_path / "run_summary.json").write_text(json.dumps({"cards": cards}))
    else:
        (tmp_path / "episode_results.jsonl").write_text("\n".join(json.dumps(c) for c in cards))
    results, _ = layout.read_run_results(tmp_path)
    assert all(results[("VideoRepick", 1, "xhard12")][key] == value for key, value in evidence.items())
    rows = summarize.collect(tmp_path)
    assert [r["net_identity"] for r in rows] == [True, False, None]
    group = summarize.aggregate(rows)[0]
    assert group["success_rate"] == 1 / 3
    assert group["identity_rate"] == 0.5 and group["identity_known"] == 2
    assert group["failures"]["SwapCollisionError×segment_start"] == 1
    assert len(group["participation"]) == 2
    assert group["collision_rejections"] == 1 and group["other_failures"] == 1
    assert group["participation_distribution"]["usage"] == {2: 4, 0: 2}
    assert "XHARD_FULL_DERIVE=DONE cards=3 ok=1 coll=1 other=1 unknown=0" == summarize.judge(rows)["XHARD_FULL_DERIVE"]
    assert "SwapCollisionError" in summarize.to_markdown(rows, summarize.judge(rows))


def test_identity_missing_evidence_is_unknown():
    assert summarize.net_identity(None) is None
    assert summarize.net_identity({"usage": [0, 0], "pairs": [[0, 5]]}) is None


@pytest.mark.parametrize("completed", [None, True, False])
@pytest.mark.parametrize("has_record", [False, True])
def test_success_requires_independent_completion(tmp_path, completed, has_record):
    import h5py

    path = tmp_path / "xhard12/hdf5_files/VideoRepick_ep6_seed1.h5"
    path.parent.mkdir(parents=True)
    with h5py.File(path, "w") as handle:
        episode = handle.create_group("episode_6")
        setup = episode.create_group("setup")
        setup.create_dataset("difficulty", data="xhard12")
        setup.create_dataset("seed", data=1)
        info = episode.create_group("timestep_0/info")
        if completed is not None:
            info.create_dataset("is_completed", data=completed)
    if has_record:
        card = {"task": "VideoRepick", "seed": 1, "mother_episode": 6,
                "role": "xhard", "difficulty": "xhard12", "ok": True}
        (tmp_path / "run_summary.json").write_text(json.dumps({"cards": [card]}))
    row = summarize.collect(tmp_path)[0]
    expected = None if has_record or completed is None else int(completed)
    assert row["task_success"] == expected
    assert row["last_completed"] is completed
    assert summarize.aggregate([row])[0]["success"] == (expected == 1)
    assert summarize.aggregate([row])[0]["unknown"] == (expected is None)


def test_ok_alone_does_not_establish_task_success(tmp_path):
    card = {"task": "VideoRepick", "seed": 1, "mother_episode": 6,
            "role": "xhard", "difficulty": "xhard12", "ok": True}
    (tmp_path / "episode_results.jsonl").write_text(json.dumps(card) + "\n")
    result = layout.read_run_results(tmp_path)[0][("VideoRepick", 1, "xhard12")]
    assert result["ok"] is True and result["task_success"] is None
    row = summarize.collect(tmp_path)[0]
    assert row["task_success"] is None
