"""固化「`scripts/` 下的代码不得依赖 `tests/`」这条不变量（2026-09-11 用户要求：
候选分布产生、生成 h5、对拍、出图都不放在 tests 内、不依赖 tests，全部放在 scripts/）。

按 AST 取每个 `scripts/**/*.py` 的实际 import，不看字符串与注释；命中 `tests`
顶层模块名（`import tests…` / `from tests… import`）即失败。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _imported_top_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_scripts_下没有任何模块导入_tests():
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(names)
        for path in sorted(SCRIPTS.rglob("*.py"))
        if "__pycache__" not in path.parts
        for names in [_imported_top_names(path)]
        if "tests" in names
    }
    assert offenders == {}, offenders
