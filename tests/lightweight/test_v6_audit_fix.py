# robomme_hard：本测试测新值档／改动行为，阶段 3 起 src/robomme 回到官方 1fadc0ec，故改测 robomme_hard（0927 计划 R8 第③类）
#!/usr/bin/env python3
"""轻量测试：V6 审查修复（0926-v6-audit-fix-plan.md 第八节 8.2）。

全部纯 CPU、不起 sapien 场景。

    uv run --no-sync python -m pytest tests/lightweight/test_v6_audit_fix.py -q
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

# 包的 __init__ 用 `from .X import *` 覆盖了同名属性，只能按模块路径取
xhard_home_site = importlib.import_module("robomme_hard.robomme_env.utils.xhard_home_site")
task_goal = importlib.import_module("robomme_hard.robomme_env.utils.task_goal")
seg_utils = importlib.import_module("robomme_hard.robomme_env.utils.segmentation_utils")
subgoal_language = importlib.import_module("robomme_hard.robomme_env.utils.subgoal_language")
vpb_mod = importlib.import_module("robomme_hard.robomme_env.VideoPlaceButton")
vrp_mod = importlib.import_module("robomme_hard.robomme_env.VideoRepick")
from robomme_hard.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402

XHARD = ("xhard1", "xhard2", "xhard3", "xhard4")
ORIGINAL = ("easy", "medium", "hard", None)


# ---------------- F6 / N2：放置序列守卫 ----------------
def test_validate_place_sequence_legal():
    """F6：合法序列（含额外放置换台）通过，返回终态占用表。"""
    occ = xhard_home_site.validate_place_sequence([(0, 0), (1, 1), (0, 2)], 3)
    assert occ == {0: None, 1: 1, 2: 0}


def test_validate_place_sequence_two_on_one():
    """F6/D8：两块同台必须抛 SceneGenerationError。"""
    with pytest.raises(SceneGenerationError):
        xhard_home_site.validate_place_sequence([(0, 0), (1, 0)], 3)


def test_validate_place_sequence_noop():
    """N2：原地空转（同一块再放回同一台）必须抛错。"""
    with pytest.raises(SceneGenerationError):
        xhard_home_site.validate_place_sequence([(0, 1), (0, 1)], 3)


def test_validate_place_sequence_out_of_range():
    """F6：越界台号必须抛错。"""
    with pytest.raises(SceneGenerationError):
        xhard_home_site.validate_place_sequence([(0, 3)], 3)


# ---------------- F1：PickHighlight 语言目标 ----------------
@pytest.mark.parametrize("difficulty", XHARD)
def test_pickhighlight_goal_xhard(difficulty):
    """F1（K2）：新四档两句不含拼写错误 highlighteted，且提到末尾按钮停止。"""
    goals = task_goal.get_language_goal(SimpleNamespace(difficulty=difficulty), "PickHighlight")
    assert len(goals) == 2
    assert all("highlighteted" not in g for g in goals)
    assert "press the button to stop" in goals[0]
    assert "press the button again to stop" in goals[1]


@pytest.mark.parametrize("difficulty", ORIGINAL)
def test_pickhighlight_goal_original(difficulty):
    """F1：原三档两句逐字保持旧文本。"""
    goals = task_goal.get_language_goal(SimpleNamespace(difficulty=difficulty), "PickHighlight")
    assert goals == [
        "first press the button, then pick up all cubes that have been highlighteted with white areas on the table",
        "first press the button, then pick up all highlighted cubes, finally press the button again to stop",
    ]


# ---------------- N3/N4：VideoPlaceButton 语言目标 ----------------
@pytest.mark.parametrize("difficulty", XHARD)
@pytest.mark.parametrize("when,phrase", [("before", "last placed before the button was pressed"),
                                         ("after", "first placed after the button was pressed")])
def test_vpb_goal_xhard_single(difficulty, when, phrase):
    """N3/N4：新四档只返回一句，before/after 分别用 last placed before / first placed after。"""
    self = SimpleNamespace(difficulty=difficulty, target_color_name="red", target_target_language=when)
    goals = task_goal.get_language_goal(self, "VideoPlaceButton")
    assert len(goals) == 1
    assert phrase in goals[0]


@pytest.mark.parametrize("difficulty", ORIGINAL)
@pytest.mark.parametrize("when", ["before", "after"])
def test_vpb_goal_original_four(difficulty, when):
    """N3/N4：原三档仍返回四句，第 1 句含 right。"""
    self = SimpleNamespace(difficulty=difficulty, target_color_name="red", target_target_language=when)
    goals = task_goal.get_language_goal(self, "VideoPlaceButton")
    assert len(goals) == 4
    assert "right" in goals[0]


# ---------------- F4：分割中心随移动刷新 ----------------
class _Actor:
    pass


def _seg_with_blocks(center_a, center_b):
    seg = np.zeros((64, 64), dtype=np.int32)
    for obj_id, (y, x) in ((1, center_a), (2, center_b)):
        seg[y - 1:y + 2, x - 1:x + 2] = obj_id
    return seg


def _run_seg(actors, seg, existing):
    return seg_utils.process_segmentation(
        segmentation=seg,
        segmentation_id_map={1: actors[0], 2: actors[1]},
        color_map={},
        current_segment=actors[0],
        current_subgoal_segment="pick up the container at <>",
        previous_subgoal_segment="pick up the container at <>",
        current_task_name="t",
        existing_points=existing,
        existing_subgoal_filled="pick up the container at <10, 10>",
    )


def test_seg_no_refresh_untagged():
    """F4(a)：子目标未切换、actor 未打标 → 沿用缓存中心，不刷新。"""
    actors = [_Actor(), _Actor()]
    existing = [[10, 10]]
    out = _run_seg(actors, _seg_with_blocks((40, 40), (5, 50)), existing)
    assert out["segmentation_points"] == existing
    assert out["current_subgoal_segment_filled"] == "pick up the container at <10, 10>"


def test_seg_refresh_tagged_moved():
    """F4(b)：打标 8 像素且中心移动超过 8 像素 → 刷新中心并用新坐标填充 <>。"""
    actors = [_Actor(), _Actor()]
    actors[0]._robomme_refresh_on_move_px = 8
    out = _run_seg(actors, _seg_with_blocks((40, 40), (5, 50)), [[10, 10]])
    assert out["segmentation_points"] == [[40, 40]]
    assert out["current_subgoal_segment_filled"] == "pick up the container at <40, 40>"


def test_seg_no_refresh_tagged_small_move():
    """F4(c)：打标但位移不超过 8 像素 → 不刷新。"""
    actors = [_Actor(), _Actor()]
    actors[0]._robomme_refresh_on_move_px = 8
    existing = [[10, 10]]
    out = _run_seg(actors, _seg_with_blocks((18, 18), (5, 50)), existing)
    assert out["segmentation_points"] == existing
    assert out["current_subgoal_segment_filled"] == "pick up the container at <10, 10>"


# ---------------- N10：共享序数表 ----------------
def test_ordinal_word_eleventh():
    """N10：SwingXtimes 第 11 轮序数为 eleventh，前十项与原本地列表逐字相同。"""
    first_ten = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]
    assert [subgoal_language._ordinal_word(i) for i in range(10)] == first_ten
    assert subgoal_language._ordinal_word(10) == "eleventh"


# ---------------- N5：VideoPlaceButton 各档台数 ----------------
def test_vpb_configs():
    """N5：xhard3/4 台数 5，xhard1/2 台数 4；原三档 configs 逐字不变。"""
    cfg = vpb_mod.VideoPlaceButton.configs
    assert cfg["xhard3"]["targets"] == 5
    assert cfg["xhard4"]["targets"] == 5
    assert cfg["xhard1"]["targets"] == cfg["xhard2"]["targets"] == 4
    assert cfg["easy"] == {"color": 1, "additional_place": False, "swap": False, "targets": 3}
    assert cfg["medium"] == {"color": 3, "additional_place": False, "swap": False, "targets": 4}
    assert cfg["hard"] == {"color": 3, "additional_place": False, "swap": True, "targets": 4}


# ---------------- N11：VideoRepick 绝对步等待 ----------------
def test_videorepick_hold_until_step_source():
    """N11：存在 _solve_hold_until_step_xhard，等待循环以绝对步 elapsed_steps < target_step 为条件。"""
    assert hasattr(vrp_mod, "_solve_hold_until_step_xhard")
    src = inspect.getsource(vrp_mod._solve_hold_until_step_xhard)
    assert "elapsed_steps" in src and "< target_step" in src


def test_videorepick_hold_until_step_runtime():
    """N11：假 env 每次 open_gripper 推进一步，循环在 elapsed_steps>=5 时停止。"""
    env = SimpleNamespace(elapsed_steps=0)

    class _Planner:
        calls = 0

        def open_gripper(self):
            _Planner.calls += 1
            env.elapsed_steps += 1

    planner = _Planner()
    assert vrp_mod._solve_hold_until_step_xhard(env, planner, 5) is None
    assert env.elapsed_steps == 5 and _Planner.calls == 5
    # 已过目标步时不再等待
    vrp_mod._solve_hold_until_step_xhard(env, planner, 3)
    assert _Planner.calls == 5
