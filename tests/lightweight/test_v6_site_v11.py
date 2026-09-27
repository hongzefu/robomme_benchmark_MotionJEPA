#!/usr/bin/env python3
"""轻量测试：site-v11（V6 语义审查修复后网站）的目录新增字段（不读 HDF5、不占 GPU）。

覆盖 scripts/parity/v6_site_catalog.py：本轮改动 15 条、已知问题分组、修复后 VPB 新句式解析、
Q-C 修复后程序答案 = 按钮前最后一次放置（不再标已知问题）、放回原位无坐标的说明、
子目标人读标签（等待容器交换完成等）、新旧数据两种说明框，以及计划第三节表格解析。

    uv run --no-sync python -m pytest tests/lightweight/test_v6_site_v11.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
for _entry in (REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "parity"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import v6_site_catalog as cat  # noqa: E402
from test_v6_site_labels import BTN, DROP, EXEC, HOME, PICK, STATIC, T, color_at, seq  # noqa: E402

NEW_BEFORE = "watch the video carefully, then place the blue cube on the target where it was last placed before the button was pressed"
NEW_AFTER = "watch the video carefully, then place the red cube on the target where it was first placed after the button was pressed"


def test_changelog_has_15_items_with_required_fields():
    assert len(cat.CHANGELOG) == 15
    refs = {ref for item in cat.CHANGELOG for ref in item["refs"]}
    for ref in ("F1", "F3", "F4", "F6", "N1", "N2", "N3", "N4", "N5", "N10", "N11", "D6", "Q-C", "M1"):
        assert ref in refs, ref
    for item in cat.CHANGELOG:
        assert all(item[key] for key in ("group", "env", "change", "reason", "tiers"))
    assert [item["group"][0] for item in cat.CHANGELOG] == list("一一二二二二二二三三三三四四四")
    for dropped in ("D1", "D4", "D5"):
        assert dropped not in refs


def test_known_issues_cover_disclosed_ids():
    text = " ".join(entry for group in cat.KNOWN_ISSUES for entry in group["items"])
    for ref in ("F2", "F5", "D3", "D7", "N6～N8", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9",
                "S10", "S11", "S12", "S13", "M3", "N9", "D2"):
        assert ref in text, ref
    assert "V4" in text and "机器人坐标系" in cat.KNOWN_ISSUES_NOTE


def test_parse_goal_new_single_sentence():
    assert cat.parse_goal(NEW_BEFORE) == {"color": "blue", "mode": "before", "n": None}
    assert cat.parse_goal(NEW_AFTER) == {"color": "red", "mode": "after", "n": None}


def test_translate_subgoal():
    assert cat.translate_subgoal("wait for the containers to finish swapping") == "等待容器交换完成"
    assert cat.translate_subgoal("press the button at <120, 86>") == "按按钮"
    assert cat.translate_subgoal("place the cube onto the table") == "把方块放到桌面"
    assert "设计如此" in cat.translate_subgoal("put the cube back to its original position")


def _fixed_two_cube_demo():
    # 蓝(正确)→A，红→B，蓝额外→C（按钮前最后一次），按钮，蓝→D，红→E，各放回原位（无坐标）
    t_e = (100, 120)
    return seq([(PICK, (100, 200)), (DROP, T["A"]), (PICK, (100, 50)), (DROP, T["C"]),
                (PICK, (44, 44)), (DROP, T["B"]), (BTN, (128, 128)),
                (PICK, (36, 116)), (DROP, T["D"]), (PICK, (158, 42)), (DROP, t_e),
                (PICK, (162, 118)), (HOME, None), (PICK, (98, 118)), (HOME, None), (STATIC, None), (STATIC, None)])


def test_fixed_vpb_before_program_answer_is_last_placement():
    ex = seq([(PICK, (101, 201))] + EXEC[1:], "execution_steps", 100)
    goal = dict(cat.parse_goal(NEW_BEFORE), fixed=True)
    flow, audit = cat.label_flow("VideoPlaceButton", _fixed_two_cube_demo() + ex, 2, goal, color_at, 5)
    assert audit["asked_index"] == audit["program_answer_index"] == 5
    assert all("note" not in step for step in flow["demo_steps"])
    texts = [s["text"] for s in flow["demo_steps"]]
    assert texts[12] == "正确方块放回原位（该子目标无坐标，设计如此）"
    assert texts[14] == "干扰方块放回原位（该子目标无坐标，设计如此）"
    assert len(audit["targets"]) == 5


def test_legacy_goal_keeps_known_issue_binding():
    ex = seq([(PICK, (101, 201))] + EXEC[1:], "execution_steps", 100)
    goal = cat.parse_goal("place the blue cube on the target right before the button was pressed")
    _, audit = cat.label_flow("VideoPlaceButton", _fixed_two_cube_demo() + ex, 2, goal, color_at, 5)
    assert audit["program_answer_index"] == 1 and audit["asked_index"] == 5


def test_task_notices_degrade_for_legacy_data():
    fixed, legacy = cat.task_notices(True), cat.task_notices(False)
    assert fixed["VideoPlaceButton"]["kind"] == "emphasis" and "Q-C" in fixed["VideoPlaceButton"]["title"]
    assert "台可交换" in " ".join(fixed["VideoPlaceButton"]["steps"])
    assert legacy["VideoPlaceButton"]["kind"] == "issue" and "示例4" in " ".join(legacy["VideoPlaceButton"]["steps"])
    assert "等待容器交换完成" in fixed["ButtonUnmaskSwap"]["title"]
    assert "修复前" in legacy["ButtonUnmaskSwap"]["note"]
    assert set(fixed) == set(legacy) == {"ButtonUnmaskSwap", "PickHighlight", "VideoPlaceOrder", "VideoPlaceButton"}


def test_gradients_parse_after_plan_table_edit():
    values = cat.gradients(REPO_ROOT / "0925-newtask-release-v6-plan.md")
    assert values["VideoPlaceButton"]["xhard3"] == "放台次数（都放回原位）：2 块 5 次"
    assert set(values) == set(cat.NAMES)


def test_html_renders_changelog_items_and_degrades():
    html = (REPO_ROOT / "scripts/parity/v6_site.html").read_text(encoding="utf-8")
    assert "data-changelog-item" in html and "renderRoundNotes(catalog)" in html
    assert "catalog.changelog" in html and "box.hidden = !box.childElementCount" in html
