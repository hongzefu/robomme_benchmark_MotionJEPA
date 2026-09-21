#!/usr/bin/env python3
"""轻量测试：每局规格的导出／回注机制（方案步 4，闸门 G4 的离线部分）。

最关键的一条：**回注模式必须返回冻结值**，哪怕原抽样恰好抽出同样的数——方案点名拒绝
「重抽出相同值却绕过规格」的实现，G4 要求这种反例被抓到。

    uv run --no-sync python -m pytest tests/lightweight/test_episode_spec_recorder.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils.episode_spec import (  # noqa: E402
    SPEC_KIND,
    EpisodeSpecError,
    SpecRecorder,
)

IDENTITY = {"task": "BinFill", "episode": 0, "seed": 4000, "difficulty": "easy"}


def _export() -> SpecRecorder:
    recorder = SpecRecorder(None, "BinFill", IDENTITY)
    recorder.value("layout.dynamic", True)
    recorder.value("layout.board.x_var", 0.123456789)
    recorder.value("objects.color_order", [2, 0, 1])
    recorder.record("objects.spawn_total", 5)
    return recorder


def test_export_returns_drawn_values_unchanged() -> None:
    recorder = _export()
    document = recorder.to_dict()
    assert document["spec_kind"] == SPEC_KIND
    assert document["identity"] == IDENTITY
    assert document["layout"]["board"]["x_var"] == 0.123456789
    assert document["objects"]["color_order"] == [2, 0, 1]
    assert document["objects"]["spawn_total"] == 5
    assert document["provenance"]["mismatches"] == 0


def test_replay_returns_frozen_value_even_when_draw_matches() -> None:
    """抽样值与冻结值相同也必须走规格——返回的对象就是规格里的那一个。"""
    document = _export().to_dict()
    replay = SpecRecorder(document, "BinFill", IDENTITY)
    assert replay.replaying
    assert replay.value("layout.board.x_var", 0.123456789) == 0.123456789
    assert replay.mismatches == []
    # 抽样漂移时仍然用冻结值，并把差异记成兼容核验失败。
    assert replay.value("objects.color_order", [0, 1, 2]) == [2, 0, 1]
    assert replay.mismatches and replay.mismatches[0]["path"] == "objects.color_order"


def test_replay_rejects_wrong_kind_or_task() -> None:
    document = _export().to_dict()
    with pytest.raises(EpisodeSpecError):
        SpecRecorder({**document, "spec_kind": "legacy/9"}, "BinFill", IDENTITY)
    with pytest.raises(EpisodeSpecError):
        SpecRecorder(document, "RouteStick", IDENTITY)


def test_replay_rejects_missing_value_point() -> None:
    document = _export().to_dict()
    replay = SpecRecorder(document, "BinFill", IDENTITY)
    with pytest.raises(EpisodeSpecError):
        replay.value("layout.button_xy", [0.0, 0.0])


def test_trace_records_every_value_point() -> None:
    recorder = _export()
    # value() 与 record() 都要进 trace：后者虽然不替换取值，但路径确实被访问过，
    # 否则 SPEC_BINDING 会把它误判成「有记录却没被消费」（unused）。
    assert [item["path"] for item in recorder.trace] == [
        "layout.dynamic", "layout.board.x_var", "objects.color_order", "objects.spawn_total",
    ]
    document = recorder.to_dict()
    # value_points 只数真正的取值点（draw/spec），不把 record 计进去
    assert document["provenance"]["value_points"] == 3


def test_recorded_paths_count_as_consumed() -> None:
    """只读记录的派生量也算被消费，不能进 unused。"""
    document = _export().to_dict()
    replay = SpecRecorder(document, "BinFill", IDENTITY)
    replay.value("layout.dynamic", True)
    replay.value("layout.board.x_var", 0.123456789)
    replay.value("objects.color_order", [2, 0, 1])
    replay.record("objects.spawn_total", 5)
    consumed = set(replay.consumed_paths())
    unused = [path for path in replay.leaf_paths() if not any(
        path == item or path.startswith(item + ".") for item in consumed
    )]
    assert unused == []
