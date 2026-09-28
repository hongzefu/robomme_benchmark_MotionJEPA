"""新值族（xhard1～xhard4）任务目标文本：由 test_TaskGoal.py 拆出，测 robomme_hard 的 task_goal（0927 计划 R8；
官方原三档用例留在 test_TaskGoal.py、恢复为官方 1fadc0ec 原文）。"""
from pathlib import Path
import importlib.util
import sys
import types

import pytest

from tests._shared.repo_paths import find_repo_root


def _load_task_goal_module():
    repo_root = find_repo_root(__file__)
    module_path = repo_root / "src" / "robomme_hard" / "robomme_env" / "utils" / "task_goal.py"
    spec = importlib.util.spec_from_file_location("task_goal_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_task_goal_module()
get_language_goal = mod.get_language_goal
REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
from robomme_hard.robomme_env.utils.difficulty import (  # noqa: E402
    NEWVALUE_DIFFICULTIES,
    is_newvalue_difficulty,
)


class _Unwrapped:
    """Mock env.unwrapped; arbitrary attributes can be set as needed."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _Env:
    def __init__(self, unwrapped):
        self.unwrapped = unwrapped


class _Self:
    """Mock self object for called methods."""
    def __init__(self, env, **kwargs):
        self.env = env
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_self(unwrapped_attrs=None, **self_attrs):
    unwrapped = _Unwrapped(**(unwrapped_attrs or {}))
    env = _Env(unwrapped)
    return _Self(env, **self_attrs)


def _call(env_id, mock_self):
    result = get_language_goal(mock_self, env_id)
    print()
    for idx, goal in enumerate(result, start=1):
        print(f"[{env_id}] goal{idx}: {goal}")
    return result


# ── V6 新值族：VideoUnmask / ButtonUnmask 按活动档位生成抓取文本 ──

NEWVALUE_PICK_COUNTS = {"xhard1": 2, "xhard2": 3, "xhard3": 3, "xhard4": 3}


@pytest.mark.parametrize("difficulty", NEWVALUE_DIFFICULTIES)
def test_videounmask_newvalue_pick_count(difficulty):
    """四个新值档均用本档实际抓取次数生成 VideoUnmask 文本。"""
    assert is_newvalue_difficulty(difficulty)
    pick_count = NEWVALUE_PICK_COUNTS[difficulty]
    s = _make_self(
        unwrapped_attrs=dict(
            color_names=["red", "blue", "green"],
            configs={difficulty: {"pick": pick_count}},
        ),
        difficulty=difficulty,
    )
    result = _call("VideoUnmask", s)
    if pick_count == 3:
        expected = (
            "watch the video carefully, then pick up the container hiding the red cube, "
            "next pick up another container hiding the blue cube, "
            "finally pick up another container hiding the green cube"
        )
    else:
        expected = (
            "watch the video carefully, then pick up the container hiding the red cube, "
            "finally pick up another container hiding the blue cube"
        )
    assert result[0] == expected


@pytest.mark.parametrize("difficulty", NEWVALUE_DIFFICULTIES)
def test_buttonunmask_newvalue_pick_count(difficulty):
    """四个新值档均用本档实际抓取次数生成 ButtonUnmask 文本。"""
    assert is_newvalue_difficulty(difficulty)
    pick_count = NEWVALUE_PICK_COUNTS[difficulty]
    s = _make_self(
        unwrapped_attrs=dict(
            color_names=["green", "red", "blue"],
            configs={difficulty: {"pick": pick_count}},
        ),
        difficulty=difficulty,
    )
    result = _call("ButtonUnmask", s)
    if pick_count == 3:
        expected = (
            "first press the button, then pick up the container hiding the green cube, "
            "next pick up another container hiding the red cube, "
            "finally pick up another container hiding the blue cube"
        )
    else:
        expected = (
            "first press the button, then pick up the container hiding the green cube, "
            "finally pick up another container hiding the red cube"
        )
    assert result[0] == expected


@pytest.mark.parametrize("difficulty", NEWVALUE_DIFFICULTIES)
def test_unmask_newvalue_prefers_actual_pick_count(difficulty):
    """新值族外部配置与实际任务表次数不同时，文本跟随实际次数。"""
    assert is_newvalue_difficulty(difficulty)
    s = _make_self(
        unwrapped_attrs=dict(
            color_names=["red", "blue", "green"],
            configs={difficulty: {"pick": 3}},
            xhard_pick_count=2,
        ),
        difficulty=difficulty,
    )
    result = _call("VideoUnmask", s)
    assert result[0] == (
        "watch the video carefully, then pick up the container hiding the red cube, "
        "finally pick up another container hiding the blue cube"
    )


# ── ButtonUnmaskSwap: 2 branches ──

def test_buttonunmaskswap_pick_one():
    """Branch behavior test case."""
    s = _make_self(
        unwrapped_attrs=dict(color_names=["blue", "green", "red"]),
        pick_times=1,
    )
    result = _call("ButtonUnmaskSwap", s)
    assert "press both buttons" in result[0]
    assert "blue cube" in result[0]
    assert "another container" not in result[0]
    g = result[1] if len(result) > 1 else result[0]
    assert "press both buttons" in g
    assert "blue cube" in g
    assert "another container" not in g


def test_buttonunmaskswap_pick_two():
    """Branch behavior test case."""
    s = _make_self(
        unwrapped_attrs=dict(color_names=["blue", "green", "red"]),
        pick_times=2,
    )
    result = _call("ButtonUnmaskSwap", s)
    assert "press both buttons" in result[0]
    assert "another container hiding the green cube" in result[0]
    g = result[1] if len(result) > 1 else result[0]
    assert "press both buttons" in g
    assert "another container hiding the green cube" in g


# ── VideoPlaceButton: 1 branch ──

def test_videoplacebutton():
    """Branch behavior test case."""
    s = _make_self(
        target_color_name="red",
        target_target_language="after",
    )
    result = _call("VideoPlaceButton", s)
    assert "red cube" in result[0]
    assert "right after the button was pressed" in result[0]
    assert "red cube" in result[1]
    assert "where it was placed immediately after the button was pressed" in result[1]


# ── VideoPlaceOrder: 1 branch ──

def test_videoplaceorder():
    """Case: place at the N-th target in order.Inputs: target_color_name=blue, which_in_subset=3."""
    s = _make_self(
        target_color_name="blue",
        which_in_subset=3,
    )
    result = _call("VideoPlaceOrder", s)
    assert "blue cube" in result[0]
    assert "third target" in result[0]
    assert "blue cube" in result[1]
    assert "third target" in result[1]
    assert "where it was placed" in result[1]


# ── PickHighlight: 1 branch ──

def test_pickhighlight():
    """Branch behavior test case."""
    s = _make_self()
    result = _call("PickHighlight", s)
    assert "press the button" in result[0]
    assert "highlighteted" in result[0]
    assert "highlighted cubes" in result[1]
    assert "press the button again to stop" in result[1]


# ── VideoRepick: 2 branches ──
# Inputs: self.num_repeats.

def test_videorepick_once():
    """Branch behavior test case."""
    s = _make_self(num_repeats=1)
    result = _call("VideoRepick", s)
    assert "pick up the same block" in result[0]
    assert "repeatedly" not in result[0]
    assert "pick up the same cube" in result[1]
    assert "repeatedly" not in result[1]


def test_videorepick_multiple():
    """Branch behavior test case."""
    s = _make_self(num_repeats=4)
    result = _call("VideoRepick", s)
    assert "repeatedly pick up and put down" in result[0]
    assert "four times" in result[0]
    assert "same cube" in result[1]
    assert "four times" in result[1]


# ── StopCube: 1 branch ──

def test_stopcube():
    """Case: press button to stop at the N-th arrival.Inputs: stop_time=2."""
    s = _make_self(unwrapped_attrs=dict(stop_time=2))
    result = _call("StopCube", s)
    assert "second time" in result[0]
    assert "second visit" in result[1]


# ── InsertPeg: 1 branch ──

def test_insertpeg():
    """Case: insert the same peg end into the same side.Inputs: none."""
    s = _make_self()
    result = _call("InsertPeg", s)
    assert "grasp the same end" in result[0]
    assert "grasp the same peg at the same end" in result[1]
    assert "as in the video" in result[1]


# ── MoveCube: 1 branch ──

def test_movecube():
    """Case: move the cube to target in the same way as before.Inputs: none."""
    s = _make_self()
    result = _call("MoveCube", s)
    assert "move the cube to the target" in result[0]
    assert "shown in the video" in result[1]


# ── PatternLock: 1 branch ──

def test_patternlock():
    """Case: retrace the same pattern with the stick.Inputs: none."""
    s = _make_self()
    result = _call("PatternLock", s)
    assert "retrace the same pattern" in result[0]
    assert "retrace the same pattern shown in the video" in result[1]


# ── RouteStick: 1 branch ──

def test_routestick():
    """Case: use the stick to follow the same path around the rods.Inputs: none."""
    s = _make_self()
    result = _call("RouteStick", s)
    assert "navigate around the sticks" in result[0]
    assert "following the same path shown in the video" in result[1]
