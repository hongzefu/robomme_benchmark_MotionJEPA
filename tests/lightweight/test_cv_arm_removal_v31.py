"""v3.1 纯 RGB-D 去臂规则的轻量契约测试。

测试只通过公开入口 ``remove_robot_arm_sequence`` 观察生产行为，并用 256x256 合成序列钉住
以下口径：任务物体即使从独立前景移动到与机械臂接触也不能进入最终遮罩；普通双指夹爪只豁免
稳定成对出现的黑色指尖，白色指身仍须删除；没有稳定双指证据的 stick 暗色末端必须随机械臂
一起删除。另用 AST 检查遮罩生产链路没有引入仿真分割、任务名或仿真对象句柄。

静态检查刻意忽略注释与 docstring。文档需要明确写出禁止事项，不能因为其中出现相关术语就把
它误判成生产依赖；真正需要拦截的是 import、标识符、属性、数据键与动态属性读取。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from tests._shared.repo_paths import find_repo_root


pytestmark = [pytest.mark.lightweight]

CV_MODULE_RELATIVE_PATH = "scripts/data-generation-v3.1-codex/cv_arm_removal.py"
MASKED_MODULE_RELATIVE_PATH = "scripts/data-generation-v3.1-codex/masked_rgb.py"

IMAGE_SIZE = 256
TABLE_RGB = np.asarray((179, 107, 67), dtype=np.uint8)
TABLE_DEPTH_MM = np.float32(1000.0)
ARM_RGB = np.asarray((202, 202, 207), dtype=np.uint8)
ARM_DEPTH_MM = np.float32(850.0)
OBJECT_RGB = np.asarray((154, 158, 154), dtype=np.uint8)
OBJECT_DEPTH_MM = np.float32(815.0)
BLACK_TIP_RGB = np.asarray((45, 45, 45), dtype=np.uint8)


def _source(relative_path: str) -> str:
    """读取仓库内待检查模块源码。"""

    return (find_repo_root(__file__) / relative_path).read_text(encoding="utf-8")


def _load_cv_module() -> ModuleType:
    """按文件路径加载带点号和连字符目录下的 CV 模块。"""

    module_path = find_repo_root(__file__) / CV_MODULE_RELATIVE_PATH
    module_name = "cv_arm_removal_v31_under_test"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载测试模块：{module_path}")
    module = importlib.util.module_from_spec(spec)
    # dataclass 会按 cls.__module__ 回查模块，执行装饰器前必须先注册。
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cv_module() -> ModuleType:
    """返回本轮共享的生产 CV 模块。"""

    return _load_cv_module()


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """收集所有模块、类与函数 docstring 的常量节点身份。"""

    result: set[int] = set()
    containers = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, containers) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            result.add(id(first.value))
    return result


def _forbidden_identifier(name: str) -> bool:
    """判断可执行标识符是否暴露了被禁用的仿真语义入口。"""

    lowered = name.lower()
    if any(
        fragment in lowered
        for fragment in ("segmentation", "seg_id", "id_map")
    ):
        return True
    return lowered in {
        "agent",
        "agent_handle",
        "actor",
        "actor_handle",
        "articulation",
        "articulation_handle",
        "env",
        "env_id",
        "env_unwrapped",
        "environment_id",
        "link",
        "link_handle",
        "object_handle",
        "robot",
        "robot_handle",
        "robot_uid",
        "robot_uids",
        "scene",
        "task",
        "task_id",
        "task_name",
    }


def _constant_string(node: ast.AST) -> str | None:
    """若节点是常量字符串则返回其内容。"""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_leaf_name(node: ast.Call) -> str | None:
    """返回调用目标最末端的函数名。"""

    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _firewall_violations(relative_path: str) -> list[str]:
    """返回模块可执行 AST 中所有禁止依赖，忽略注释与 docstring。"""

    tree = ast.parse(_source(relative_path), filename=relative_path)
    docstrings = _docstring_constant_ids(tree)
    violations: list[str] = []
    forbidden_import_roots = {"mani_skill", "robomme", "sapien"}
    known_task_literals = {
        "binfill",
        "buttonunmask",
        "buttonunmaskswap",
        "insertpeg",
        "movecube",
        "patternlock",
        "pickhighlight",
        "pickxtimes",
        "routestick",
        "stopcube",
        "swingxtimes",
        "videoplacebutton",
        "videoplaceorder",
        "videorepick",
        "videounmask",
        "videounmaskswap",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0].lower()
                if root in forbidden_import_roots:
                    violations.append(f"禁止 import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0].lower()
            if root in forbidden_import_roots:
                violations.append(f"禁止 from {node.module} import ...")
        elif isinstance(node, ast.Name) and _forbidden_identifier(node.id):
            violations.append(f"禁止标识符 {node.id}")
        elif isinstance(node, ast.arg) and _forbidden_identifier(node.arg):
            violations.append(f"禁止参数 {node.arg}")
        elif isinstance(node, ast.Attribute) and _forbidden_identifier(node.attr):
            violations.append(f"禁止属性访问 .{node.attr}")
        elif isinstance(node, ast.keyword) and node.arg is not None:
            if _forbidden_identifier(node.arg):
                violations.append(f"禁止关键字参数 {node.arg}")
        elif isinstance(node, ast.Subscript):
            key = _constant_string(node.slice)
            if key is not None and _forbidden_identifier(key):
                violations.append(f"禁止数据键 {key!r}")
        elif isinstance(node, ast.Call):
            leaf = _call_leaf_name(node)
            # 动态属性读取和字典键读取也属于真实数据依赖，不能藏在字符串里。
            if leaf in {
                "get",
                "getattr",
                "hasattr",
                "import_module",
                "pop",
                "setattr",
                "setdefault",
            }:
                for argument in node.args:
                    value = _constant_string(argument)
                    if value is not None and _forbidden_identifier(value):
                        violations.append(f"禁止动态读取 {value!r}")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            lowered = node.value.lower()
            if lowered in known_task_literals:
                violations.append(f"禁止硬编码任务名 {node.value!r}")
            if any(
                fragment in lowered
                for fragment in ("segmentation", "seg_id", "id_map")
            ):
                violations.append(f"禁止可执行字符串 {node.value!r}")

    return sorted(set(violations))


def test_mask_production_ast_firewall() -> None:
    """遮罩生产模块不得读取仿真分割、任务名或仿真对象句柄。"""

    all_violations: list[str] = []
    for relative_path in (CV_MODULE_RELATIVE_PATH, MASKED_MODULE_RELATIVE_PATH):
        all_violations.extend(
            f"{relative_path}: {detail}"
            for detail in _firewall_violations(relative_path)
        )
    assert not all_violations, "\n".join(all_violations)

    tree = ast.parse(_source(CV_MODULE_RELATIVE_PATH))
    public_entry = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "remove_robot_arm_sequence"
    )
    positional = [argument.arg for argument in public_entry.args.args]
    assert positional == ["rgb_frames", "depth_frames", "config"], (
        "公开入口只能接收 RGB、深度与纯 CV 配置，禁止追加任务或仿真对象参数"
    )
    assert public_entry.args.vararg is None
    assert public_entry.args.kwarg is None
    assert not public_entry.args.kwonlyargs


def _empty_episode(frame_count: int) -> tuple[np.ndarray, np.ndarray]:
    """建立固定棕色桌面与恒定桌面深度。"""

    rgb = np.empty(
        (frame_count, IMAGE_SIZE, IMAGE_SIZE, 3),
        dtype=np.uint8,
    )
    rgb[...] = TABLE_RGB
    depth = np.full(
        (frame_count, IMAGE_SIZE, IMAGE_SIZE),
        TABLE_DEPTH_MM,
        dtype=np.float32,
    )
    return rgb, depth


def _paint(
    rgb: np.ndarray,
    depth: np.ndarray,
    frame_index: int,
    rows: slice,
    columns: slice,
    color: np.ndarray,
    depth_mm: np.float32,
) -> None:
    """在单帧矩形区域写入颜色与深度。"""

    rgb[frame_index, rows, columns] = color
    depth[frame_index, rows, columns] = depth_mm


def _object_contact_episode() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """构造任务物体先独立、后与机械臂侧面接触的序列。"""

    frame_count = 24
    rgb, depth = _empty_episode(frame_count)
    object_truth = np.zeros(rgb.shape[:3], dtype=bool)
    arm_core = np.zeros_like(object_truth)

    # 前十四帧保持独立，中间两帧接近，最后八帧与臂右侧直接相邻。
    object_lefts = [176] * 14 + [158, 144] + [132] * 8
    for frame_index, object_left in enumerate(object_lefts):
        _paint(
            rgb,
            depth,
            frame_index,
            slice(0, 180),
            slice(108, 132),
            ARM_RGB,
            ARM_DEPTH_MM,
        )
        arm_core[frame_index, 36:126, 113:127] = True

        rows = slice(146, 164)
        columns = slice(object_left, object_left + 18)
        _paint(
            rgb,
            depth,
            frame_index,
            rows,
            columns,
            OBJECT_RGB,
            OBJECT_DEPTH_MM,
        )
        object_truth[frame_index, rows, columns] = True

    return rgb, depth, object_truth, arm_core


def _gripper_episode() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """构造随时间平移的普通双指夹爪及成对黑色指尖。"""

    frame_count = 18
    rgb, depth = _empty_episode(frame_count)
    black_tip_truth = np.zeros(rgb.shape[:3], dtype=bool)
    white_finger_truth = np.zeros_like(black_tip_truth)

    for frame_index in range(frame_count):
        center = 116 + frame_index // 3
        _paint(
            rgb,
            depth,
            frame_index,
            slice(0, 132),
            slice(center - 14, center + 14),
            ARM_RGB,
            ARM_DEPTH_MM,
        )
        _paint(
            rgb,
            depth,
            frame_index,
            slice(120, 140),
            slice(center - 18, center + 18),
            ARM_RGB,
            ARM_DEPTH_MM,
        )

        left_columns = slice(center - 15, center - 9)
        right_columns = slice(center + 9, center + 15)
        for columns in (left_columns, right_columns):
            _paint(
                rgb,
                depth,
                frame_index,
                slice(136, 168),
                columns,
                ARM_RGB,
                ARM_DEPTH_MM,
            )
            white_finger_truth[frame_index, 143:157, columns] = True
            _paint(
                rgb,
                depth,
                frame_index,
                slice(160, 168),
                columns,
                BLACK_TIP_RGB,
                ARM_DEPTH_MM,
            )
            black_tip_truth[frame_index, 160:168, columns] = True

    return rgb, depth, black_tip_truth, white_finger_truth


def _stick_episode() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """构造只有单条暗色末端、没有稳定双指证据的 stick 序列。"""

    frame_count = 18
    rgb, depth = _empty_episode(frame_count)
    stick_core = np.zeros(rgb.shape[:3], dtype=bool)

    for frame_index in range(frame_count):
        center = 124 + frame_index // 4
        _paint(
            rgb,
            depth,
            frame_index,
            slice(0, 148),
            slice(center - 13, center + 13),
            ARM_RGB,
            ARM_DEPTH_MM,
        )
        _paint(
            rgb,
            depth,
            frame_index,
            slice(140, 220),
            slice(center - 3, center + 3),
            BLACK_TIP_RGB,
            ARM_DEPTH_MM,
        )
        # 避开边缘形态学影响，只检查暗色长条内部。
        stick_core[frame_index, 151:212, center - 2 : center + 2] = True

    return rgb, depth, stick_core


@pytest.fixture(scope="module")
def object_contact_result(cv_module: ModuleType) -> dict[str, Any]:
    """运行任务物体接触序列。"""

    rgb, depth, object_truth, arm_core = _object_contact_episode()
    original = rgb.copy()
    result = cv_module.remove_robot_arm_sequence(rgb, depth)
    return {
        "rgb": rgb,
        "original": original,
        "object_truth": object_truth,
        "arm_core": arm_core,
        "result": result,
    }


@pytest.fixture(scope="module")
def gripper_result(cv_module: ModuleType) -> dict[str, Any]:
    """运行普通双指夹爪序列。"""

    rgb, depth, black_tip_truth, white_finger_truth = _gripper_episode()
    original = rgb.copy()
    result = cv_module.remove_robot_arm_sequence(rgb, depth)
    return {
        "rgb": rgb,
        "original": original,
        "black_tip_truth": black_tip_truth,
        "white_finger_truth": white_finger_truth,
        "result": result,
    }


@pytest.fixture(scope="module")
def stick_result(cv_module: ModuleType) -> dict[str, Any]:
    """运行无双指证据的 stick 序列。"""

    rgb, depth, stick_core = _stick_episode()
    original = rgb.copy()
    result = cv_module.remove_robot_arm_sequence(rgb, depth)
    return {
        "rgb": rgb,
        "original": original,
        "stick_core": stick_core,
        "result": result,
    }


def test_low_saturation_object_is_preserved_before_and_during_contact(
    object_contact_result: dict[str, Any],
) -> None:
    """低饱和任务物体先分离后接触机械臂，全程都不得进入最终遮罩。"""

    result = object_contact_result["result"]
    masks = np.asarray(result.masks)
    object_truth = object_contact_result["object_truth"]
    arm_core = object_contact_result["arm_core"]

    assert not np.any(masks[object_truth]), "任务物体像素被最终遮罩误删"
    assert np.all(masks[arm_core]), "测试必须同时证明边缘进入的机械臂确实被遮罩"


def test_paired_black_gripper_tips_are_preserved_but_white_fingers_are_masked(
    gripper_result: dict[str, Any],
) -> None:
    """稳定成对的黑色小块应豁免，相邻白色指身仍须遮罩。"""

    result = gripper_result["result"]
    masks = np.asarray(result.masks)
    black_tip_truth = gripper_result["black_tip_truth"]
    white_finger_truth = gripper_result["white_finger_truth"]

    tip_sums = gripper_result["rgb"].astype(np.uint16).sum(axis=-1)[
        black_tip_truth
    ]
    assert np.all(tip_sums <= 300), "合成黑色指尖必须满足 v2.1 的亮度定义"
    assert not np.any(masks[black_tip_truth]), "稳定成对的黑色指尖没有被豁免"
    assert np.all(masks[white_finger_truth]), "白色指身被错误地一起豁免"


def test_stick_dark_pixels_are_not_exempt_without_stable_finger_pair(
    stick_result: dict[str, Any],
) -> None:
    """没有稳定双指证据时，stick 的黑色像素必须随机械臂一起遮罩。"""

    result = stick_result["result"]
    masks = np.asarray(result.masks)
    stick_core = stick_result["stick_core"]

    stick_sums = stick_result["rgb"].astype(np.uint16).sum(axis=-1)[stick_core]
    assert np.all(stick_sums <= 300), "合成 stick 必须落入同一黑色阈值"
    assert np.all(masks[stick_core]), "单条暗色 stick 被误判成双指夹爪并豁免"


@pytest.mark.parametrize(
    "fixture_name",
    ["object_contact_result", "gripper_result", "stick_result"],
)
def test_public_result_shape_dtype_and_untouched_contract(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """公开结果保持 shape、dtype，且遮罩外像素与输入逐位相同。"""

    record = request.getfixturevalue(fixture_name)
    result = record["result"]
    rgb = record["rgb"]
    original = record["original"]
    frames = np.asarray(result.frames)
    masks = np.asarray(result.masks)

    assert np.array_equal(rgb, original), "公开入口不得就地改写输入 RGB"
    assert frames.shape == rgb.shape
    assert frames.dtype == np.uint8
    assert masks.shape == rgb.shape[:3]
    assert masks.dtype == np.bool_
    assert np.array_equal(frames[~masks], rgb[~masks])
