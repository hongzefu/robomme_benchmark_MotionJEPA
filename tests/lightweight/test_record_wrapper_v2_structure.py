"""把 v2 薄子类的两条结构铁律固化下来。

这两条不是风格偏好，是「只增不改」能否成立的根据。它们没法靠跑一次生成来保证——一次跑通不
代表下次改动不会破坏，所以用 AST 静态断言钉死。

**铁律一：只增量、不重写。** ``RobommeRecordWrapperV2`` 只允许 override ``__init__`` /
``reset`` / ``step`` / ``close``，且这四个方法都必须调用同名的 ``super()`` 方法。一旦有人为了
方便把父类的 ``close()`` 整段抄过来改，「父类零改动」这个前提就没了，自对拍也就失去意义。

**铁律二：flow 采集必须在 ``super().step()`` 之后。** 这是 ``joint_action`` 能逐位一致的根本
原因——采集只读仿真状态、不消费随机数，且发生在这一步的随机数全部消费完之后，因此不可能改变
仿真与规划的轨迹。若哪天有人把采集挪到 ``super().step()`` 之前，逐位一致会立刻失效，而且症状
会表现为「某些 episode 偶尔对不上」这种极难定位的形式。
"""

from __future__ import annotations

import ast

import pytest

from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]


WRAPPER_RELATIVE_PATH = "scripts/data-generation-v2/record_wrapper_v2.py"
ALLOWED_OVERRIDES = {"__init__", "reset", "step", "close"}


def _wrapper_class() -> ast.ClassDef:
    repo_root = find_repo_root(__file__)
    source = (repo_root / WRAPPER_RELATIVE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RobommeRecordWrapperV2":
            return node
    raise AssertionError("没有找到 RobommeRecordWrapperV2 类定义")


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


def test_subclass_inherits_from_original_wrapper():
    """必须直接继承父类，而不是复制一份改。"""
    node = _wrapper_class()
    base_names = {base.id for base in node.bases if isinstance(base, ast.Name)}
    assert "RobommeRecordWrapper" in base_names


def test_only_the_three_lifecycle_methods_are_overridden():
    """override 面必须收敛在 __init__ / reset / step / close 之内。"""
    node = _wrapper_class()
    defined = {
        item.name
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # flow_capture_ms_per_step 是新增的只读属性，不是 override，单独放行
    extra = defined - ALLOWED_OVERRIDES - {"flow_capture_ms_per_step"}
    assert not extra, f"出现了计划外的 override：{sorted(extra)}"


@pytest.mark.parametrize("method_name", sorted(ALLOWED_OVERRIDES))
def test_each_override_calls_super(method_name: str):
    """每个 override 都必须把活先交给父类。"""
    node = _wrapper_class()
    target = next(
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == method_name
    )
    assert any(
        _is_super_call(child, method_name) for child in ast.walk(target)
    ), f"{method_name}() 没有调用 super().{method_name}()"


def test_flow_capture_happens_after_super_step():
    """step() 里对 buffer 的 flow 写入必须严格排在 super().step() 之后。

    比较的是两者在函数体顶层语句序列中的位置：super().step() 所在的语句下标，必须小于
    任何出现 ``_flow`` 赋值的语句下标。
    """
    node = _wrapper_class()
    step = next(
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == "step"
    )

    super_step_index: int | None = None
    flow_write_indices: list[int] = []
    for index, statement in enumerate(step.body):
        for child in ast.walk(statement):
            if _is_super_call(child, "step") and super_step_index is None:
                super_step_index = index
            if (
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and child.value == "_flow"
            ):
                flow_write_indices.append(index)

    assert super_step_index is not None, "step() 里没有调用 super().step()"
    assert flow_write_indices, "step() 里没有出现 _flow 写入，flow 采集消失了"
    assert min(flow_write_indices) > super_step_index, (
        "flow 采集出现在 super().step() 之前或同一条语句里——"
        "这会让采集参与到随机数消费顺序中，joint_action 的逐位一致立刻失效"
    )


def test_close_snapshots_buffer_before_super_close():
    """close() 必须先抄走 flow 数据，再调 super().close()。

    父类 close() 结尾会 clear buffer，顺序反了就什么都抄不到，flow 会静默丢失。
    """
    node = _wrapper_class()
    close = next(
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == "close"
    )

    super_close_index: int | None = None
    buffer_read_indices: list[int] = []
    for index, statement in enumerate(close.body):
        for child in ast.walk(statement):
            if _is_super_call(child, "close") and super_close_index is None:
                super_close_index = index
            if isinstance(child, ast.Attribute) and child.attr == "buffer":
                buffer_read_indices.append(index)

    assert super_close_index is not None, "close() 里没有调用 super().close()"
    assert buffer_read_indices, "close() 里没有读取 buffer，flow 数据抄不到"
    assert min(buffer_read_indices) < super_close_index, (
        "close() 在 super().close() 之后才读 buffer——"
        "父类那时已经把 buffer 清空了，flow 会静默丢失"
    )
