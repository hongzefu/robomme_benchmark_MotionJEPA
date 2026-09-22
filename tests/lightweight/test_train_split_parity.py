#!/usr/bin/env python3
"""轻量测试：原始 train 身份冻结的口径与反例（不加载仿真、不占 GPU）。

对应 NEWTASK_RELEASE_V3_PLAN.md 步 0 的 G1：身份逐条取官方 metadata、不用公式替换
实际 seed、子集按每 task 每难度前 3 条固定、恢复模式按官方 ``EpisodeJob.recovery_mode``。
另覆盖 ``run``／``compare`` 的参数校验反例（步 1b 之前只有校验）。

    uv run --no-sync python -m pytest tests/lightweight/test_train_split_parity.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
# 对拍链路已迁入 scripts/parity/；seed_layout 仍在 scripts/ 顶层，两处都要进 sys.path。
SCRIPTS_DIR = REPO_ROOT / "scripts"
for _entry in (SCRIPTS_DIR, SCRIPTS_DIR / "parity"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import train_split_parity as parity  # noqa: E402
from seed_layout import ALL_TASKS, DIFFICULTY_ORDER  # noqa: E402

FROZEN_DIR = REPO_ROOT / "scripts" / "configs" / "newtask-v3"


def _load(name: str) -> dict:
    path = FROZEN_DIR / name
    if not path.exists():
        pytest.skip(f"冻结产物缺失：{path}；先运行 freeze-identities")
    return json.loads(path.read_text(encoding="utf-8"))


def test_recovery_mode_matches_official_rule() -> None:
    """官方 EpisodeJob.recovery_mode：0～2 为 z，3～5 为 xy，其余无。"""
    assert [parity.recovery_mode(ep) for ep in range(8)] == [
        "z", "z", "z", "xy", "xy", "xy", None, None,
    ]


def test_full_manifest_is_official_1600_rows() -> None:
    manifest = _load("train_manifest.json")
    rows = manifest["rows"]
    assert manifest["source_ref"] == parity.DEFAULT_SOURCE_REF
    assert manifest["records_sha256"] == parity.EXPECTED_RECORDS_SHA256
    assert len(rows) == 1600
    assert manifest["recovery_config_counts"] == parity.EXPECTED_FULL_RECOVERY
    # 170 条实际 seed 不等于 attempt 0 公式值，且必须原样保留。
    non_formula = [row for row in rows if not row["seed_matches_formula"]]
    assert len(non_formula) == parity.EXPECTED_NON_FORMULA_SEEDS
    for row in non_formula:
        assert row["seed"] != row["formula_base_seed"]
    # 每环境 100 条、episode 0～99 无重复。
    for task in ALL_TASKS:
        episodes = [row["episode"] for row in rows if row["task"] == task]
        assert sorted(episodes) == list(range(100))


def test_subset_is_first_three_per_difficulty() -> None:
    subset = _load("subset_manifest.json")
    full = _load("train_manifest.json")
    rows = subset["rows"]
    assert len(rows) == 144 == len(ALL_TASKS) * len(DIFFICULTY_ORDER) * subset["per_cell"]
    assert subset["recovery_config_counts"] == parity.EXPECTED_SUBSET_RECOVERY
    full_index = {(row["task"], row["episode"]): row for row in full["rows"]}
    for task in ALL_TASKS:
        picked = [row for row in rows if row["task"] == task]
        assert sorted(row["episode"] for row in picked) == list(parity.EXPECTED_SUBSET_EPISODES)
        for difficulty in DIFFICULTY_ORDER:
            cell = [row for row in picked if row["difficulty"] == difficulty]
            expected = [
                row
                for row in full["rows"]
                if row["task"] == task and row["difficulty"] == difficulty
            ][: subset["per_cell"]]
            assert cell == expected
        # 子集每条都能回指全量行，且 seed／难度与全量一致。
        for row in picked:
            assert full_index[(row["task"], row["episode"])] == row


def test_cross_check_detects_replaced_seed() -> None:
    """把一条 seed 改成公式值，双向比较必须报出 mismatch。"""
    raw = json.dumps(
        {
            "env_id": "BinFill",
            "record_count": 1,
            "records": [
                {"task": "BinFill", "episode": 3, "seed": 4301, "difficulty": "hard"}
            ],
        }
    ).encode()
    metadata = {task: {"raw": raw} for task in ALL_TASKS}
    rows = [{"task": "BinFill", "episode": 3, "seed": 4301, "difficulty": "hard"}] * len(ALL_TASKS)
    assert parity.cross_check_identity(rows, metadata) > 0  # 集合去重后行数不同，必须被抓到

    good_rows = [{"task": "BinFill", "episode": 3, "seed": 4301, "difficulty": "hard"}]
    single = {"BinFill": {"raw": raw}}
    assert parity.cross_check_identity(good_rows, single, tasks=("BinFill",)) == 0
    # 把实际 seed 4301 换成公式值 4300，必须判 mismatch。
    bad_rows = [{"task": "BinFill", "episode": 3, "seed": 4300, "difficulty": "hard"}]
    assert parity.cross_check_identity(bad_rows, single, tasks=("BinFill",)) > 0


def test_record_validation_rejects_bad_metadata() -> None:
    base = {
        "env_id": "BinFill",
        "record_count": 2,
        "records": [
            {"task": "BinFill", "episode": 0, "seed": 4000, "difficulty": "easy"},
            {"task": "BinFill", "episode": 1, "seed": 4100, "difficulty": "easy"},
        ],
    }
    assert len(parity._validate_records("BinFill", base, 2)) == 2

    dup = json.loads(json.dumps(base))
    dup["records"][1]["episode"] = 0
    with pytest.raises(parity.IdentityFreezeError):
        parity._validate_records("BinFill", dup, 2)

    short = json.loads(json.dumps(base))
    short["records"].pop()
    short["record_count"] = 1
    with pytest.raises(parity.IdentityFreezeError):
        parity._validate_records("BinFill", short, 2)

    extra_key = json.loads(json.dumps(base))
    extra_key["records"][0]["attempt"] = 0
    with pytest.raises(parity.IdentityFreezeError):
        parity._validate_records("BinFill", extra_key, 2)

    bad_difficulty = json.loads(json.dumps(base))
    bad_difficulty["records"][0]["difficulty"] = "xhard"
    with pytest.raises(parity.IdentityFreezeError):
        parity._validate_records("BinFill", bad_difficulty, 2)


def test_select_subset_requires_enough_rows() -> None:
    rows = [
        {"task": task, "episode": 0, "seed": 1, "difficulty": "easy", "recovery_mode": "z"}
        for task in ALL_TASKS
    ]
    with pytest.raises(parity.IdentityFreezeError):
        parity.select_subset(rows, per_cell=3)


def test_argument_validation_rejects_invalid_scope() -> None:
    with pytest.raises(parity.IdentityFreezeError):
        parity._parse_paths("A1,A1")
    with pytest.raises(parity.IdentityFreezeError):
        parity._parse_paths("A3")
    assert parity._parse_paths("D,A1") == ["A1", "D"]
    with pytest.raises(parity.IdentityFreezeError):
        parity._parse_shard("5/4")
    with pytest.raises(parity.IdentityFreezeError):
        parity._parse_shard("1-4")
    assert parity._parse_shard("2/4") == (2, 4)


def test_run_rejects_episode_outside_subset(tmp_path: Path) -> None:
    """episode 5 不在 144 条子集内，run 必须拒绝，不得由连续编号推导。"""
    manifest = _load("subset_manifest.json")
    path = tmp_path / "subset_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    parser = parity.build_parser()
    args = parser.parse_args(
        ["run", "--manifest", str(path), "--env", "BinFill", "--episode", "5",
         "--paths", "A1", "--output", str(tmp_path / "out")]
    )
    with pytest.raises(parity.IdentityFreezeError):
        parity.cmd_run(args)
    # 子集内的 episode 0 必须能选出唯一一条身份（这里只做选择，不真的起仿真）。
    picked = parity.select_rows(manifest, "BinFill", 0, None)
    assert len(picked) == 1
    assert picked[0]["seed"] == 4000 and picked[0]["recovery_mode"] == "z"
    # 分片选择与方案第二部分「十」的分片表一致：4 片按 ALL_TASKS 顺序连续切。
    shard1 = parity.select_rows(manifest, None, None, (1, 4))
    assert {row["task"] for row in shard1} == set(parity.ALL_TASKS[0:4])
    assert len(shard1) == 36


# --------------------------------------------------------------------------
# 步 1a：历史证据冻结与 R1a 投影
# --------------------------------------------------------------------------


def _load_history() -> dict:
    path = FROZEN_DIR / "history" / "history_projection.json"
    if not path.exists():
        pytest.skip(f"历史投影缺失：{path}；先运行 freeze-history")
    return json.loads(path.read_text(encoding="utf-8"))


def test_history_projection_covers_subset_only_with_comparable_fields() -> None:
    projection = _load_history()
    assert projection["rows_total"] == 144
    assert projection["missing_rows"] == 0
    assert projection["identity_mismatch"] == 0
    # R1a 明确不含历史动作数值。
    assert projection["projected_fields"] == list(parity.HISTORY_PROJECTED_FIELDS)
    assert "action" not in " ".join(projection["projected_fields"])
    subset = _load("subset_manifest.json")
    keys = {(row["task"], row["episode"]) for row in subset["rows"]}
    rows = projection["rows"]
    assert len(rows) == 144
    assert {(row["task"], row["episode"]) for row in rows} == keys
    for row in rows:
        # 逐条都要有历史帧数与成功标志，缺一条就不能称 R1a 可投影。
        assert row["history"]["timestep_count"] is not None
        assert row["history"]["ok"] is True
        assert row["history"]["generated_final_is_completed"] is True
        assert row["history"]["reference_timestep_count"] is not None


def test_history_full_set_numbers_are_kept_as_failed() -> None:
    """历史全集动作比较是 failed，原始数值必须原样保留，不得改写成 PASS。"""
    projection = _load_history()
    full = projection["full_set_action_comparison"]
    assert full["passed"] is False
    assert full["different_element_count"] == 217242
    assert full["max_abs_diff"] == pytest.approx(0.007857919612339614)
    assert full["max_allowed_abs_diff"] == 1e-8
    # different_element_count 的定义必须写明是 delta!=0，不能混称「超过 1e-8 的元素数」。
    assert "1e-8" in full["different_element_count_definition"] or "delta" in full["different_element_count_definition"]
    assert projection["report_status"] == "failed"


def test_history_subset_timestep_errors_are_the_two_known_rows() -> None:
    projection = _load_history()
    assert len(projection["timestep_errors_full_set"]) == 10
    hits = projection["timestep_errors_in_subset"]
    assert len(hits) == 2
    assert any(item.startswith("BinFill/episode_11") for item in hits)
    assert any(item.startswith("PickHighlight/episode_3") for item in hits)
    # 最大差位置 BinFill/99 不在子集内，不能用全集最大差代表子集。
    assert projection["full_set_action_comparison"]["max_abs_diff_location"]["episode"] == 99


def test_history_artifacts_are_registered_missing() -> None:
    projection = _load_history()
    assert projection["not_run"]["HISTORICAL_ACTION_PARITY"] == "historical_per_episode_evidence_missing"
    assert projection["not_run"]["HISTORICAL_ARTIFACT_PARITY"] == "historical_files_missing"
    assert all(exists is False for exists in projection["artifact_probes"].values())
