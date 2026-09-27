#!/usr/bin/env python3
"""轻量测试：VPB/VPO 网站子目标人读标签的位置链归属与题目标记（不读 HDF5、不占 GPU）。

覆盖 scripts/parity/v6_site_catalog.py 的 parse_goal / label_flow：一块 hard（放到桌面无坐标）、
两块 VPB before 且按钮前额外段归正确方块（题意与程序答案不同）、VPB after、VPO 第 N 次、
抓取偏差 12 px 归属、偏差 20 px 且方块数已满必须拒绝。

    uv run --no-sync python -m pytest tests/lightweight/test_v6_site_labels.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
for _entry in (REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "parity"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import v6_site_catalog as cat  # noqa: E402

ORIGINS = {(100, 50): "red", (100, 200): "blue"}


def color_at(point):
    for origin, color in ORIGINS.items():
        if cat._dist(point, origin) <= 3:
            return color
    raise AssertionError(f"测试桩没有该原点：{point}")


def step(simple, point=None, phase="demo_steps", timestep=None):
    return {"timestep": timestep if timestep is not None else 0, "phase": phase, "simple": simple,
            "grounded": simple, "point": point, "point_source": "grounded" if point else "none"}


def seq(items, phase="demo_steps", start=0):
    return [step(name, point, phase, start + index) for index, (name, point) in enumerate(items)]


PICK, DROP, HOME, TABLE, BTN, STATIC = ("pick up the cube", "drop the cube onto target",
                                       "put the cube back to its original position", "drop the cube onto table",
                                       "press the button", "static")
EXEC = [("pick up the cube", None), ("place the cube onto the correct target", (60, 60))]
T = {"A": (40, 40), "B": (40, 120), "C": (160, 40), "D": (160, 120)}


def test_parse_goal():
    goal = cat.parse_goal("watch the video carefully, then place the blue cube on the target right before the button was pressed")
    assert goal["text"].startswith("watch the video carefully")  # 2026-09-27：保留英文原句供网页展示
    assert {k: v for k, v in goal.items() if k != "text"} == {"color": "blue", "mode": "before", "n": None}
    assert cat.parse_goal("then place the red cube on the target right after the button was pressed")["mode"] == "after"
    assert {k: v for k, v in cat.parse_goal("then place the green cube on the third target it was previously placed on").items()
            if k != "text"} == {"color": "green", "mode": "order", "n": 3}
    with pytest.raises(ValueError):
        cat.parse_goal("place the purple cube on the target right before the button was pressed")


def test_hard_single_cube_table_then_exec():
    demo = seq([(PICK, (100, 50)), (DROP, T["A"]), (BTN, (128, 128)), (PICK, (41, 42)), (DROP, T["B"]),
                (PICK, (42, 121)), (TABLE, None), (STATIC, None), (STATIC, None)])
    ex = seq([(PICK, (90, 90))] + EXEC[1:], "execution_steps", 100)
    goal = cat.parse_goal("place the red cube on the target right before the button was pressed")
    flow, audit = cat.label_flow("VideoPlaceButton", demo + ex, 1, goal, color_at, None)
    texts = [s["text"] for s in flow["demo_steps"]]
    assert texts == ["抓起正确方块（红）", "正确方块 → 台 A（按钮前第 1 次放置）", "按按钮", "抓起正确方块（红）",
                     "正确方块 → 台 B（按钮后第 1 次放置）", "抓起正确方块（红）", "正确方块放到桌面（演示结束）", "静止", "静止"]
    assert [s["asked"] for s in flow["demo_steps"]].index(True) == 1
    assert audit["asked_index"] == audit["program_answer_index"] == 1
    assert [s["text"] for s in flow["execution_steps"]] == ["抓起正确方块（红）", "放到答案台"]
    assert flow["question_zh"] == "题目：把红色方块放到它在按按钮前最后一次放置的台"
    assert flow["question"].startswith("题目：") and "cube" in flow["question"]  # 英文原句
    assert all("en" in step for step in flow["demo_steps"] + flow["execution_steps"])


def test_vpb_two_cubes_before_with_extra_segment_flags_known_issue():
    # c0 蓝(正确)→A，c1 红→C，额外段 c0→B，按钮，c0→D，c1→B?（此处放 A 已空），各放回原位
    demo = seq([(PICK, (100, 200)), (DROP, T["A"]), (PICK, (100, 50)), (DROP, T["C"]),
                (PICK, (44, 44)), (DROP, T["B"]), (BTN, (128, 128)),
                (PICK, (36, 116)), (DROP, T["D"]), (PICK, (158, 42)), (DROP, T["A"]),
                (PICK, (162, 118)), (HOME, (100, 200)), (PICK, (42, 38)), (HOME, (100, 50)), (STATIC, None), (STATIC, None)])
    ex = seq([(PICK, (101, 201))] + EXEC[1:], "execution_steps", 100)
    goal = cat.parse_goal("place the blue cube on the target right before the button was pressed")
    flow, audit = cat.label_flow("VideoPlaceButton", demo + ex, 2, goal, color_at, 5)
    texts = [s["text"] for s in flow["demo_steps"]]
    assert texts[:6] == ["抓起正确方块（蓝）", "正确方块 → 台 A（按钮前第 1 次放置）", "抓起干扰方块（红）",
                         "干扰方块 → 台 B（按钮前第 1 次放置）", "抓起正确方块（蓝）", "正确方块 → 台 C（按钮前第 2 次放置）"]
    assert texts[8] == "正确方块 → 台 D（按钮后第 1 次放置）" and texts[10] == "干扰方块 → 台 A（按钮后第 1 次放置）"
    assert texts[12] == "正确方块放回原位" and texts[14] == "干扰方块放回原位"
    asked = [i for i, s in enumerate(flow["demo_steps"]) if s["asked"]]
    assert asked == [5] and audit["program_answer_index"] == 1
    assert flow["demo_steps"][5]["note"] == cat.KNOWN_ISSUE_NOTE
    assert flow["cubes"] == [{"color": "蓝", "role": "correct"}, {"color": "红", "role": "distractor"}]


def test_vpb_after_marks_first_after_placement():
    demo = seq([(PICK, (100, 50)), (DROP, T["A"]), (BTN, (128, 128)), (PICK, (41, 42)), (DROP, T["B"]),
                (PICK, (42, 121)), (DROP, T["C"]), (PICK, (158, 42)), (HOME, (100, 50)), (STATIC, None), (STATIC, None)])
    ex = seq([(PICK, (100, 51))] + EXEC[1:], "execution_steps", 100)
    goal = cat.parse_goal("place the red cube on the target right after the button was pressed")
    flow, audit = cat.label_flow("VideoPlaceButton", demo + ex, 1, goal, color_at, 3)
    assert [s["asked"] for s in flow["demo_steps"]].index(True) == 4
    assert flow["demo_steps"][6]["text"] == "正确方块 → 台 C（按钮后第 2 次放置）"
    assert "note" not in flow["demo_steps"][4]


def test_vpo_nth_placement_counts_per_cube_without_side():
    demo = seq([(PICK, (100, 50)), (DROP, T["A"]), (PICK, (41, 42)), (DROP, T["B"]), (BTN, (128, 128)),
                (PICK, (42, 121)), (DROP, T["C"]), (PICK, (158, 42)), (HOME, (100, 50)),
                (PICK, (100, 200)), (DROP, T["B"]), (PICK, (38, 118)), (DROP, T["D"]), (PICK, (161, 122)), (HOME, (100, 200)),
                (STATIC, None), (STATIC, None)])
    ex = seq([(PICK, (100, 199))] + EXEC[1:], "execution_steps", 100)
    goal = cat.parse_goal("place the blue cube on the second target it was previously placed on")
    flow, audit = cat.label_flow("VideoPlaceOrder", demo + ex, 2, goal, color_at, 5)
    texts = [s["text"] for s in flow["demo_steps"]]
    assert texts[1] == "干扰方块 → 台 A（第 1 次放置）" and texts[6] == "干扰方块 → 台 C（第 3 次放置）"
    assert texts[10] == "正确方块 → 台 B（第 1 次放置）" and texts[12] == "正确方块 → 台 D（第 2 次放置）"
    assert [s["asked"] for s in flow["demo_steps"]].index(True) == 12
    assert audit["targets"] == [list(T["A"]), list(T["B"]), list(T["C"]), list(T["D"])]


def test_pick_offset_12px_matches_but_20px_when_full_is_rejected():
    goal = cat.parse_goal("place the red cube on the target right before the button was pressed")
    ok = seq([(PICK, (100, 50)), (DROP, T["A"]), (BTN, (128, 128)), (PICK, (52, 52)), (DROP, T["B"]),
              (PICK, (40, 120)), (HOME, (100, 50)), (STATIC, None), (STATIC, None)])
    ex = seq([(PICK, (100, 50))] + EXEC[1:], "execution_steps", 100)
    flow, _ = cat.label_flow("VideoPlaceButton", ok + ex, 1, goal, color_at, 2)
    assert flow["demo_steps"][3]["text"] == "抓起正确方块（红）"
    bad = seq([(PICK, (100, 50)), (DROP, T["A"]), (BTN, (128, 128)), (PICK, (60, 60)), (DROP, T["B"]),
               (PICK, (40, 120)), (HOME, (100, 50)), (STATIC, None), (STATIC, None)])
    with pytest.raises(ValueError, match="无法归属"):
        cat.label_flow("VideoPlaceButton", bad + ex, 1, goal, color_at, 2)


def test_color_mismatch_and_placement_count_are_rejected():
    demo = seq([(PICK, (100, 50)), (DROP, T["A"]), (BTN, (128, 128)), (PICK, (41, 42)), (DROP, T["B"]),
                (PICK, (42, 121)), (HOME, (100, 50)), (STATIC, None), (STATIC, None)])
    ex = seq([(PICK, (100, 50))] + EXEC[1:], "execution_steps", 100)
    wrong_color = cat.parse_goal("place the blue cube on the target right before the button was pressed")
    with pytest.raises(ValueError, match="颜色"):
        cat.label_flow("VideoPlaceButton", demo + ex, 1, wrong_color, color_at, 2)
    goal = cat.parse_goal("place the red cube on the target right before the button was pressed")
    with pytest.raises(ValueError, match="放台"):
        cat.label_flow("VideoPlaceButton", demo + ex, 1, goal, color_at, 3)
