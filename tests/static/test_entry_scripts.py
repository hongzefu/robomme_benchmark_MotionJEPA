"""L0：顶层入口（C18 入口白名单、生产不依赖 tests、``run_example.EPISODE_LIMITS`` 与官方元数据一致）。

- ``evaluation_hard.py`` 与上游 ``evaluation.py`` 恰好差 3 个单行 hunk：import、``dataset="test-hard"``、``max_steps``；
  ``max_steps`` 的数值不断言（计划 Q16 待定），只断言它在同一位置、仍是整数字面值关键字参数。
- ``scripts/*.py`` 恰好四个入口（AGENTS.md P1）。
- ``scripts/`` 与 ``challenge_interface/`` 的生产代码不 import ``tests``（AST 收集 import 语句，L0 允许）。
"""
from __future__ import annotations

import ast
import difflib
import json
import re
import typing
from pathlib import Path

import pytest

from tests._support.loaders import REPO, load_script

SCRIPTS = REPO / "scripts"
ENTRY_SET = {"dataset_replay.py", "evaluation.py", "run_example.py", "evaluation_hard.py"}
PRODUCTION_DIRS = (REPO / "scripts", REPO / "challenge_interface")


# ---------------------------------------------------------------- evaluation_hard 与 evaluation 的差异


def single_line_hunks(old: str, new: str) -> list[tuple[int, str, str]]:
    """逐行差异；每块必须是「同一行号上一行换一行」，否则返回 None 表示形态不合。

    返回 [(行号(1 起), 旧行, 新行)]。
    """
    a, b = old.splitlines(), new.splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "replace" or i2 - i1 != 1 or j2 - j1 != 1 or i1 != j1:
            return None
        out.append((i1 + 1, a[i1], b[j1]))
    return out


def _builder_call(tree: ast.AST) -> ast.Call:
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "BenchmarkEnvBuilder"]
    assert len(calls) == 1
    return calls[0]


def test_evaluation_hard_diff_is_exactly_three_single_line_hunks():
    old = (SCRIPTS / "evaluation.py").read_text(encoding="utf-8")
    new = (SCRIPTS / "evaluation_hard.py").read_text(encoding="utf-8")
    hunks = single_line_hunks(old, new)
    assert hunks is not None and len(hunks) == 3, hunks
    (l1, o1, n1), (l2, o2, n2), (l3, o3, n3) = hunks
    # 1) import：只把包名换成 robomme_hard。
    assert o1 == "from robomme.env_record_wrapper import BenchmarkEnvBuilder"
    assert n1 == "from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder"
    tree = ast.parse(new)
    first_def = min(n.lineno for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)))
    assert l1 < first_def
    # 2) dataset：test → test-hard，缩进不变。
    assert o2.strip() == 'dataset="test",' and n2.strip() == 'dataset="test-hard",'
    assert o2[: len(o2) - len(o2.lstrip())] == n2[: len(n2) - len(n2.lstrip())]
    # 3) max_steps：只断言仍是整数关键字参数、缩进不变，数值不断言（Q16）。
    pat = re.compile(r"^(\s*)max_steps=\d+,")
    mo, mn = pat.match(o3), pat.match(n3)
    assert mo and mn and mo.group(1) == mn.group(1)
    # 位置：后两处恰是 BenchmarkEnvBuilder(...) 调用的 dataset／max_steps 关键字参数。
    kw = {k.arg: k for k in _builder_call(tree).keywords}
    assert kw["dataset"].value.lineno == l2
    assert isinstance(kw["dataset"].value, ast.Constant) and kw["dataset"].value.value == "test-hard"
    assert kw["max_steps"].value.lineno == l3
    assert isinstance(kw["max_steps"].value, ast.Constant) and isinstance(kw["max_steps"].value.value, int)


def test_single_line_hunks_negatives():
    base = "a\nb\nc\n"
    assert single_line_hunks(base, base) == []
    assert single_line_hunks(base, "a\nB\nc\n") == [(2, "b", "B")]
    assert single_line_hunks(base, "a\nb\nx\nc\n") is None  # 多一行
    assert single_line_hunks(base, "a\nc\n") is None  # 少一行
    assert single_line_hunks(base, "a\nB\nC\n") is None  # 两行连成一块


# ---------------------------------------------------------------- 入口清单


def test_scripts_top_level_has_exactly_four_entries():
    assert {p.name for p in SCRIPTS.glob("*.py")} == ENTRY_SET


# ---------------------------------------------------------------- 生产代码不 import tests


def imports_of_tests(source: str) -> list[str]:
    """源码中指向 ``tests`` 包的导入（import／from-import／importlib.import_module／__import__ 字面值）。"""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names if a.name == "tests" or a.name.startswith("tests.")]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "tests" or node.module.startswith("tests."):
                hits.append(node.module)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            arg = node.args[0].value
            if name in ("import_module", "__import__") and isinstance(arg, str) \
                    and (arg == "tests" or arg.startswith("tests.")):
                hits.append(arg)
    return hits


def _production_py() -> list[Path]:
    out = []
    for d in PRODUCTION_DIRS:
        out += [p for p in d.rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(out)


def test_production_code_does_not_import_tests():
    files = _production_py()
    assert files
    bad = {str(p.relative_to(REPO)): h for p in files if (h := imports_of_tests(p.read_text(encoding="utf-8")))}
    assert bad == {}


@pytest.mark.parametrize("src", [
    "import tests\n",
    "import tests._support.loaders as L\n",
    "from tests._support import loaders\n",
    "from tests import conftest\n",
    "import importlib\nimportlib.import_module('tests._support.loaders')\n",
    "__import__('tests')\n",
])
def test_imports_of_tests_catches(src):
    assert imports_of_tests(src)


@pytest.mark.parametrize("src", [
    "import testscenario\n",
    "from .tests import x\n",
    "from robomme import tests_helper\n",
    "s = 'import tests'\n",
])
def test_imports_of_tests_ignores_non_tests(src):
    assert imports_of_tests(src) == []


# ---------------------------------------------------------------- run_example.EPISODE_LIMITS


def test_episode_limits_match_official_metadata():
    run_example = load_script("run_example.py")
    limits = run_example.EPISODE_LIMITS
    meta_root = REPO / "src" / "robomme" / "env_metadata"
    assert set(limits) == {p.name for p in meta_root.iterdir() if p.is_dir()}
    assert set(typing.get_args(run_example.DatasetType)) == set(limits)
    tasks = set(typing.get_args(run_example.TaskID)) - {"All"}
    for split, limit in limits.items():
        files = sorted((meta_root / split).glob("record_dataset_*_metadata.json"))
        seen = set()
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            seen.add(d["env_id"])
            assert d["record_count"] == limit, (split, f.name)
            assert sorted(r["episode"] for r in d["records"]) == list(range(limit)), (split, f.name)
        assert seen == tasks, split
