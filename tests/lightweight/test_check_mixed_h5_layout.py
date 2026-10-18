"""校验工具 --layout／--tasks：身份推算与生成器一致、任务子集计数、默认行为不变。"""

from __future__ import annotations

import functools
import json

import pytest

from robomme_xhard.configs import TASK_ORDER, TIER_CONFIGS
from robomme_xhard.tests import test_check_mixed_h5 as base
from robomme_xhard.tools import check_mixed_h5 as checker
from seed_layout import difficulty_for, filter_cycle, get_layout, parse_difficulty_cycle

XHARD_CYCLE = "xhard12,xhard14,xhard16,xhard18,xhard20"
GROUPS = {
    "G5": (("BinFill", "PickXtimes", "SwingXtimes", "VideoUnmaskSwap", "ButtonUnmaskSwap",
            "VideoRepick", "PatternLock", "RouteStick"), 60),
    "G4": (("StopCube",), 48),
    "G3": (("PickHighlight",), 36),
    "G2": (("VideoPlaceButton",), 24),
    "G1": (("VideoUnmask", "ButtonUnmask", "VideoPlaceOrder"), 12),
}


def _generator_identity(task, episode, attempt, cycle, layout):
    """照生成器 generate_dataset_newseed 的推法：filter_cycle + difficulty_for + layout.seed。"""
    effective = filter_cycle(cycle, TIER_CONFIGS.get(task, {}))
    return difficulty_for(episode, effective), get_layout(layout).seed(task, episode, attempt)


@pytest.mark.parametrize("task", ["StopCube", "PickHighlight", "VideoRepick", "BinFill"])
def test_test_layout_identity_matches_generator(task):
    cycle = parse_difficulty_cycle(XHARD_CYCLE, checker.DIFFICULTIES)
    for episode in range(50, 110):
        for attempt in (0, 3):
            got = checker.expected_identity(task, episode, attempt, cycle, "test")
            assert (got["difficulty"], got["seed"]) == _generator_identity(task, episode, attempt, cycle, "test")
            # test 布局：500000 + env_code*10000 + ep*100 + attempt
            assert 500_000 <= got["seed"] < 1_000_000


def test_group_start_tiers_follow_filtered_cycle():
    cycle = parse_difficulty_cycle(XHARD_CYCLE, checker.DIFFICULTIES)
    for tasks, _ in GROUPS.values():
        for task in tasks:
            effective = filter_cycle(cycle, TIER_CONFIGS.get(task, {}))
            assert checker.effective_cycle(task, cycle) == effective
            assert checker.expected_identity(task, 50, 0, cycle, "test")["difficulty"] == effective[50 % len(effective)]


def test_default_layout_is_train():
    cycle = tuple(checker.DEFAULT_CYCLE.split(","))
    for task in TASK_ORDER:
        assert checker.expected_identity(task, 7, 2, cycle) == checker.expected_identity(task, 7, 2, cycle, "train")
        assert checker.expected_identity(task, 7, 2, cycle)["seed"] == get_layout("train").seed(task, 7, 2)


def _write_test_layout(root, tasks, cycle, start, episodes, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(checker, "expected_identity",
                      functools.partial(checker.expected_identity, layout="test"))
        return base.write_products(root, tasks=tasks, cycle=cycle, start=start, episodes=episodes)


def test_cli_test_layout_and_task_subset(tmp_path, monkeypatch, capsys):
    cycle = tuple(XHARD_CYCLE.split(","))
    root = _write_test_layout(tmp_path / "g3", ("PickHighlight",), cycle, 50, 3, monkeypatch)
    common = ["--output-dir", str(root), "--cycle", XHARD_CYCLE, "--episode-start", "50",
              "--episodes", "3", "--tasks", "PickHighlight"]
    assert checker.main(["audit", *common, "--layout", "test"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == \
        "IDENTITY_AUDIT=PASS episodes=3 missing=0 dup=0 unknown=0 mismatch=0"
    # 同一批产物按默认 train 布局审查，seed 必然对不上。
    assert checker.main(["audit", *common]) == 1
    assert capsys.readouterr().out.startswith("IDENTITY_AUDIT=FAIL")
    args = ["check", *common, "--layout", "test", "--golden-dir", str(base.GOLDEN_DIR), "--workers", "2",
            "--out-json", str(tmp_path / "check.json"), "--out-md", str(tmp_path / "check.md")]
    assert checker.main(args) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 4 and all("=PASS" in line for line in lines), lines
    assert lines[2] == "H5_COUNTS=PASS tasks=1 episodes=3 per_tier_ok=1"
    report = json.loads((tmp_path / "check.json").read_text())
    assert {row["task"] for row in report["counts"]["per_tier"]} == {"PickHighlight"}


def test_cli_rejects_unknown_task(tmp_path):
    with pytest.raises(SystemExit):
        checker.main(["audit", "--output-dir", str(tmp_path), "--episodes", "1", "--tasks", "NoSuchTask"])


def test_default_cli_counts_all_tasks(tmp_path, capsys):
    """不传 --layout／--tasks 时与原行为一致：16 个任务、train 布局。"""
    root = base.write_products(tmp_path / "all", tasks=TASK_ORDER, cycle=("easy",))
    assert checker.main(["audit", "--output-dir", str(root), "--cycle", "easy", "--episodes", "1"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == \
        "IDENTITY_AUDIT=PASS episodes=16 missing=0 dup=0 unknown=0 mismatch=0"
