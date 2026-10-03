"""D-19：Swap 两任务外环在低档取母布局外环的一段连续弧（nest_outer_arc + SpecRecorder.nest_context），纯 CPU。"""

from __future__ import annotations

import pytest

from robomme_hard.robomme_env.utils.episode_spec import (
    OUTER_ARC_KEY,
    SPEC_KIND_LAYERED,
    SPEC_KIND_NEWVALUE,
    SpecRecorder,
    nest_outer_arc,
)

pytestmark = pytest.mark.lightweight

PARENT_BINS = {str(i): [0.1 * i, -0.1 * i, 10.0 * i] for i in range(8)}
LAYOUT = {"L": [], "G": ["objects.distractors.cube_count"], "N": [f"{OUTER_ARC_KEY}.*"]}


def _recorder() -> SpecRecorder:
    parent = {"spec_kind": SPEC_KIND_NEWVALUE, "task": "ButtonUnmaskSwap",
              "objects": {"distractors": {"bins": PARENT_BINS, "cube_count": 4}}}
    return SpecRecorder({"envelope": "derive", "parent": parent, "layout": LAYOUT}, "ButtonUnmaskSwap",
                        {"seed": 14700004}, difficulty="xhard1")


def test_弧上下文决定取母布局哪几个外环容器():
    rec = _recorder()
    rec.nest_context[OUTER_ARC_KEY] = [5, 6]
    first = rec.value(f"{OUTER_ARC_KEY}.0", [9.0, 9.0, 9.0])
    second = rec.value(f"{OUTER_ARC_KEY}.1", [8.0, 8.0, 8.0])
    assert first == PARENT_BINS["5"] and second == PARENT_BINS["6"]
    doc = rec.to_dict()
    assert doc["spec_kind"] == SPEC_KIND_LAYERED
    assert doc["layout_nest_context"][OUTER_ARC_KEY] == [5, 6]
    assert doc["layout_drawn"][f"{OUTER_ARC_KEY}.0"] == [9.0, 9.0, 9.0]


def test_无上下文时退化为按放置序取前缀():
    rec = _recorder()
    assert nest_outer_arc(None, None, recorder=rec, path=f"{OUTER_ARC_KEY}.1") == PARENT_BINS["1"]


def test_弧派生文档分层回注零漂移():
    rec = _recorder()
    rec.nest_context[OUTER_ARC_KEY] = [3, 4]
    rec.value(f"{OUTER_ARC_KEY}.0", [1.0, 1.0, 1.0])
    rec.value(f"{OUTER_ARC_KEY}.1", [2.0, 2.0, 2.0])
    doc = rec.to_dict()
    replay = SpecRecorder(doc, "ButtonUnmaskSwap", {"seed": 14700004}, difficulty="xhard1")
    assert replay.value(f"{OUTER_ARC_KEY}.0", [1.0, 1.0, 1.0]) == PARENT_BINS["3"]
    assert replay.value(f"{OUTER_ARC_KEY}.1", [2.0, 2.0, 2.0]) == PARENT_BINS["4"]
    assert replay.layout_drift == 0 and not replay.mismatches
