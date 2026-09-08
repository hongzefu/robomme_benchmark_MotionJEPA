"""原版执行和判定函数必须保留固定基线，不能在接入时改写行为。"""

import ast
from pathlib import Path
import subprocess

import pytest

from robomme_icl.specs import NATIVE_REFERENCE

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "task", ["BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"]
)
def test_native_step_and_evaluate_are_unchanged(task):
    path = f"src/robomme/robomme_env/{task}.py"
    reference = subprocess.run(
        ["git", "show", f"{NATIVE_REFERENCE}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    current = (ROOT / path).read_text()

    def methods(source):
        tree = ast.parse(source)
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == task
        )
        return {
            node.name: ast.dump(node, include_attributes=False)
            for node in cls.body
            if isinstance(node, ast.FunctionDef)
            and node.name
            in {"step", "evaluate", "_initialize_episode", "_refresh_swap_schedule"}
        }

    assert methods(reference) == methods(current)


@pytest.mark.parametrize(
    "task", ["BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"]
)
def test_native_subgoal_callables_are_not_rewritten(task):
    from collections import Counter

    path = f"src/robomme/robomme_env/{task}.py"
    original = subprocess.run(
        ["git", "show", f"{NATIVE_REFERENCE}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    def task_entries(source):
        entries = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Dict):
                keys = {key.value for key in node.keys if isinstance(key, ast.Constant)}
                if {"func", "solve", "name"} <= keys:
                    entries.append(ast.dump(node, include_attributes=False))
        return Counter(entries)

    expected = task_entries(original)
    assert expected
    assert expected == task_entries((ROOT / path).read_text())


@pytest.mark.parametrize(
    "filename",
    [
        "object_generation.py",
        "statechange.py",
        "subgoal_evaluate_func.py",
        "subgoal_planner_func.py",
        "task_goal.py",
        "planner_fail_safe.py",
    ],
)
def test_native_shared_behaviors_are_byte_identical_to_reference(filename):
    path = f"src/robomme/robomme_env/utils/{filename}"
    original = subprocess.run(
        ["git", "show", f"{NATIVE_REFERENCE}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    assert (ROOT / path).read_bytes() == original
