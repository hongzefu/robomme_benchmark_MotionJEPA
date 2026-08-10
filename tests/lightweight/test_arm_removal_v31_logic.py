"""v3.1-claude 纯 CV 口径的 AST 防火墙 + 变体契约结构检查。

与 v3 的 ``test_arm_removal_logic.py`` 同一思路：「纯 CV 定位、不碰仿真真值」这条
口径靠测试在结构上钉死，不靠人记住。本文件覆盖 ``scripts/data-generation-v3.1-claude/``：

1. **import 白名单**：``cv_base.py`` 与 ``variants/*.py`` 只准 import
   numpy / cv2 / 标准库 / 本目录基座 ``cv_base``；h5py、scipy、torch、仓库内其他
   模块一律禁止（h5py 只允许出现在渲染入口 ``render_variant_outputs.py``）。
2. **分割标识符禁用**：全部源码不得出现任何仿真分割相关标识符。
3. **变体契约**：每个变体模块必须在模块层定义 ``NAME`` / ``DESCRIPTION`` /
   ``compute_masks``，且变体之间不得互相 import。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V31_DIR = REPO_ROOT / "scripts" / "data-generation-v3.1-claude"
VARIANTS_DIR = V31_DIR / "variants"

# 标准库以外允许的顶层包；cv_base 是本目录基座、variants 包自身的相对导入不经此表
_ALLOWED_TOP_LEVEL = {"numpy", "cv2", "cv_base"}

# 出现即失败的分割相关标识符片段（大小写不敏感）
_FORBIDDEN_FRAGMENTS = ("segmentation", "seg_id", "actor_id", "link_name", "h5py", "scipy", "torch")

# 渲染入口另行豁免 h5py（它要读 h5，本就不属于「纯 CV 判定层」）
_RENDER_EXEMPT = {"h5py"}


def _std_lib(name: str) -> bool:
    return name in sys.stdlib_module_names


def _variant_sources() -> list[Path]:
    files = sorted(VARIANTS_DIR.glob("*.py"))
    assert files, f"variants 目录为空：{VARIANTS_DIR}"
    return files


def _iter_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                yield node.module.split(".")[0]


def test_cv_base_and_variants_import_whitelist():
    for path in [V31_DIR / "cv_base.py", *_variant_sources()]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for top in _iter_imports(tree):
            assert _std_lib(top) or top in _ALLOWED_TOP_LEVEL, (
                f"{path.name} import 了白名单外的 {top!r}（只准 numpy/cv2/标准库/cv_base）"
            )


def _identifiers(tree: ast.AST) -> set[str]:
    """收集源码中实际使用的标识符（不含注释与 docstring 散文——散文里描述
    「禁止 h5py/scipy」本身不应触发防火墙）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.name)
            if node.asname:
                names.add(node.asname)
    return {name.lower() for name in names}


def test_no_segmentation_identifiers():
    for path in [V31_DIR / "cv_base.py", V31_DIR / "render_variant_outputs.py", *_variant_sources()]:
        identifiers = _identifiers(ast.parse(path.read_text(encoding="utf-8")))
        exempt = _RENDER_EXEMPT if path.name == "render_variant_outputs.py" else set()
        for fragment in _FORBIDDEN_FRAGMENTS:
            if fragment in exempt:
                continue
            hits = {name for name in identifiers if fragment in name}
            assert not hits, f"{path.name} 出现禁用标识符 {sorted(hits)}（命中片段 {fragment!r}）"


def test_variant_contract_and_isolation():
    variant_names = {p.stem for p in _variant_sources() if p.stem != "__init__"}
    for path in _variant_sources():
        if path.stem == "__init__":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top_level = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert "NAME" in top_level, f"{path.name} 缺少模块层 NAME"
        assert "DESCRIPTION" in top_level, f"{path.name} 缺少模块层 DESCRIPTION"
        assert "compute_masks" in functions, f"{path.name} 缺少 compute_masks 函数"
        for top in _iter_imports(tree):
            assert top not in (variant_names - {path.stem}), (
                f"{path.name} import 了另一个变体 {top!r}（变体之间必须互相独立）"
            )
