"""把 GT segmentation 落盘子类的结构铁律固化下来（AST 静态断言，不起仿真）。

这些不是风格偏好，是「只增不改」能否成立的根据。它们没法靠跑一次生成来保证——一次跑通
不代表下次改动不会破坏。

**铁律一：只增量、不重写。** ``RobommeRecordWrapperGT`` 只允许 override ``__init__`` /
``reset`` / ``close``，且都必须调用同名的 ``super()`` 方法。一旦有人为了方便把父类的
``close()`` 整段抄过来改，「父类零改动」这个前提就没了。

**铁律二：不得 override ``step()``。** 这是重构后新增的契约。历史上这一层挂过逐帧采集
（每步 0.5–1.0 ms），本链路把它整体删除后，``step()`` 回到父类实现，于是「新增采集会不会
挤掉规划器那 1 秒墙钟预算、进而改变 RRTStar 的采样结果」这个风险结构性归零。谁要是再往
``step()`` 里加东西，这条会立刻红。

**铁律三：``close()`` 必须先抄 buffer 再调 ``super().close()``。** 父类 ``close()`` 会
``clear()`` buffer，抄晚了就什么都没有了。
"""

from __future__ import annotations

import ast

import pytest

from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]


WRAPPER_RELATIVE_PATH = "scripts/data-generation/gt-data/record_wrapper.py"
CLASS_NAME = "RobommeRecordWrapperGT"
ALLOWED_OVERRIDES = {"__init__", "reset", "close"}


def _wrapper_class() -> ast.ClassDef:
    repo_root = find_repo_root(__file__)
    source = (repo_root / WRAPPER_RELATIVE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == CLASS_NAME:
            return node
    raise AssertionError(f"没有找到 {CLASS_NAME} 类定义")


def _is_super_call(node: ast.AST, method_name: str) -> bool:
    """判断某个节点是不是 super().<method_name>(...) 调用。"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != method_name:
        return False
    inner = func.value
    return (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "super"
    )


def test_必须直接继承父类而不是复制一份改():
    node = _wrapper_class()
    base_names = {base.id for base in node.bases if isinstance(base, ast.Name)}
    assert "RobommeRecordWrapper" in base_names


def test_override_面收敛在三个生命周期方法内():
    node = _wrapper_class()
    defined = {
        item.name
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    extra = defined - ALLOWED_OVERRIDES
    assert not extra, f"出现了计划外的 override：{sorted(extra)}"


def test_不得override_step_热路径必须零开销():
    """铁律二：step() 一旦被 override，规划器墙钟预算就可能被挤占。"""
    node = _wrapper_class()
    defined = {
        item.name
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "step" not in defined, (
        "step() 被 override 了：本链路的 GT segmentation 全部在 close() 里落盘，"
        "热路径必须保持零开销，否则会动到 RRTStar 的采样结果"
    )


@pytest.mark.parametrize("method_name", sorted(ALLOWED_OVERRIDES))
def test_每个override都调用super(method_name: str):
    node = _wrapper_class()
    target = next(
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == method_name
    )
    assert any(
        _is_super_call(child, method_name) for child in ast.walk(target)
    ), f"{method_name}() 没有调用 super().{method_name}()"


def test_close先抄buffer再调super():
    """铁律三：父类 close() 会 clear buffer，抄晚了就什么都没有了。"""
    node = _wrapper_class()
    close = next(
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == "close"
    )
    super_close_index: int | None = None
    buffer_read_index: int | None = None
    for index, statement in enumerate(close.body):
        for child in ast.walk(statement):
            if _is_super_call(child, "close") and super_close_index is None:
                super_close_index = index
            # self.buffer 的任何读取
            if (
                isinstance(child, ast.Attribute)
                and child.attr == "buffer"
                and isinstance(child.value, ast.Name)
                and child.value.id == "self"
                and buffer_read_index is None
            ):
                buffer_read_index = index

    assert super_close_index is not None, "close() 没有调用 super().close()"
    assert buffer_read_index is not None, "close() 没有读 self.buffer"
    assert buffer_read_index < super_close_index, (
        "close() 在 super().close() 之后才读 self.buffer——"
        "父类会先 clear()，那时 buffer 已经空了"
    )


def test_seg_id表在reset里冻结():
    """场景在 super().reset() 之后才建好，且 close() 会拆场景——只能在 reset 里冻结。"""
    node = _wrapper_class()
    reset = next(
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == "reset"
    )
    names = {
        child.func.id
        for child in ast.walk(reset)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    assert "SegIdTable" in names, "reset() 没有冻结 seg_id 表"
