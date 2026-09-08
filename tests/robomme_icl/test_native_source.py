"""原版执行和判定函数必须保留固定基线，不能在接入时改写行为。"""

import ast
from pathlib import Path
import subprocess

import pytest

from robomme_icl.specs import NATIVE_REFERENCE

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("task", ["BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"])
def test_native_step_and_evaluate_are_unchanged(task):
    path = f"src/robomme/robomme_env/{task}.py"
    reference = subprocess.run(["git", "show", f"{NATIVE_REFERENCE}:{path}"],
                               cwd=ROOT, check=True, capture_output=True, text=True).stdout
    current = (ROOT / path).read_text()
    def methods(source):
        tree = ast.parse(source)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == task)
        return {node.name: ast.dump(node, include_attributes=False) for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name in {"step", "evaluate", "_initialize_episode", "_refresh_swap_schedule"}}
    assert methods(reference) == methods(current)
