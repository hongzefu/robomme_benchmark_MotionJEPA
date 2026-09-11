#!/usr/bin/env python3
"""无 seed 独立生成：seed 由公式自算，失败自动 attempt+1 重试。

与旧的复现型入口（读 train metadata 里的死 seed、单次尝试、锁死 GPU 0；该脚本已随
``scripts/data-generation/`` 在 newtask-v2 第五步退出工作树，可从 Git 历史追溯）的差别：

* seed 不再读表，由 ``seed_layout`` 按 ``offset + env_code*env_block + episode*100 + attempt`` 现算
* 单条失败不再让整体 raise，而是 attempt+1 重新入队，直到成功或达到上限
* 每卡一个进程池、进程终身绑卡，支持多 GPU
* 每 worker 的 CPU 线程被压到 1（骨架完全没设，32 核上会严重过度订阅）
* 结果边跑边写 JSONL，中途崩溃不丢已完成的部分
* 不合并 h5（合并见 ``--merge-only``）、不做 replay、不与官方 reference 做数值比对

env kwargs、FailRecover 分档、planner 的 screw×3 → RRT*×3 重试、成功判定，
均与骨架逐字相同 —— 本脚本的用途之一是验证当前环境代码与 2025-12 环境代码的行为等价性，
这些口径一旦改动，比对结果就失去意义。

平铺说明（newtask-v2 10.0）：本文件从 ``scripts/data-generation-newSeed/`` 迁到根 ``scripts/``，
并入了原先散在别处的四组函数：``validate_generated_dataset_contract.py`` 的轨迹末帧检查、
``write_generation_report.py`` 的原子写、``merge_episode_h5.py`` 的最小合并逻辑，
以及本轮新增的原版采样配置提取与校验。同一个 main() 提供三种入口模式：

* ``--extract-config <JSON>``：只读源码 AST，导出或（``--check-config``）核对原值快照
* ``--merge-only``：把每 episode 的 h5 合并成 ``record_dataset_{task}.h5``
* 不指定上述模式：常规生成，可选 ``--sampling-config`` 显式传入原版采样输入

分流发生在建进程池与导入仿真之前；顶层与被顶层导入的模块都不得出现 torch/sapien/cv2/robomme，
因为 spawn 子进程会以 ``__mp_main__`` 重跑本模块顶层，而那早于 ``_pool_init()`` 写 CUDA_VISIBLE_DEVICES。
"""

from __future__ import annotations

import os


# ── 线程限制必须在 import numpy 之前生效 ──────────────────────────────────────
# OpenBLAS/libgomp 都是在 .so 加载时读取线程数的，放到进程池 initializer 里已经太晚：
# spawn 的子进程 bootstrap 会重跑本模块顶层（为了还原 _worker 的定义），
# 那时 numpy 已经 import 完毕。所以只能放在顶层、且在 import numpy 之前。
# 父进程解析完 CLI 后会改写 NEWSEED_LIMIT_THREADS 再建池，子进程继承后在这里读到。
_THREAD_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "OPENCV_FOR_THREADS_NUM",
)
LIMIT_THREADS_ENV = "NEWSEED_LIMIT_THREADS"


def _apply_thread_env(value: str) -> None:
    for name in _THREAD_VARS:
        os.environ[name] = value


def _clear_thread_env() -> None:
    for name in _THREAD_VARS:
        os.environ.pop(name, None)


if os.environ.get(LIMIT_THREADS_ENV, "1") != "0":
    _apply_thread_env("1")

import argparse  # noqa: E402
import ast  # noqa: E402
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import multiprocessing as mp  # noqa: E402
import re  # noqa: E402
import resource  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from collections import deque  # noqa: E402
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait  # noqa: E402
from concurrent.futures.process import BrokenProcessPool  # noqa: E402
from dataclasses import dataclass, field, replace  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Mapping, Sequence  # noqa: E402

import h5py  # noqa: E402
import numpy as np  # noqa: E402


SCRIPT_DIR = Path(__file__).resolve().parent
# 保留 sys.path 插入：让非脚本入口（测试的 importlib、python -m）也能解析同级 seed_layout
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from seed_layout import (  # noqa: E402
    DEFAULT_LAYOUT,
    LAYOUTS,
    MAX_ATTEMPTS,
    MAX_EPISODES,
    difficulty_for,
    get_layout,
    parse_difficulty_ratio,
    parse_tasks,
)


REPO_ROOT = SCRIPT_DIR.parent
SRC_ROOT = REPO_ROOT / "src"
STICK_TASKS = frozenset(("PatternLock", "RouteStick"))
DEFAULT_WORKERS = 20
DEFAULT_DIFFICULTY_RATIO = "211"
# 每个池进程跑多少个 job 后强制回收：太小则反复付 import/CUDA 上下文成本，
# 太大则 RecordWrapper 的显存/内存残留会跨 episode 累积、且一次段错误牵连更多 job。
DEFAULT_MAX_TASKS_PER_CHILD = 8
# 同一个 episode 连续这么多次非任务性失败（真 bug、池崩溃）就放弃，
# 避免对着一个必然复现的 bug 空转到 attempt 上限
MAX_NON_TASK_STRIKES = 3

TIMESTEP_RE = re.compile(r"^timestep_(\d+)$")

# 池进程私有：由 initializer 填，worker 回传供审计（证明确实绑到了预期的物理卡）
_BOUND: dict[str, Any] = {}


class DatasetGenerationError(RuntimeError):
    """生成过程违反约定。"""


class PlannerExhausted(RuntimeError):
    """planner 的 screw 与 RRTStar 重试均已耗尽。"""


class MergeError(RuntimeError):
    """合并的输入不完整或结构不符。"""


class SamplingConfigError(RuntimeError):
    """采样配置的提取、校验或来源核对失败。"""


# ── 迁自 write_generation_report.py ────────────────────────────────────────────


def write_text_atomic(path: Path, value: str) -> None:
    """Atomically replace with a temporary file in the same directory to avoid leaving a partial report after an interruption."""
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


# ── 迁自 validate_generated_dataset_contract.py ────────────────────────────────


def timestep_indices(group: h5py.Group, source: str) -> tuple[list[int], list[str]]:
    """Parse numeric timestep names and strictly validate contiguity; valid setup groups do not count as timesteps."""
    errors: list[str] = []
    indices: list[int] = []
    for name in group.keys():
        if name == "setup":
            continue
        match = TIMESTEP_RE.fullmatch(name)
        if match is None or not isinstance(group[name], h5py.Group):
            errors.append(f"{source}: invalid timestep {name!r}")
        else:
            indices.append(int(match.group(1)))
    indices.sort()
    if not indices:
        errors.append(f"{source}: no timesteps")
    elif indices != list(range(len(indices))):
        errors.append(f"{source}: timesteps must be contiguous from 0; got {indices[:12]}")
    return indices, errors


def inspect_episode_terminal(
    group: h5py.Group,
    source: str,
) -> tuple[list[int], bool | None, list[str]]:
    """Read the strict boolean scalar info/is_completed from the final numeric timestep."""
    indices, errors = timestep_indices(group, source)
    if errors:
        return indices, None, errors
    try:
        dataset = group[f"timestep_{indices[-1]}"]["info"]["is_completed"]
    except KeyError:
        return indices, None, [f"{source}: final timestep is missing info/is_completed"]
    if (
        not isinstance(dataset, h5py.Dataset)
        or dataset.shape != ()
        or np.dtype(dataset.dtype) != np.dtype(bool)
    ):
        return indices, None, [f"{source}: info/is_completed must be a bool scalar"]
    value = dataset[()]
    if not isinstance(value, (bool, np.bool_)):
        return indices, None, [f"{source}: info/is_completed is not a bool"]
    return indices, bool(value), []


# ── 原版采样配置：来源表、AST 提取、校验 ────────────────────────────────────────

SAMPLING_TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")
SAMPLING_SCHEMA_VERSION = 3

# 七份来源文件与本次实际读取的锚点；顺序即写入 JSON 的顺序。
SAMPLING_SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "BinFill",
        "src/robomme/robomme_env/BinFill.py",
        ("config_easy", "config_medium", "config_hard", "__init__", "_load_scene", "_initialize_episode"),
    ),
    (
        "RouteStick",
        "src/robomme/robomme_env/RouteStick.py",
        ("config_easy", "config_medium", "config_hard", "config_xhard", "__init__", "_load_scene", "_initialize_episode"),
    ),
    (
        "VideoUnmaskSwap",
        "src/robomme/robomme_env/VideoUnmaskSwap.py",
        ("config_easy", "config_medium", "config_hard", "config_xhard", "__init__", "_load_scene", "_initialize_episode"),
    ),
    (
        "VideoRepick",
        "src/robomme/robomme_env/VideoRepick.py",
        ("config_easy", "config_medium", "config_hard", "config_xhard", "__init__", "_load_scene", "_initialize_episode"),
    ),
    (
        "object_generation",
        "src/robomme/robomme_env/utils/object_generation.py",
        (
            "build_button",
            "spawn_random_cube",
            "spawn_random_bin",
            "build_bin",
            "build_board_with_hole",
            "spawn_fixed_cube",
            "build_gray_white_target",
        ),
    ),
    ("statechange", "src/robomme/robomme_env/utils/statechange.py", ("rotate_points_random",)),
    ("route", "src/robomme/robomme_env/utils/route.py", ("generate_dynamic_walk",)),
)

# 提取结果里由源码决定、必须与 JSON 逐项相同的块；其余块（units / native_semantics 等）
# 是人写的语义说明，导出时从既有文件原样带过，不参与 --check-config 的比对。
SAMPLING_EXTRACTED_BLOCKS = ("parameters", "positions", "sources")

# 真正参与运算的操作元路径：--source-ref 的旧式源码只能还原这一层，
# 说明性字段（*_expression、*_origin、min_gap 文本等）不在其中。
# ⚠ RouteStick／VideoUnmaskSwap／VideoRepick 的 configs 按难度逐条列出，不列整块：
# 固定基线 94449db 只有三档，2026-09-11 起这三个任务多了 config_xhard，整块比对会把新增档误判成「原版操作元不一致」。
# 基线只担保原三档一字未动；BinFill 没有 xhard，仍整块比对。
SAMPLING_OPERAND_PATHS: tuple[str, ...] = (
    "parameters.BinFill.configs",
    "parameters.BinFill.dynamic.low",
    "parameters.BinFill.dynamic.high_exclusive",
    "parameters.BinFill.dynamic.shape",
    "parameters.RouteStick.configs.easy",
    "parameters.RouteStick.configs.medium",
    "parameters.RouteStick.configs.hard",
    "parameters.RouteStick.configs_fallback_difficulty",
    "parameters.RouteStick.walk",
    "parameters.VideoUnmaskSwap.configs.easy",
    "parameters.VideoUnmaskSwap.configs.medium",
    "parameters.VideoUnmaskSwap.configs.hard",
    "parameters.VideoUnmaskSwap.object_selection",
    "parameters.VideoUnmaskSwap.swap_selection",
    "parameters.VideoRepick.configs.easy",
    "parameters.VideoRepick.configs.medium",
    "parameters.VideoRepick.configs.hard",
    "parameters.VideoRepick.object_selection",
    "parameters.VideoRepick.swap_selection",
    "parameters.VideoRepick.num_repeats.low",
    "parameters.VideoRepick.num_repeats.high_exclusive",
    "parameters.VideoRepick.num_repeats.shape",
    "parameters.VideoRepick.hard_spawn_rounds",
    "positions.BinFill.button.center_xy",
    "positions.BinFill.button.randomize",
    "positions.BinFill.button.randomize_range",
    "positions.BinFill.button.scale",
    "positions.BinFill.board.base_position",
    "positions.BinFill.board.x_offset",
    "positions.BinFill.board.y_offset",
    "positions.BinFill.board.yaw_deg",
    "positions.BinFill.board.board_side",
    "positions.BinFill.board.hole_side",
    "positions.BinFill.board.thickness",
    "positions.BinFill.cubes.region_center",
    "positions.BinFill.cubes.region_half_size",
    "positions.BinFill.cubes.random_yaw",
    "positions.BinFill.cubes.include_existing",
    "positions.BinFill.cubes.include_goal",
    "positions.RouteStick.grid_center",
    "positions.RouteStick.grid_spacing_x",
    "positions.RouteStick.grid_spacing_y",
    "positions.RouteStick.yaw_deg",
    "positions.RouteStick.cylinder_radius",
    "positions.RouteStick.cylinder_height",
    "positions.VideoUnmaskSwap.containers.region3_tri",
    "positions.VideoUnmaskSwap.containers.region3_line",
    "positions.VideoUnmaskSwap.containers.region4",
    "positions.VideoUnmaskSwap.containers.region3_choice.low",
    "positions.VideoUnmaskSwap.containers.region3_choice.high_exclusive",
    "positions.VideoUnmaskSwap.containers.layout_rotation_range_rad",
    "positions.VideoUnmaskSwap.containers.region_half_size",
    "positions.VideoUnmaskSwap.containers.yaw_scale_deg",
    "positions.VideoRepick.button.center_xy",
    "positions.VideoRepick.button.randomize",
    "positions.VideoRepick.button.randomize_range",
    "positions.VideoRepick.button.scale",
    "positions.VideoRepick.easy_medium_cubes.region3_tri",
    "positions.VideoRepick.easy_medium_cubes.region3_line",
    "positions.VideoRepick.easy_medium_cubes.region4",
    "positions.VideoRepick.easy_medium_cubes.region3_choice.low",
    "positions.VideoRepick.easy_medium_cubes.region3_choice.high_exclusive",
    "positions.VideoRepick.easy_medium_cubes.layout_rotation_range_rad",
    "positions.VideoRepick.easy_medium_cubes.region_half_size",
    "positions.VideoRepick.easy_medium_cubes.random_yaw",
    "positions.VideoRepick.easy_medium_cubes.include_existing",
    "positions.VideoRepick.easy_medium_cubes.include_goal",
    "positions.VideoRepick.hard_cubes.region_center",
    "positions.VideoRepick.hard_cubes.region_half_size",
    "positions.VideoRepick.hard_cubes.random_yaw",
    "positions.VideoRepick.hard_cubes.include_existing",
    "positions.VideoRepick.hard_cubes.include_goal",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_source(repo_root: Path, rel_path: str, source_ref: str | None) -> bytes:
    """读一份来源源码：默认读工作树，给了 --source-ref 就读该提交。"""
    if source_ref is None:
        path = repo_root / rel_path
        if not path.is_file():
            raise SamplingConfigError(f"缺少来源文件：{path}")
        return path.read_bytes()
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{source_ref}:{rel_path}"],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:  # git 不可用时直接失败，不降级
        raise SamplingConfigError("--source-ref 需要 git 可执行文件") from exc
    except subprocess.CalledProcessError as exc:
        raise SamplingConfigError(
            f"git show {source_ref}:{rel_path} 失败：{exc.stderr.decode('utf-8', 'replace').strip()}"
        ) from exc
    return completed.stdout


def _module_tree(payload: bytes, label: str) -> ast.Module:
    try:
        return ast.parse(payload.decode("utf-8"))
    except SyntaxError as exc:
        raise SamplingConfigError(f"{label}: 源码无法解析：{exc}") from exc


def _class_def(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise SamplingConfigError(f"未找到类定义：{name}")


def _func_def(scope: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(scope):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise SamplingConfigError(f"未找到函数定义：{name}")


def _has_assigned(scope: ast.AST, name: str) -> bool:
    """scope 内是否存在 ``name = ...`` 赋值（只判存在，不求值）。"""
    return any(
        isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
        for node in ast.walk(scope)
    )


def _assigned_literal(scope: ast.AST, name: str) -> Any:
    """取 scope 内 ``name = <字面量>`` 的值；同名多次赋值时取第一次。"""
    for node in ast.walk(scope):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                try:
                    return ast.literal_eval(node.value)
                except ValueError as exc:
                    raise SamplingConfigError(f"{name} 不是字面量：{exc}") from exc
    raise SamplingConfigError(f"未找到赋值：{name}")


def _module_literal(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise SamplingConfigError(f"模块顶层未找到赋值：{name}")


def _has_module_literal(tree: ast.Module, name: str) -> bool:
    try:
        _module_literal(tree, name)
    except SamplingConfigError:
        return False
    return True


def _callee_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _calls(scope: ast.AST, name: str) -> list[ast.Call]:
    """按源码行号返回同名调用；ast.walk 是广度优先，直接用会把分支里的调用排错。"""
    found = [node for node in ast.walk(scope) if isinstance(node, ast.Call) and _callee_name(node) == name]
    return sorted(found, key=lambda node: (node.lineno, node.col_offset))


def _kwarg_node(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _kwarg_literal(call: ast.Call, name: str, label: str) -> Any:
    node = _kwarg_node(call, name)
    if node is None:
        raise SamplingConfigError(f"{label}: 调用缺少关键字实参 {name}")
    try:
        return ast.literal_eval(node)
    except ValueError as exc:
        raise SamplingConfigError(f"{label}: 关键字实参 {name} 不是字面量：{exc}") from exc


def _param_default(func: ast.FunctionDef, name: str, label: str) -> Any:
    args = func.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults = list(args.defaults)
    offset = len(positional) - len(defaults)
    for index, arg in enumerate(positional):
        if arg.arg == name:
            if index < offset:
                raise SamplingConfigError(f"{label}: 形参 {name} 没有默认值")
            return ast.literal_eval(defaults[index - offset])
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if arg.arg == name:
            if default is None:
                raise SamplingConfigError(f"{label}: 形参 {name} 没有默认值")
            return ast.literal_eval(default)
    raise SamplingConfigError(f"{label}: 未找到形参 {name}")


def _scale_subtract(node: ast.AST, label: str) -> dict[str, float]:
    """匹配 ``<随机数> * scale - subtract`` 这类原版 BinOp，返回运算元。

    不折算成 [min,max]：``0.15 + (u*0.2 - 0.2)`` 与 ``-0.05 + u*0.2`` 的 float64
    位模式不同，配置里只能存源码里出现的运算元。
    """
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)):
        raise SamplingConfigError(f"{label}: 不是 `... - <常量>` 形式")
    subtract = ast.literal_eval(node.right)
    inner = node.left
    if not (isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Mult)):
        raise SamplingConfigError(f"{label}: 减法左侧不是乘法")
    scale = ast.literal_eval(inner.right)
    return {"scale": scale, "subtract": subtract}


def _randint_args(call: ast.Call, label: str) -> tuple[Any, Any, Any]:
    if len(call.args) < 3:
        raise SamplingConfigError(f"{label}: randint 位置实参不足")
    low = ast.literal_eval(call.args[0])
    high = ast.literal_eval(call.args[1])
    shape = ast.literal_eval(call.args[2])
    return low, high, list(shape)


def _flatten(payload: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            flat.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    else:
        flat[prefix] = payload
    return flat


def _pick_path(payload: Mapping[str, Any], path: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise SamplingConfigError(f"配置缺少字段：{path}")
        node = node[part]
    return node


def _operand_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    """把完整配置投影到操作元集合，供与旧式源码对照。"""
    return {path: _pick_path(payload, path) for path in SAMPLING_OPERAND_PATHS}


def extract_native_sampling(
    repo_root: Path,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """从源码 AST 提取四任务的原版采样输入。

    工作树（以及任何已经接入 sampling_config 的提交）里，四个任务模块顶层各有一份
    ``NATIVE_SAMPLING`` 字面量，它同时是不传配置时的运行默认值，因此提取即读取运行真值；
    难度字典仍从类属性 ``config_easy/medium/hard``（三任务另有 ``config_xhard``）读，不在两处重复。
    """
    sources: dict[str, Any] = {}
    trees: dict[str, ast.Module] = {}
    for name, rel_path, anchors in SAMPLING_SOURCES:
        payload = _read_source(repo_root, rel_path, source_ref)
        sources[name] = {
            "path": rel_path,
            "sha256": _sha256_bytes(payload),
            "anchors": list(anchors),
        }
        trees[name] = _module_tree(payload, rel_path)

    legacy = [task for task in SAMPLING_TASKS if not _has_module_literal(trees[task], "NATIVE_SAMPLING")]
    if legacy:
        parameters, positions = _extract_legacy(trees)
        _complete_action_parameters(trees, parameters)
        return {"parameters": parameters, "positions": positions, "sources": sources, "_legacy": True}

    parameters: dict[str, Any] = {}
    positions: dict[str, Any] = {}
    for task in SAMPLING_TASKS:
        tree = trees[task]
        class_def = _class_def(tree, task)
        native = _module_literal(tree, "NATIVE_SAMPLING")
        if set(native) != {"parameters", "positions"}:
            raise SamplingConfigError(f"{task}: NATIVE_SAMPLING 顶层只能有 parameters 与 positions")
        task_parameters: dict[str, Any] = {
            "configs": {
                "easy": _assigned_literal(class_def, "config_easy"),
                "medium": _assigned_literal(class_def, "config_medium"),
                "hard": _assigned_literal(class_def, "config_hard"),
            }
        }
        # 第四档 xhard（2026-09-11）只有 RouteStick／VideoUnmaskSwap／VideoRepick 有，类里存在才写入；
        # BinFill 没有，保持三键。legacy 分支（旧式源码）永远没有该属性，不改。
        if _has_assigned(class_def, "config_xhard"):
            task_parameters["configs"]["xhard"] = _assigned_literal(class_def, "config_xhard")
        task_parameters.update(copy.deepcopy(native["parameters"]))
        parameters[task] = task_parameters
        positions[task] = copy.deepcopy(native["positions"])

    _complete_action_parameters(trees, parameters)
    _cross_check(trees, parameters, positions)
    return {"parameters": parameters, "positions": positions, "sources": sources}


def _require_ast(scope: ast.AST, expression: str, label: str) -> None:
    """历史规则必须在真实 AST 中命中；忽略注释、空白与行号，不执行源码。"""
    expected = ast.parse(expression).body[0]
    if isinstance(expected, ast.Expr):
        expected = expected.value
    signature = ast.dump(expected, include_attributes=False)
    if not any(ast.dump(node, include_attributes=False) == signature for node in ast.walk(scope)):
        raise SamplingConfigError(f"{label}: 未识别历史规则 {expression}")


def _assignment_value(scope: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise SamplingConfigError(f"未找到历史赋值 {name}")


def _historical_action_parameters(task: str, tree: ast.Module, route: ast.Module) -> dict[str, Any]:
    """从旧调用点提取操作元，固定策略名称只在其 AST 证据通过后生成。"""
    scene = _func_def(_class_def(tree, task), "_load_scene")
    if task == "RouteStick":
        walk = _func_def(route, "generate_dynamic_walk")
        for expr in (
            "torch.randint(0, len(indices), (1,), generator=generator).item()",
            "neighbors.append(current_idx - 1)", "neighbors.append(current_idx + 1)",
            "filtered if filtered else neighbors",
            "torch.randint(0, len(candidates), (1,), generator=generator).item()",
        ):
            _require_ast(walk, expr, task)
        direction = _assignment_value(scene, "dir_flag")
        if not isinstance(direction, ast.IfExp) or not isinstance(direction.test, ast.Compare) or not isinstance(direction.test.ops[0], ast.Lt):
            raise SamplingConfigError("RouteStick: 未识别方向抽样表达式")
        _require_ast(direction.test.left, "torch.rand(1, generator=generator).item()", task)
        return {"walk": {
            "node_indices": _assigned_literal(scene, "button_indices"),
            "start_selection": "randint", "neighbor_order": [-1, 1],
            "force_reverse_at_endpoint": True,
            "direction": {"sampler": "torch.rand", "shape": [1],
                "threshold": ast.literal_eval(direction.test.comparators[0]),
                "less_than": ast.literal_eval(direction.body), "otherwise": ast.literal_eval(direction.orelse)},
        }}
    step = _func_def(_class_def(tree, task), "step")
    population = "spawned_bins" if task == "VideoUnmaskSwap" else "spawned_cubes"
    for expr in (
        "pair_idx2 is None and pair_idx1 is not None",
        "candidate is None or candidate is pair_idx1",
        "np.linalg.norm(reference_pos[:2] - candidate_pos[:2])",
        "dist < closest_dist", "closest_actor = candidate",
        f"self.{population}",
    ):
        _require_ast(step, expr, task)
    partner = {"selection": "nearest", "position_axes": [0, 1],
               "resolve_at": "swap_start", "exclude_self": True, "tie_break": "first_in_spawn_order"}
    if task == "VideoUnmaskSwap":
        permutation = _calls(scene, "randperm")
        hidden = _assignment_value(scene, "num_bins_to_select")
        targets = _assignment_value(scene, "target_indices")
        if not isinstance(hidden, ast.Call) or not isinstance(targets, ast.Subscript) or not isinstance(targets.slice, ast.Slice):
            raise SamplingConfigError("VideoUnmaskSwap: 未识别容器或交换目标数量")
        for expr in (
            "self.spawned_bins[swap_indices[0]]", "self.spawned_bins[swap_indices[1]]", "self.spawned_bins[swap_indices[2]]",
            "torch.randint(0, len(remaining_indices), (1,), generator=generator).item()",
            "[i for i in range(len(self.spawned_bins)) if i not in target_indices.tolist()]",
            "is_bin_pickup(self, obj=self.selected_bins[0])", "is_bin_pickup(self, obj=self.selected_bins[1])",
        ):
            _require_ast(scene, expr, task)
        return {
            "object_selection": {
                "hidden_bin_permutation_size": ast.literal_eval(permutation[1].args[0]),
                "hidden_bin_count_max": ast.literal_eval(hidden.args[0]),
                "pickup_selected_indices": [0, 1],
                "swap_seed_target_count": ast.literal_eval(targets.slice.upper),
            },
            "swap_selection": {"initiator_mapping": "selected_local_indices_into_spawned_bins",
                "remaining_selection": "randint_from_spawned_indices_excluding_local_targets", "partner": partner},
        }
    for expr in (
        "torch.randperm(len(self.spawned_cubes), generator=self.generator)",
        "torch.randperm(len(remaining_indices), generator=self.generator)",
        "swap_indices = target_indices + selected_indices",
        "[remaining_indices[i] for i in selected_remaining]",
    ):
        _require_ast(scene, expr, task)
    targets = _assignment_value(scene, "target_indices")
    remaining = _assignment_value(scene, "selected_remaining")
    target_call = _calls(_assignment_value(scene, "target_idx"), "randint")[0]
    try:
        return {
            "object_selection": {
                "easy_medium_target_count": ast.literal_eval(targets.func.value.slice.upper),
                "hard_target_low": ast.literal_eval(target_call.args[0]),
                "swap_remaining_count": ast.literal_eval(remaining.func.value.slice.upper),
            },
            "swap_selection": {"initiator_mapping": "target_then_permuted_remaining_spawned_indices",
                "remaining_selection": "randperm_without_target", "partner": partner},
        }
    except (AttributeError, ValueError) as exc:
        raise SamplingConfigError("VideoRepick: 未识别目标和交换对象抽样") from exc


def _complete_action_parameters(trees: Mapping[str, ast.Module], parameters: dict[str, Any]) -> None:
    for task in ("RouteStick", "VideoUnmaskSwap", "VideoRepick"):
        keys = ("walk",) if task == "RouteStick" else ("object_selection", "swap_selection")
        present = [key in parameters[task] for key in keys]
        if not any(present):
            parameters[task].update(_historical_action_parameters(task, trees[task], trees["route"]))
        elif not all(present):
            raise SamplingConfigError(f"{task}: 对象选择配置块不完整，不能混用历史与新版字段")


def _validate_action_parameters(parameters: Mapping[str, Any], native: Mapping[str, Any]) -> None:
    """策略只支持原规则，方向阈值是唯一开放的新增数值输入。"""
    for task in ("RouteStick", "VideoUnmaskSwap", "VideoRepick"):
        keys = ("walk",) if task == "RouteStick" else ("object_selection", "swap_selection")
        for key in keys:
            candidate = copy.deepcopy(parameters[task][key])
            expected = native[task][key]
            if key == "walk":
                threshold = candidate["direction"]["threshold"]
                if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
                    raise SamplingConfigError("RouteStick.walk.direction.threshold 必须为 [0,1] 内有限数值")
                candidate["direction"]["threshold"] = expected["direction"]["threshold"]
            if json.dumps(candidate, sort_keys=True) != json.dumps(expected, sort_keys=True):
                raise SamplingConfigError(f"{task}.{key} 必须保留原版规则与类型")


def _cross_check(
    trees: Mapping[str, ast.Module],
    parameters: Mapping[str, Any],
    positions: Mapping[str, Any],
) -> None:
    """AST 不能直接达到的项：跨文件的被调函数默认值必须与快照一致。"""
    object_generation = trees["object_generation"]
    build_button = _func_def(object_generation, "build_button")
    default_range = list(_param_default(build_button, "randomize_range", "build_button"))
    snapshot_range = list(positions["BinFill"]["button"]["randomize_range"])
    if default_range != snapshot_range:
        raise SamplingConfigError(
            "BinFill 按钮的 randomize_range 来源是 build_button 形参默认值，"
            f"源码为 {default_range}，快照为 {snapshot_range}"
        )
    spawn_random_bin = _func_def(object_generation, "spawn_random_bin")
    default_yaw = _param_default(spawn_random_bin, "yaw_scale_deg", "spawn_random_bin")
    snapshot_yaw = positions["VideoUnmaskSwap"]["containers"]["yaw_scale_deg"]
    if float(default_yaw) != float(snapshot_yaw):
        raise SamplingConfigError(
            f"spawn_random_bin 的 yaw_scale_deg 默认值 {default_yaw} 与快照 {snapshot_yaw} 不一致"
        )
    # 新字段必须真正接到原调用点，不能只存在于 NATIVE_SAMPLING 声明中。
    for task in ("VideoUnmaskSwap", "VideoRepick", "RouteStick"):
        declared = _module_literal(trees[task], "NATIVE_SAMPLING")["parameters"]
        key = "walk" if task == "RouteStick" else "object_selection"
        if key not in declared:
            # schema 2 历史源码的内联值已由 _complete_action_parameters 独立提取。
            continue
        cls = _class_def(trees[task], task)
        scene = _func_def(cls, "_load_scene")
        if task == "RouteStick":
            expressions = (
                'button_indices = list(walk_cfg["node_indices"])',
                'generate_dynamic_walk(button_indices, steps=steps, allow_backtracking=allow_backtracking, generator=generator, walk_config=walk_cfg)',
                'torch.rand(*direction_cfg["shape"], generator=generator).item() < direction_cfg["threshold"]',
            )
            walk = _func_def(trees["route"], "generate_dynamic_walk")
            if _param_default(walk, "walk_config", "generate_dynamic_walk") is not None:
                raise SamplingConfigError("generate_dynamic_walk.walk_config 默认值必须为 None")
            _require_ast(walk, 'neighbor_order = walk_config["neighbor_order"]', task)
        elif task == "VideoUnmaskSwap":
            expressions = (
                'min(selection_cfg["hidden_bin_count_max"], len(self.spawned_bins))',
                'torch.randperm(selection_cfg["hidden_bin_permutation_size"], generator=generator)',
                'torch.randperm(len(selected_bin_indices), generator=generator)[:selection_cfg["swap_seed_target_count"]]',
                'pickup_indices = selection_cfg["pickup_selected_indices"]',
                'self.selected_bins[pickup_indices[0]]', 'self.selected_bins[pickup_indices[1]]',
            )
        else:
            expressions = (
                'torch.randint(selection_cfg["hard_target_low"], len(self.spawned_cubes), (1,), generator=self.generator)',
                'torch.randperm(len(self.spawned_cubes), generator=self.generator)[:selection_cfg["easy_medium_target_count"]]',
                'torch.randperm(len(remaining_indices), generator=self.generator)[:selection_cfg["swap_remaining_count"]]',
            )
        for expression in expressions:
            _require_ast(scene, expression, f"{task} 新字段消费位置")
        if task != "RouteStick":
            step = _func_def(cls, "step")
            for expression in (
                'axes = self._sampling["parameters"]["swap_selection"]["partner"]["position_axes"]',
                'np.linalg.norm(reference_pos[axes] - candidate_pos[axes])',
                'dist < closest_dist', 'pair_idx2 is None and pair_idx1 is not None',
            ):
                _require_ast(step, expression, f"{task} 交换搭档规则")


def _extract_legacy(trees: Mapping[str, ast.Module]) -> tuple[dict[str, Any], dict[str, Any]]:
    """从尚未接入 sampling_config 的旧式源码里还原操作元。

    只覆盖 ``SAMPLING_OPERAND_PATHS``：说明性字段在旧源码里并不存在，
    因此 ``--source-ref <基线>`` 的比对口径是操作元子集，不是整份快照。
    """
    parameters: dict[str, Any] = {}
    positions: dict[str, Any] = {}

    for task in SAMPLING_TASKS:
        class_def = _class_def(trees[task], task)
        parameters[task] = {
            "configs": {
                "easy": _assigned_literal(class_def, "config_easy"),
                "medium": _assigned_literal(class_def, "config_medium"),
                "hard": _assigned_literal(class_def, "config_hard"),
            }
        }

    # BinFill：dynamic 抽样、按钮、孔板 BinOp、方块区域
    binfill = _class_def(trees["BinFill"], "BinFill")
    binfill_init = _func_def(binfill, "__init__")
    dynamic_call = None
    for call in _calls(binfill_init, "randint"):
        dynamic_call = call
        break
    if dynamic_call is None:
        raise SamplingConfigError("BinFill.__init__ 未找到 dynamic 的 randint")
    low, high, shape = _randint_args(dynamic_call, "BinFill.dynamic")
    parameters["BinFill"]["dynamic"] = {
        "sampler": "torch.randint",
        "low": low,
        "high_exclusive": high,
        "shape": shape,
        "cast": "bool",
    }

    binfill_scene = _func_def(binfill, "_load_scene")
    button_call = _calls(binfill_scene, "build_button")[0]
    build_button = _func_def(trees["object_generation"], "build_button")
    positions["BinFill"] = {
        "button": {
            "center_xy": list(_kwarg_literal(button_call, "center_xy", "BinFill.build_button")),
            "randomize": _param_default(build_button, "randomize", "build_button"),
            "randomize_range": list(_param_default(build_button, "randomize_range", "build_button")),
            "scale": _kwarg_literal(button_call, "scale", "BinFill.build_button"),
        }
    }
    board_call = _calls(binfill_scene, "build_board_with_hole")[0]
    x_var = _assigned_literal_node(binfill_scene, "x_var")
    y_var = _assigned_literal_node(binfill_scene, "y_var")
    z_rot = _assigned_literal_node(binfill_scene, "z_rot_deg")
    position_node = _kwarg_node(board_call, "position")
    if not isinstance(position_node, ast.List) or len(position_node.elts) != 3:
        raise SamplingConfigError("BinFill 孔板 position 不是三元列表")
    base_position = [
        ast.literal_eval(position_node.elts[0].left)
        if isinstance(position_node.elts[0], ast.BinOp)
        else ast.literal_eval(position_node.elts[0]),
        ast.literal_eval(position_node.elts[1].left)
        if isinstance(position_node.elts[1], ast.BinOp)
        else ast.literal_eval(position_node.elts[1]),
        ast.literal_eval(position_node.elts[2]),
    ]
    positions["BinFill"]["board"] = {
        "base_position": base_position,
        "x_offset": _scale_subtract(x_var, "BinFill.x_var"),
        "y_offset": _scale_subtract(y_var, "BinFill.y_var"),
        "yaw_deg": _scale_subtract(z_rot, "BinFill.z_rot_deg"),
        "board_side": _kwarg_literal(board_call, "board_side", "BinFill.board"),
        "hole_side": _kwarg_literal(board_call, "hole_side", "BinFill.board"),
        "thickness": _kwarg_literal(board_call, "thickness", "BinFill.board"),
    }
    cube_call = _calls(binfill_scene, "spawn_random_cube")[0]
    positions["BinFill"]["cubes"] = {
        "region_center": list(_kwarg_literal(cube_call, "region_center", "BinFill.cube")),
        "region_half_size": list(_kwarg_literal(cube_call, "region_half_size", "BinFill.cube")),
        "random_yaw": _kwarg_literal(cube_call, "random_yaw", "BinFill.cube"),
        "include_existing": _kwarg_literal(cube_call, "include_existing", "BinFill.cube"),
        "include_goal": _kwarg_literal(cube_call, "include_goal", "BinFill.cube"),
    }

    # RouteStick：网格、theta、障碍柱几何、难度兜底分支
    route_stick = _class_def(trees["RouteStick"], "RouteStick")
    route_scene = _func_def(route_stick, "_load_scene")
    theta_call = _calls(route_scene, "radians")[0]
    positions["RouteStick"] = {
        "grid_center": list(_assigned_literal(route_scene, "grid_center")),
        "grid_spacing_x": _assigned_literal(route_scene, "grid_spacing_x"),
        "grid_spacing_y": _assigned_literal(route_scene, "grid_spacing_y"),
        "yaw_deg": _scale_subtract(theta_call.args[0], "RouteStick.theta"),
        "cylinder_radius": _assigned_literal(route_scene, "cylinder_radius"),
        "cylinder_height": _assigned_literal(route_scene, "cylinder_height"),
    }
    parameters["RouteStick"]["configs_fallback_difficulty"] = _legacy_routestick_fallback(route_scene)

    # VideoUnmaskSwap：容器锚点、region3 选择、整体旋转、区域半边长、容器 yaw
    vus = _class_def(trees["VideoUnmaskSwap"], "VideoUnmaskSwap")
    vus_scene = _func_def(vus, "_load_scene")
    vus_choice = _calls(vus_scene, "randint")[0]
    low, high, _shape = _randint_args(vus_choice, "VideoUnmaskSwap.region3_choice")
    rotate_call = _calls(vus_scene, "rotate_points_random")[0]
    bin_call = _calls(vus_scene, "spawn_random_bin")[0]
    spawn_random_bin = _func_def(trees["object_generation"], "spawn_random_bin")
    positions["VideoUnmaskSwap"] = {
        "containers": {
            "region3_tri": _assigned_literal(vus_scene, "region3_tri"),
            "region3_line": _assigned_literal(vus_scene, "region3_line"),
            "region4": _assigned_literal(vus_scene, "region4"),
            "region3_choice": {"sampler": "torch.randint", "low": low, "high_exclusive": high},
            "layout_rotation_range_rad": list(ast.literal_eval(rotate_call.args[1])),
            "region_half_size": _kwarg_literal(bin_call, "region_half_size", "VideoUnmaskSwap.bin"),
            "yaw_scale_deg": _legacy_bin_yaw_scale(spawn_random_bin),
        }
    }

    # VideoRepick：按钮、num_repeats、hard 轮数、easy/medium 与 hard 区域
    repick = _class_def(trees["VideoRepick"], "VideoRepick")
    repick_init = _func_def(repick, "__init__")
    repeats_call = _calls(repick_init, "randint")[0]
    low, high, shape = _randint_args(repeats_call, "VideoRepick.num_repeats")
    parameters["VideoRepick"]["num_repeats"] = {
        "sampler": "torch.randint",
        "low": low,
        "high_exclusive": high,
        "shape": shape,
    }
    repick_scene = _func_def(repick, "_load_scene")
    parameters["VideoRepick"]["hard_spawn_rounds"] = _legacy_hard_rounds(repick_scene)
    button_call = _calls(repick_scene, "build_button")[0]
    cube_calls = _calls(repick_scene, "spawn_random_cube")
    hard_call, plain_call = cube_calls[0], cube_calls[1]
    choice_call = None
    for call in _calls(repick_scene, "randint"):
        if len(call.args) >= 2 and _is_literal(call.args[1]) and ast.literal_eval(call.args[1]) == 2:
            choice_call = call
            break
    if choice_call is None:
        raise SamplingConfigError("VideoRepick 未找到 region3_choice 的 randint")
    low, high, _shape = _randint_args(choice_call, "VideoRepick.region3_choice")
    rotate_call = _calls(repick_scene, "rotate_points_random")[0]
    spawn_random_cube = _func_def(trees["object_generation"], "spawn_random_cube")
    positions["VideoRepick"] = {
        "button": {
            "center_xy": list(_kwarg_literal(button_call, "center_xy", "VideoRepick.build_button")),
            "randomize": _kwarg_literal(button_call, "randomize", "VideoRepick.build_button"),
            "randomize_range": list(_kwarg_literal(button_call, "randomize_range", "VideoRepick.build_button")),
            "scale": _kwarg_literal(button_call, "scale", "VideoRepick.build_button"),
        },
        "easy_medium_cubes": {
            "region3_tri": _assigned_literal(repick_scene, "region3_tri"),
            "region3_line": _assigned_literal(repick_scene, "region3_line"),
            "region4": _assigned_literal(repick_scene, "region4"),
            "region3_choice": {"sampler": "torch.randint", "low": low, "high_exclusive": high},
            "layout_rotation_range_rad": list(ast.literal_eval(rotate_call.args[1])),
            "region_half_size": _kwarg_literal(plain_call, "region_half_size", "VideoRepick.cube"),
            "random_yaw": _param_default(spawn_random_cube, "random_yaw", "spawn_random_cube"),
            "include_existing": _param_default(spawn_random_cube, "include_existing", "spawn_random_cube"),
            "include_goal": _param_default(spawn_random_cube, "include_goal", "spawn_random_cube"),
        },
        "hard_cubes": {
            "region_center": list(_kwarg_literal(hard_call, "region_center", "VideoRepick.hard")),
            "region_half_size": list(_kwarg_literal(hard_call, "region_half_size", "VideoRepick.hard")),
            "random_yaw": _kwarg_literal(hard_call, "random_yaw", "VideoRepick.hard"),
            "include_existing": _kwarg_literal(hard_call, "include_existing", "VideoRepick.hard"),
            "include_goal": _kwarg_literal(hard_call, "include_goal", "VideoRepick.hard"),
        },
    }
    return parameters, positions


def _is_literal(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return False
    return True


def _assigned_literal_node(scope: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    raise SamplingConfigError(f"未找到赋值：{name}")


def _legacy_routestick_fallback(scene: ast.FunctionDef) -> str:
    """旧式源码里的兜底是 ``self.configs.get(..., self.config_easy)``。"""
    for call in _calls(scene, "get"):
        if len(call.args) == 2 and isinstance(call.args[1], ast.Attribute):
            attribute = call.args[1].attr
            if attribute.startswith("config_"):
                return attribute[len("config_") :]
    raise SamplingConfigError("RouteStick 未找到难度兜底分支")


def _legacy_bin_yaw_scale(func: ast.FunctionDef) -> float:
    """旧式 spawn_random_bin 里 yaw 是内联的 ``torch.rand(...).item() * 90.0``。"""
    try:
        return float(_param_default(func, "yaw_scale_deg", "spawn_random_bin"))
    except SamplingConfigError:
        pass
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "z_rotation":
                    value = node.value
                    if isinstance(value, ast.Call) and _callee_name(value) == "float":
                        value = value.args[0]
                    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mult):
                        return float(ast.literal_eval(value.right))
    raise SamplingConfigError("spawn_random_bin 未找到容器 yaw 的抽样常量")


def _legacy_hard_rounds(scene: ast.FunctionDef) -> int:
    """旧式源码里 hard 的五轮是 ``for idx in range(5)``。"""
    candidates = [
        node
        for node in ast.walk(scene)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and _callee_name(node.iter) == "range"
        and len(node.iter.args) == 1
        and _is_literal(node.iter.args[0])
    ]
    if not candidates:
        raise SamplingConfigError("VideoRepick 未找到 hard 的生成轮数")
    first = min(candidates, key=lambda node: node.lineno)
    return int(ast.literal_eval(first.iter.args[0]))


def _same_shape(native: Any, candidate: Any, path: str) -> None:
    """逐字段核对结构、字段名与类型；数值可以不同，形状与类型不能变。"""
    if isinstance(native, dict):
        if not isinstance(candidate, dict):
            raise SamplingConfigError(f"{path}: 应为对象，实际为 {type(candidate).__name__}")
        missing = sorted(set(native) - set(candidate))
        unknown = sorted(set(candidate) - set(native))
        if missing:
            raise SamplingConfigError(f"{path}: 缺少字段 {missing}")
        if unknown:
            raise SamplingConfigError(f"{path}: 出现未知字段 {unknown}")
        for key in native:
            _same_shape(native[key], candidate[key], f"{path}.{key}" if path else key)
        return
    if isinstance(native, list):
        if not isinstance(candidate, list):
            raise SamplingConfigError(f"{path}: 应为数组，实际为 {type(candidate).__name__}")
        if len(native) != len(candidate):
            raise SamplingConfigError(f"{path}: 数组长度应为 {len(native)}，实际为 {len(candidate)}")
        for index, item in enumerate(native):
            _same_shape(item, candidate[index], f"{path}[{index}]")
        return
    if native is None:
        if candidate is not None:
            raise SamplingConfigError(f"{path}: 该字段在原版中恒为 null")
        return
    if isinstance(native, bool):
        if not isinstance(candidate, bool):
            raise SamplingConfigError(f"{path}: 应为布尔值")
        return
    if isinstance(native, int):
        if isinstance(candidate, bool) or not isinstance(candidate, int):
            raise SamplingConfigError(f"{path}: 应为整数")
        return
    if isinstance(native, float):
        if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
            raise SamplingConfigError(f"{path}: 应为数值")
        return
    if isinstance(native, str):
        if not isinstance(candidate, str):
            raise SamplingConfigError(f"{path}: 应为字符串")
        return
    raise SamplingConfigError(f"{path}: 快照中出现不支持的类型 {type(native).__name__}")


def load_sampling_config(path: str | Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    """读取并校验采样配置，返回按任务切好的普通字典。

    只读、只校验、只复制：全程不采样、不创建环境、不导入仿真依赖。
    """
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise SamplingConfigError(f"采样配置不存在：{config_path}")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SamplingConfigError(f"{config_path}: JSON 无法解析：{exc}") from exc
    if not isinstance(payload, dict):
        raise SamplingConfigError(f"{config_path}: 顶层必须是对象")
    if payload.get("schema_version") != SAMPLING_SCHEMA_VERSION:
        raise SamplingConfigError(
            f"{config_path}: schema_version 必须为 {SAMPLING_SCHEMA_VERSION}，实际为 {payload.get('schema_version')!r}；请使用 --extract-config 重新导出"
        )
    for block in ("parameters", "positions"):
        if block not in payload or not isinstance(payload[block], dict):
            raise SamplingConfigError(f"{config_path}: 缺少 {block} 块")
        unknown = sorted(set(payload[block]) - set(SAMPLING_TASKS))
        if unknown:
            raise SamplingConfigError(f"{config_path}: {block} 出现未知任务名 {unknown}")
        missing = sorted(set(SAMPLING_TASKS) - set(payload[block]))
        if missing:
            raise SamplingConfigError(f"{config_path}: {block} 缺少任务 {missing}")

    native = extract_native_sampling(repo_root)
    _same_shape(native["parameters"], payload["parameters"], "parameters")
    _same_shape(native["positions"], payload["positions"], "positions")
    _validate_action_parameters(payload["parameters"], native["parameters"])

    # 来源指纹：生成时核对七份源码，防止配置与实际运行的源码脱节
    declared = payload.get("sources")
    if not isinstance(declared, dict):
        raise SamplingConfigError(f"{config_path}: 缺少 sources 块")
    for name, actual in native["sources"].items():
        expected = declared.get(name)
        if not isinstance(expected, dict):
            raise SamplingConfigError(f"{config_path}: sources 缺少 {name}")
        if expected.get("sha256") != actual["sha256"]:
            raise SamplingConfigError(
                f"{config_path}: {actual['path']} 的 SHA-256 与快照不符"
                f"（源码 {actual['sha256'][:12]}…，快照 {str(expected.get('sha256'))[:12]}…）"
            )

    return {
        task: {
            "parameters": copy.deepcopy(payload["parameters"][task]),
            "positions": copy.deepcopy(payload["positions"][task]),
        }
        for task in SAMPLING_TASKS
    }


def _merge_snapshot(existing: Mapping[str, Any] | None, extracted: Mapping[str, Any]) -> dict[str, Any]:
    """写快照：源码派生块整体重写，人写的说明块从既有文件原样带过。"""
    payload: dict[str, Any] = {}
    payload["schema_version"] = SAMPLING_SCHEMA_VERSION
    for key in ("source_commit", "target_version", "status", "scope", "extraction_note", "units"):
        if existing and key in existing:
            payload[key] = copy.deepcopy(existing[key])
    payload["sources"] = copy.deepcopy(extracted["sources"])
    payload["parameters"] = copy.deepcopy(extracted["parameters"])
    payload["positions"] = copy.deepcopy(extracted["positions"])
    if existing and "native_semantics" in existing:
        payload["native_semantics"] = copy.deepcopy(existing["native_semantics"])
        references = {
            "RouteStick": {"route_button_indices": "parameters.RouteStick.walk.node_indices",
                "swing_directions": "parameters.RouteStick.walk.direction",
                "backtrack_false_can_force_reverse_at_endpoint": "parameters.RouteStick.walk.force_reverse_at_endpoint"},
            "VideoUnmaskSwap": {"hidden_bin_permutation_size": "parameters.VideoUnmaskSwap.object_selection.hidden_bin_permutation_size"},
        }
        for task, fields in references.items():
            for key, path in fields.items():
                if key in payload["native_semantics"].get(task, {}):
                    payload["native_semantics"][task][key] = {"source": path}
    return payload


def run_extract_config(
    config_path: str | Path,
    repo_root: Path,
    check_only: bool,
    source_ref: str | None,
) -> dict[str, Any]:
    """``--extract-config`` 分支：只读源码，导出或核对原值快照。"""
    target = Path(config_path).expanduser()
    extracted = extract_native_sampling(repo_root)
    existing: dict[str, Any] | None = None
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))

    report: dict[str, Any] = {
        "mode": "check" if check_only else "write",
        "config": str(target),
        "tasks": list(SAMPLING_TASKS),
        "source_ref": source_ref,
    }

    if check_only:
        if existing is None:
            raise SamplingConfigError(f"--check-config 需要既有快照：{target}")
        differences: list[str] = []
        for block in SAMPLING_EXTRACTED_BLOCKS:
            flat_native = _flatten(extracted[block], block)
            flat_existing = _flatten(existing.get(block, {}), block)
            for key in sorted(set(flat_native) | set(flat_existing)):
                if flat_native.get(key, "<缺失>") != flat_existing.get(key, "<缺失>"):
                    differences.append(
                        f"{key}: 源码={flat_native.get(key, '<缺失>')!r} 快照={flat_existing.get(key, '<缺失>')!r}"
                    )
        if differences:
            raise SamplingConfigError(
                f"{target}: 快照与当前工作树源码不一致，共 {len(differences)} 处：\n  "
                + "\n  ".join(differences[:20])
            )
        report["working_tree"] = "一致"
        if source_ref is not None:
            reference = extract_native_sampling(repo_root, source_ref=source_ref)
            ref_operands = _operand_view(reference)
            snapshot_operands = _operand_view(existing)
            ref_diff = [
                f"{path}: {source_ref}={ref_operands[path]!r} 快照={snapshot_operands[path]!r}"
                for path in SAMPLING_OPERAND_PATHS
                if ref_operands[path] != snapshot_operands[path]
            ]
            if ref_diff:
                raise SamplingConfigError(
                    f"{target}: 与 {source_ref} 的原版操作元不一致，共 {len(ref_diff)} 处：\n  "
                    + "\n  ".join(ref_diff[:20])
                )
            report["source_ref_operands"] = f"{len(SAMPLING_OPERAND_PATHS)} 项一致"
        return report

    payload = _merge_snapshot(existing, extracted)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    report["written"] = True
    report["sha256"] = {name: item["sha256"] for name, item in extracted["sources"].items()}
    return report


# ── 迁自 merge_episode_h5.py ──────────────────────────────────────────────────


def _sources(input_dir: Path, task: str) -> list[tuple[int, Path]]:
    metadata_path = input_dir / f"record_dataset_{task}_metadata.json"
    if not metadata_path.is_file():
        raise MergeError(f"缺少 metadata：{metadata_path}")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    records = sorted(payload["records"], key=lambda item: int(item["episode"]))
    sources: list[tuple[int, Path]] = []
    missing: list[str] = []
    for record in records:
        episode = int(record["episode"])
        seed = int(record["seed"])
        path = input_dir / "hdf5_files" / f"{task}_ep{episode}_seed{seed}.h5"
        if not path.is_file():
            missing.append(f"episode_{episode}(seed={seed}) → {path.name}")
            continue
        sources.append((episode, path))
    if missing:
        raise MergeError(f"{task}: 有 {len(missing)} 条源文件缺失：" + "; ".join(missing[:10]))
    return sources


def merge_task(input_dir: Path, output_dir: Path, task: str, delete_source: bool) -> dict[str, Any]:
    """合并逻辑与骨架 generate_dataset.py 的 _merge 一致：临时文件 + 原子替换。"""
    sources = _sources(input_dir, task)
    target = output_dir / f"record_dataset_{task}.h5"
    temporary = output_dir / f".record_dataset_{task}.h5.tmp"
    try:
        with h5py.File(temporary, "w") as merged:
            for episode, path in sources:
                name = f"episode_{episode}"
                with h5py.File(str(path), "r") as raw:
                    if name not in raw:
                        raise MergeError(f"{path}: 缺少 {name}")
                    raw.copy(raw[name], merged, name=name)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    if delete_source:
        for _, path in sources:
            path.unlink(missing_ok=True)

    return {
        "task": task,
        "episode_count": len(sources),
        "target": str(target),
        "bytes": target.stat().st_size,
        "source_deleted": delete_source,
    }


def run_merge_only(
    input_dir: str | Path,
    output_dir: str | Path | None,
    env: str,
    delete_source: bool,
) -> dict[str, Any]:
    """``--merge-only`` 分支：沿用原独立脚本的参数与行为。"""
    source_dir = Path(input_dir).expanduser().resolve()
    target_dir = Path(output_dir).expanduser().resolve() if output_dir else source_dir
    if not source_dir.is_dir():
        raise MergeError(f"输入目录不存在：{source_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for task in parse_tasks(env):
        result = merge_task(source_dir, target_dir, task, delete_source)
        results.append(result)
        print(
            f"{task}: 合并 {result['episode_count']} 个 episode → "
            f"{result['target']}（{result['bytes'] / 2**30:.1f} GiB）",
            flush=True,
        )
    return {"merged": results}


# ── 生成 ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EpisodeJob:
    task: str
    episode: int
    attempt: int
    seed: int
    difficulty: str
    output_root: str
    repo_root: str
    # 已校验的本任务采样配置；普通 dict，随 job 一起 pickle 到 worker。
    # 注意：带上它之后 EpisodeJob 不再可哈希，不得用作 dict key。
    sampling_config: dict[str, Any] | None = field(default=None)
    # 本条 episode 的固定规格（新值注入）。不传 --episode-specs 时恒为 None，
    # 此时 gym.make 不多这个 kwarg，链路与改动前逐字相同。
    episode_spec: dict[str, Any] | None = field(default=None)

    @property
    def recovery_mode(self) -> str | None:
        """FailRecover 分档按 episode 序号决定，与 seed / attempt 无关（与骨架一致）。"""
        if self.episode <= 2:
            return "z"
        if self.episode <= 5:
            return "xy"
        return None

    def bump(self, seed: int) -> "EpisodeJob":
        return replace(self, attempt=self.attempt + 1, seed=seed)


class EpisodeSpecError(DatasetGenerationError):
    """``--episode-specs`` 的输入不合法。父进程建池之前就报错，绝不带进 worker。"""


#: 规格文档必须有的顶层字段；多一个未知字段也拒绝，避免拼错的键被静默忽略。
SPEC_DOCUMENT_FIELDS = frozenset(
    {
        "spec_schema_version",
        "task",
        "difficulty",
        "generator_seed",
        "derived_seed",
        "generator_version",
        "sampling_config_sha256",
        "episodes",
    }
)
#: 每条 episode 记录必须有的字段。
SPEC_RECORD_REQUIRED = ("episode", "task", "difficulty", "layout", "objects", "actions", "spec_sha256")


def _spec_canonical_json(payload: Any) -> str:
    """规范序列化：固定 UTF-8、键排序、固定分隔符、禁止 NaN。

    ⚠ 必须与 ``tests._shared.injection_specs.canonical_json`` 逐字节一致。生产代码不导入
    ``tests``，所以这里是第二份实现；``tests/lightweight/test_episode_specs.py`` 里有一条
    定向测试把两边锁在一起，改动任一侧都会立刻红。
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


#: 不进规格身份散列的字段；必须与 ``tests._shared.injection_specs.SHA_EXCLUDED_FIELDS`` 一致。
#: ``collision`` 是碰撞诊断结果而不是规格原文，检查器内部的无害优化会改变它的数值，
#: 不该因此让已冻结的规格全部对不上散列。
SPEC_SHA_EXCLUDED_FIELDS = frozenset({"spec_sha256", "collision"})


def spec_record_sha256(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key not in SPEC_SHA_EXCLUDED_FIELDS}
    return _sha256_bytes(_spec_canonical_json(payload).encode("utf-8"))


def _assert_finite(value: Any, where: str) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EpisodeSpecError(f"{where}: 出现非有限数 {value!r}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_finite(item, f"{where}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite(item, f"{where}[{index}]")


def validate_episode_spec(record: Mapping[str, Any], task: str, difficulty: str, where: str) -> None:
    """单条记录的格式校验：必备字段、任务／难度一致、有限数、散列自洽。"""
    missing = [key for key in SPEC_RECORD_REQUIRED if key not in record]
    if missing:
        raise EpisodeSpecError(f"{where}: 缺字段 {missing}")
    if record["task"] != task or record["difficulty"] != difficulty:
        raise EpisodeSpecError(
            f"{where}: 记录标称 {record['task']}/{record['difficulty']}，与文件的 {task}/{difficulty} 不符"
        )
    if not isinstance(record["episode"], int) or isinstance(record["episode"], bool):
        raise EpisodeSpecError(f"{where}: episode 必须是整数")
    _assert_finite({key: value for key, value in record.items() if key not in SPEC_SHA_EXCLUDED_FIELDS}, where)
    actual = spec_record_sha256(record)
    if actual != record["spec_sha256"]:
        raise EpisodeSpecError(f"{where}: spec_sha256 不符（重算 {actual}，文件写的 {record['spec_sha256']}）")


def load_spec_document(path: Path, task: str | None = None, difficulty: str | None = None) -> dict[str, Any]:
    """读一份规格文档并逐条校验，返回 ``{"task":..,"difficulty":..,"records":{episode: 记录}}``。"""
    if not path.is_file():
        raise EpisodeSpecError(f"找不到规格文件：{path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EpisodeSpecError(f"{path}: 不是合法 JSON：{exc}") from exc
    if not isinstance(document, dict):
        raise EpisodeSpecError(f"{path}: 顶层必须是对象")
    unknown = set(document) - SPEC_DOCUMENT_FIELDS
    if unknown:
        raise EpisodeSpecError(f"{path}: 出现未知顶层字段 {sorted(unknown)}")
    missing = SPEC_DOCUMENT_FIELDS - set(document)
    if missing:
        raise EpisodeSpecError(f"{path}: 缺顶层字段 {sorted(missing)}")
    doc_task = str(document["task"])
    doc_difficulty = str(document["difficulty"])
    if task is not None and doc_task != task:
        raise EpisodeSpecError(f"{path}: 文件是 {doc_task} 的规格，CLI 请求的是 {task}")
    if difficulty is not None and doc_difficulty != difficulty:
        raise EpisodeSpecError(f"{path}: 文件是 {doc_difficulty} 的规格，CLI 请求的是 {difficulty}")
    episodes = document["episodes"]
    if not isinstance(episodes, list) or not episodes:
        raise EpisodeSpecError(f"{path}: episodes 必须是非空列表")
    records: dict[int, dict[str, Any]] = {}
    for index, record in enumerate(episodes):
        if not isinstance(record, dict):
            raise EpisodeSpecError(f"{path}: 第 {index} 条不是对象")
        validate_episode_spec(record, doc_task, doc_difficulty, f"{path}#{index}")
        number = int(record["episode"])
        if number in records:
            raise EpisodeSpecError(f"{path}: episode {number} 重复")
        records[number] = record
    return {"task": doc_task, "difficulty": doc_difficulty, "records": records, "path": str(path)}


@dataclass(frozen=True)
class SpecGroup:
    """清单里的一组：一个任务／难度、一份规格、一个独立输出根、一段 episode 范围。"""

    task: str
    difficulty: str
    spec_path: str
    output_root: str
    episodes: tuple[int, ...]
    records: Mapping[int, Mapping[str, Any]]


def load_episode_specs(
    value: str | Path,
    repo_root: Path,
    output: Path,
    *,
    task: str | None = None,
    difficulty: str | None = None,
    episodes: Sequence[int] | None = None,
) -> list[SpecGroup]:
    """解析 ``--episode-specs``：既接受单份规格文件，也接受多组清单。

    * **单组**：文件顶层带 ``spec_schema_version``，配合 ``--env/--difficulty`` 与
      ``--episodes/--episode-start`` 使用，产物落 ``--output-dir`` 本身。
    * **清单**：文件顶层带 ``manifest_version``，一次调用把多个任务／难度的 job 混进
      同一套进程池；每组自带难度与独立输出根 ``<output>/<任务>/<难度>``。
      同任务不同难度的 seed 与 HDF5 文件名相同，因此**必须**分目录。
    """
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    if not path.is_file():
        raise EpisodeSpecError(f"找不到 --episode-specs 指向的文件：{path}")
    try:
        head = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EpisodeSpecError(f"{path}: 不是合法 JSON：{exc}") from exc
    if not isinstance(head, dict):
        raise EpisodeSpecError(f"{path}: 顶层必须是对象")

    if "manifest_version" in head:
        groups_raw = head.get("groups")
        if not isinstance(groups_raw, list) or not groups_raw:
            raise EpisodeSpecError(f"{path}: 清单的 groups 必须是非空列表")
        groups: list[SpecGroup] = []
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(groups_raw):
            if not isinstance(item, dict):
                raise EpisodeSpecError(f"{path}: 第 {index} 组不是对象")
            for key in ("task", "difficulty", "spec_path", "episodes"):
                if key not in item:
                    raise EpisodeSpecError(f"{path}: 第 {index} 组缺字段 {key}")
            group_task = str(item["task"])
            group_difficulty = str(item["difficulty"])
            if (group_task, group_difficulty) in seen:
                raise EpisodeSpecError(f"{path}: 组 {group_task}/{group_difficulty} 重复")
            seen.add((group_task, group_difficulty))
            spec_path = Path(item["spec_path"])
            if not spec_path.is_absolute():
                spec_path = (path.parent / spec_path).resolve()
            document = load_spec_document(spec_path, group_task, group_difficulty)
            wanted = [int(number) for number in item["episodes"]]
            unknown = [number for number in wanted if number not in document["records"]]
            if unknown:
                raise EpisodeSpecError(f"{spec_path}: 清单点名的 episode {unknown[:5]} 不在规格里")
            groups.append(
                SpecGroup(
                    task=group_task,
                    difficulty=group_difficulty,
                    spec_path=str(spec_path),
                    output_root=str(output / group_task / group_difficulty),
                    episodes=tuple(wanted),
                    records=document["records"],
                )
            )
        return groups

    if "spec_schema_version" not in head:
        raise EpisodeSpecError(f"{path}: 既不是规格文件（缺 spec_schema_version）也不是清单（缺 manifest_version）")

    document = load_spec_document(path, task, difficulty)
    wanted = list(episodes) if episodes is not None else sorted(document["records"])
    unknown = [number for number in wanted if number not in document["records"]]
    if unknown:
        raise EpisodeSpecError(f"{path}: 请求的 episode {unknown[:5]} 不在规格里")
    return [
        SpecGroup(
            task=document["task"],
            difficulty=document["difficulty"],
            spec_path=str(path),
            output_root=str(output),
            episodes=tuple(wanted),
            records=document["records"],
        )
    ]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ensure_layout() -> None:
    """只校验生成必需的路径。

    骨架还要求 ``data/robomme_data_h5``（官方 reference）存在，那是为了跑 1e-8 数值比对；
    本脚本不做该比对，而且该目录在本仓库根本不存在，照搬会直接失败。
    """
    required = (REPO_ROOT / "uv.lock", SRC_ROOT)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise DatasetGenerationError("缺少必需路径：" + ", ".join(missing))


def _prepare_output(value: str | Path) -> Path:
    requested = Path(value).expanduser()
    if requested.is_symlink():
        raise DatasetGenerationError(f"输出目录不能是符号链接：{requested}")
    parent = requested.parent
    while parent != parent.parent:
        if parent.exists() and parent.is_symlink():
            raise DatasetGenerationError(f"输出路径含符号链接父目录：{parent}")
        if parent == REPO_ROOT:
            break
        parent = parent.parent
    output = requested.resolve()
    repo = REPO_ROOT.resolve()
    if output == repo or not _inside(output, repo):
        raise DatasetGenerationError(f"输出目录必须在仓库内：{output}")
    if output.exists():
        if not output.is_dir():
            raise DatasetGenerationError(f"输出路径已存在且不是目录：{output}")
    else:
        output.mkdir(parents=True, exist_ok=True)
    return output


def _parse_gpus(value: str | Sequence[str | int]) -> tuple[str, ...]:
    """解析 --gpus。骨架把它锁死为 "0"，这里放开为逗号分隔的多卡。"""
    raw = value.split(",") if isinstance(value, str) else value
    gpus = tuple(str(item).strip() for item in raw if str(item).strip())
    if not gpus:
        raise DatasetGenerationError("--gpus 不能为空")
    if len(gpus) != len(set(gpus)):
        raise DatasetGenerationError(f"--gpus 有重复项：{gpus}")
    for gpu in gpus:
        if not gpu.isdigit():
            raise DatasetGenerationError(f"--gpus 只接受物理卡号：{gpu!r}")
    return gpus


def _runtime_bool(value: Any, torch_module: Any) -> bool:
    if isinstance(value, torch_module.Tensor):
        if value.numel() != 1:
            raise DatasetGenerationError("evaluate 返回了非标量 Tensor")
        return bool(value.detach().cpu().item())
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise DatasetGenerationError("evaluate 返回了非标量 ndarray")
        return bool(value.item())
    return bool(value)


def _is_failure(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and int(value) == -1


def _planner_classes(
    arm_base: type,
    stick_base: type,
    screw_error: type[BaseException],
) -> tuple[type, type]:
    """局部子类实现 screw 三次 → RRTStar 三次的回退，不做 monkeypatch（与骨架一致）。"""

    class ScrewThenRRT:
        def move_to_pose_with_screw(self, *args: Any, **kwargs: Any) -> Any:
            last_error: BaseException | None = None
            for _ in range(3):
                try:
                    result = super().move_to_pose_with_screw(*args, **kwargs)
                except screw_error as exc:
                    last_error = exc
                    continue
                if not _is_failure(result):
                    return result
            for _ in range(3):
                try:
                    result = super().move_to_pose_with_RRTStar(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    continue
                if not _is_failure(result):
                    return result
            suffix = f": {last_error}" if last_error is not None else ""
            raise PlannerExhausted("screw 三次与 RRTStar 三次均失败" + suffix)

    class NoPatchArm(ScrewThenRRT, arm_base):
        pass

    class NoPatchStick(ScrewThenRRT, stick_base):
        pass

    return NoPatchArm, NoPatchStick


def _execute_tasks(record_env: Any, planner: Any, torch_module: Any, job: EpisodeJob) -> None:
    """成功判定与骨架逐字相同：跑完 task_list 且 evaluate 报 success 真、fail 假。"""
    task_list = list(getattr(record_env.unwrapped, "task_list", []) or [])
    if not task_list:
        raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: task_list 为空")
    for entry in task_list:
        solve = entry.get("solve") if isinstance(entry, Mapping) else None
        if not callable(solve):
            raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: task 没有 solve 方法")
        record_env.unwrapped.evaluate(solve_complete_eval=True)
        result = solve(record_env, planner)
        if _is_failure(result):
            raise PlannerExhausted(f"{job.task}/episode_{job.episode}: solve 返回 -1")
        evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
        if _runtime_bool(evaluation.get("fail", False), torch_module):
            raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: 环境报告失败")
        if _runtime_bool(evaluation.get("success", False), torch_module):
            return
    evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
    if not _runtime_bool(evaluation.get("success", False), torch_module):
        raise DatasetGenerationError(f"{job.task}/episode_{job.episode}: 跑完整个 task_list 仍未成功")


def _raw_summary(path: Path, job: EpisodeJob) -> dict[str, Any]:
    """worker 成功后立刻用同文件内的合约辅助函数检查原始轨迹的终态。"""
    if not path.is_file():
        raise DatasetGenerationError(f"缺少原始 HDF5：{path}")
    name = f"episode_{job.episode}"
    with h5py.File(path, "r") as handle:
        if name not in handle or not isinstance(handle[name], h5py.Group):
            raise DatasetGenerationError(f"{path}: 缺少 {name}")
        timesteps, done, errors = inspect_episode_terminal(handle[name], f"{path}/{name}")
        if errors:
            raise DatasetGenerationError("; ".join(errors))
        if done is not True:
            raise DatasetGenerationError(f"{path}/{name}: 末帧 is_completed 不为真")
    return {"h5_path": str(path), "timestep_count": len(timesteps)}


def _h5_path(output_root: Path, job: EpisodeJob) -> Path:
    """与 RecordWrapper 的命名约定一致（RecordWrapper.py:145,152）。"""
    return output_root / "hdf5_files" / f"{job.task}_ep{job.episode}_seed{job.seed}.h5"


# ── 视频核验（录像器冻结，这里只做只读观测）────────────────────────────────
# RobommeRecordWrapper 不改、不覆盖、不打补丁：视频就是它现有逻辑的产出。
# 下面只在 close() 之后按命名规则找文件、数帧、算散列，四态如实登记。
# 视频判定失败**不改变** HDF5 的 ok 判定，样本也不移出分母。
VIDEO_STATUS_COMPLETE = "complete"
VIDEO_STATUS_FRAME_MISMATCH = "frame_mismatch"
VIDEO_STATUS_MISSING = "missing"
VIDEO_STATUS_NO_CLOSE = "no_close"


def _video_candidates(videos_dir: Path, task: str, episode: int, seed: int) -> tuple[list[Path], list[Path]]:
    """按 ``<任务>_ep<k>_seed<s>`` 前缀找主视频与 NO_OBJECT 调试视频。

    命名来自 ``RecordWrapper`` 的 ``video_prefix``＝``f"{env_id}_ep{episode}_seed{seed}{fail_recover_suffix}"``，
    成功名无前缀、失败名加 ``FAILED_``；``NO_OBJECT`` 调试视频另有
    ``success_NO_OBJECT_`` / ``FAILED_NO_OBJECT_`` 前缀，不当主视频。
    """
    if not videos_dir.is_dir():
        return [], []
    base = f"{task}_ep{episode}_seed{seed}"
    main = [path for path in videos_dir.glob(f"{base}*.mp4") if "NO_OBJECT" not in path.name]
    main += [path for path in videos_dir.glob(f"FAILED_{base}*.mp4") if "NO_OBJECT" not in path.name]
    no_object = sorted(videos_dir.glob(f"success_NO_OBJECT_{base}*.mp4")) + sorted(
        videos_dir.glob(f"FAILED_NO_OBJECT_{base}*.mp4")
    )
    return sorted(main), no_object


def _probe_frame_count(path: Path) -> tuple[int | None, str | None]:
    """``ffprobe -count_frames`` 逐帧数，不用容器头里的估计值。"""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries", "stream=nb_read_frames",
        "-of", "default=nokey=1:noprint_wrappers=1", str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        return None, "找不到 ffprobe"
    except subprocess.TimeoutExpired:
        return None, "ffprobe 超时"
    if completed.returncode != 0:
        return None, f"ffprobe 退出码 {completed.returncode}: {completed.stderr.strip()[:200]}"
    text = completed.stdout.strip()
    if not text.isdigit():
        return None, f"ffprobe 输出不是帧数：{text[:80]!r}"
    return int(text), None


def _video_summary(
    output_root: Path,
    job: EpisodeJob,
    *,
    timestep_count: int | None,
    close_error: str | None,
) -> dict[str, Any]:
    """``close()`` 之后的纯观测核验，返回一条 ``video`` 记录。

    成功局要求「帧数 == HDF5 的 timestep 数」——这是可核验的等式，因为录像器从正式
    ``reset()`` 后第一次 ``step`` 的观测起记到终止为止，``NO RECORD`` 阶段按设计跳过。
    ``FAILED_`` 视频没有 HDF5 可比，只要求帧数 > 0 且可解码。
    """
    videos_dir = output_root / "videos"
    main, no_object = _video_candidates(videos_dir, job.task, job.episode, job.seed)
    payload: dict[str, Any] = {
        "status": VIDEO_STATUS_MISSING,
        "path": None,
        "frames": None,
        "frames_expected": timestep_count,
        "bytes": None,
        "sha256": None,
        "no_object_paths": [str(item) for item in no_object],
        "reason": None,
    }
    if not main:
        payload["reason"] = "videos/ 下没有匹配前缀的主视频" + (f"；close 抛出 {close_error}" if close_error else "")
        return payload
    if len(main) > 1:
        payload["reason"] = f"同一前缀匹配到 {len(main)} 个主视频：{[item.name for item in main]}"
    path = main[0]
    payload["path"] = str(path)
    payload["bytes"] = path.stat().st_size
    payload["sha256"] = _sha256_bytes(path.read_bytes())
    frames, error = _probe_frame_count(path)
    payload["frames"] = frames
    if frames is None:
        payload["status"] = VIDEO_STATUS_FRAME_MISMATCH
        payload["reason"] = error
        return payload
    failed_video = path.name.startswith("FAILED_")
    if failed_video:
        payload["status"] = VIDEO_STATUS_COMPLETE if frames > 0 else VIDEO_STATUS_FRAME_MISMATCH
        if frames <= 0:
            payload["reason"] = "FAILED_ 视频帧数为 0"
        return payload
    if timestep_count is None:
        payload["status"] = VIDEO_STATUS_FRAME_MISMATCH
        payload["reason"] = "成功名视频但没有可比的 HDF5 timestep 数"
        return payload
    if frames != timestep_count:
        payload["status"] = VIDEO_STATUS_FRAME_MISMATCH
        payload["reason"] = f"帧数 {frames} != HDF5 timestep 数 {timestep_count}"
        return payload
    payload["status"] = VIDEO_STATUS_COMPLETE
    return payload


def _pool_init(gpu: str, cpus: tuple[int, ...] | None, src_root: str) -> None:
    """池进程一生只跑一次：绑卡、压线程、预热 import。

    绑卡必须早于任何 torch / sapien import —— 此刻 CUDA 尚未初始化（本模块顶层只 import
    了 h5py/numpy，二者不碰 CUDA），所以 setenv 有效且对该进程终身有效。
    GPU 号是池的静态属性（从 initargs 来），因此 worker 被回收或崩溃重建后依然正确。
    """
    global _BOUND
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu

    limit_threads = os.environ.get(LIMIT_THREADS_ENV, "1") != "0"
    if limit_threads:
        _apply_thread_env("1")

    # CPU 亲和会被 ffmpeg 子进程继承 —— x264 按 sched_getaffinity 自动决定线程数，
    # 不看 OMP_NUM_THREADS，这是唯一能在不改 RecordWrapper 的前提下压住它的手段。
    if cpus:
        try:
            os.sched_setaffinity(0, set(cpus))
        except OSError:
            pass

    if src_root not in sys.path:
        sys.path.insert(0, src_root)

    # initializer 里抛异常会让整个池立刻 broken，所以全部包起来
    info: dict[str, Any] = {"gpu": gpu, "pid": os.getpid()}
    try:
        import cv2
        import torch

        if limit_threads:
            torch.set_num_threads(1)
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass  # 已有并行工作启动过就不能再设，忽略
            cv2.setNumThreads(0)

        import gymnasium  # noqa: F401
        import sapien

        import robomme.robomme_env  # noqa: F401
        from robomme.env_record_wrapper import RobommeRecordWrapper  # noqa: F401

        device = sapien.Device("cuda")
        info.update(
            {
                "cuda_id": getattr(device, "cuda_id", None),
                "pci": getattr(device, "pci_string", None),
                "can_render": bool(device.can_render()),
                "torch_threads": torch.get_num_threads(),
            }
        )
    except Exception as exc:
        info["error"] = repr(exc)
    try:
        info["affinity"] = sorted(os.sched_getaffinity(0))
    except OSError:
        pass
    _BOUND = info


def _worker(job: EpisodeJob) -> dict[str, Any]:
    """跑一次 attempt。重试由父进程负责（失败的 job 会带新 seed 重新入队）。"""
    started = time.time()
    clock = time.monotonic()
    phases: dict[str, float] = {}
    output_root = Path(job.output_root)
    raw_path = _h5_path(output_root, job)
    record_env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None
    close_error: str | None = None
    runtime_checks: list[dict[str, Any]] = []
    injection_evidence: dict[str, Any] = {}

    # import 单独成段：若这里失败，下面的 except 子句会因为异常类未定义而变成 NameError
    try:
        source_root = Path(job.repo_root) / "src"
        if not source_root.is_dir():
            raise DatasetGenerationError(f"src 不存在：{source_root}")
        if str(source_root) not in sys.path:
            sys.path.insert(0, str(source_root))
        import gymnasium as gym
        import torch
        import robomme.robomme_env  # noqa: F401
        from robomme.env_record_wrapper import FailsafeTimeout, RobommeRecordWrapper
        from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
        from robomme.robomme_env.utils.bin_collision import BinCollisionError, SpecBindingError
        from robomme.robomme_env.utils.planner_fail_safe import (
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )

        arm_cls, stick_cls = _planner_classes(
            FailAwarePandaArmMotionPlanningSolver,
            FailAwarePandaStickMotionPlanningSolver,
            ScrewPlanFailure,
        )
    except Exception as exc:
        return {
            "task": job.task,
            "episode": job.episode,
            "attempt": job.attempt,
            "seed": job.seed,
            "difficulty": job.difficulty,
            "recovery_mode": job.recovery_mode,
            "bound": dict(_BOUND),
            "ok": False,
            "failure_class": "code",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "finished_at": time.time(),
        }

    # 这几类是「该 seed / 该样本不通」，属于任务性失败；其余异常视为代码/环境层面的真 bug。
    # ⚠ 新增的两类是新值注入的运行时判据：碰撞拒绝与「实际对象／动作不符」。归到任务性失败
    # 只是为了不被 MAX_NON_TASK_STRIKES 当成代码 bug；正式实跑固定 --max-attempts 1，
    # 因此它们**不会**触发换 seed 重试——计划明确禁止换 seed、换搭档、补位。
    retryable = (
        SceneGenerationError,
        FailsafeTimeout,
        PlannerExhausted,
        ScrewPlanFailure,
        DatasetGenerationError,
        BinCollisionError,
        SpecBindingError,
    )

    try:
        # 以下 kwargs 与骨架逐字相同，不要改动
        kwargs: dict[str, Any] = {
            "obs_mode": "rgb+depth+segmentation",
            "control_mode": "pd_joint_pos",
            "render_mode": "rgb_array",
            "reward_mode": "dense",
            "seed": job.seed,
            "difficulty": job.difficulty,
        }
        if job.recovery_mode is not None:
            kwargs["robomme_failure_recovery"] = True
            kwargs["robomme_failure_recovery_mode"] = job.recovery_mode
        # 只有显式传了 --sampling-config 才多这一个 kwarg；不传时 kwargs 与原版逐字相同
        if job.sampling_config is not None:
            kwargs["sampling_config"] = job.sampling_config
        # 同理，只有显式传了 --episode-specs 才多这一个 kwarg（DEFAULT_PARITY 靠这条成立）
        if job.episode_spec is not None:
            kwargs["episode_spec"] = job.episode_spec

        mark = time.monotonic()
        base_env = gym.make(job.task, **kwargs)
        # 产物直接落共享输出根：h5 进 hdf5_files/、视频进 videos/，
        # 文件名已含 task/episode/seed 天然唯一，因此不需要 per-job 的临时目录。
        record_env = RobommeRecordWrapper(
            base_env,
            dataset=str(output_root),
            env_id=job.task,
            episode=job.episode,
            seed=job.seed,
            save_video=True,
        )
        phases["make_s"] = time.monotonic() - mark

        mark = time.monotonic()
        record_env.reset()
        phases["reset_s"] = time.monotonic() - mark

        planner_kwargs: dict[str, Any] = {
            "debug": False,
            "vis": False,
            "base_pose": record_env.unwrapped.agent.robot.pose,
            "visualize_target_grasp_pose": False,
            "print_env_info": False,
        }
        if job.task in STICK_TASKS:
            planner_kwargs["joint_vel_limits"] = 0.3
            planner = stick_cls(record_env, **planner_kwargs)
        else:
            planner = arm_cls(record_env, **planner_kwargs)

        mark = time.monotonic()
        _execute_tasks(record_env, planner, torch, job)
        phases["solve_s"] = time.monotonic() - mark
    except Exception as exc:
        caught = exc
        error_traceback = traceback.format_exc()
    finally:
        if record_env is not None:
            # ⚠ 必须在 close() **之前**把运行时检查证据取出来：close 之后环境被拆掉，
            # 两个视频任务在 _initialize_episode / step / 子步里累积的 _runtime_checks
            # 就没了，COLLISION_RUNTIME 的 checked / missing_checks 将无从计算。
            try:
                runtime_checks = [dict(item) for item in getattr(record_env.unwrapped, "_runtime_checks", [])]
            except Exception:  # noqa: BLE001 - 取证据失败不能影响主流程
                runtime_checks = []
            try:
                injection_evidence = dict(getattr(record_env.unwrapped, "_injection_evidence", {}) or {})
            except Exception:  # noqa: BLE001
                injection_evidence = {}
            mark = time.monotonic()
            try:
                # h5 落盘与 mp4 编码都发生在 close 里
                record_env.close()
            except Exception as close_exc:
                close_error = f"{type(close_exc).__name__}: {close_exc}"
                if caught is None:
                    caught = close_exc
                    error_traceback = traceback.format_exc()
            phases["close_s"] = time.monotonic() - mark

    base = {
        "task": job.task,
        "episode": job.episode,
        "attempt": job.attempt,
        "seed": job.seed,
        "difficulty": job.difficulty,
        "recovery_mode": job.recovery_mode,
        "bound": dict(_BOUND),
        # 运行时检查的四态证据与注入绑定证据：成功失败都带，供 COLLISION_RUNTIME 与
        # INJECTION_BINDING 统计；不传规格时两者都是空的
        "runtime_checks": runtime_checks,
        "injection_evidence": injection_evidence,
        "phases": {name: round(value, 3) for name, value in phases.items()},
        "wall_s": round(time.monotonic() - clock, 3),
        "started_at": started,
        "finished_at": time.time(),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }
    if caught is not None:
        # 失败的 attempt 不写 h5 内容（RecordWrapper 只在 episode_success 时写），
        # 但文件在 __init__ 里就被创建了，会留下几 KB 空壳 —— 删掉，
        # 让 hdf5_files/ 里只剩真正成功的轨迹。FAILED_ 视频保留作为失败演进的证据。
        _discard_empty_h5(raw_path, job)
        return {
            **base,
            "ok": False,
            "failure_class": "task" if isinstance(caught, retryable) else "code",
            "error_type": type(caught).__name__,
            "error": str(caught),
            "traceback": error_traceback,
            # 视频核验是纯观测：失败局同样登记，FAILED_ 视频只要能解码就算完整
            "video": _video_summary(output_root, job, timestep_count=None, close_error=close_error),
        }
    try:
        summary = _raw_summary(raw_path, job)
    except Exception as exc:
        _discard_empty_h5(raw_path, job)
        return {
            **base,
            "ok": False,
            "failure_class": "task" if isinstance(exc, retryable) else "code",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "video": _video_summary(output_root, job, timestep_count=None, close_error=close_error),
        }
    # ⚠ 视频核验放在 ok 判定**之后**且不参与它：视频缺失或帧数不符只让 VIDEO_* 判定失败，
    # 不改变任务结果，也不删已经落盘的 HDF5。
    return {
        **base,
        "ok": True,
        **summary,
        "video": _video_summary(
            output_root, job, timestep_count=summary.get("timestep_count"), close_error=close_error
        ),
    }


def _discard_empty_h5(path: Path, job: EpisodeJob) -> None:
    """删掉失败 attempt 留下的空 h5；万一里面确实有内容就保留，交人工判断。"""
    if not path.is_file():
        return
    try:
        with h5py.File(path, "r") as handle:
            if f"episode_{job.episode}" in handle:
                return
    except Exception:
        pass  # 打不开就是坏文件，照删
    try:
        path.unlink()
    except OSError:
        pass


def _synth_failure(job: EpisodeJob, exc: BaseException, failure_class: str) -> dict[str, Any]:
    """worker 进程本身没能返回结果（池崩溃 / 被杀）时，父进程合成一条记录。"""
    return {
        "task": job.task,
        "episode": job.episode,
        "attempt": job.attempt,
        "seed": job.seed,
        "difficulty": job.difficulty,
        "recovery_mode": job.recovery_mode,
        "ok": False,
        "failure_class": failure_class,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "finished_at": time.time(),
        # 池崩溃／被杀：worker 没能返回结果，就一定没走到 close()，视频没写出来
        "video": {
            "status": VIDEO_STATUS_NO_CLOSE,
            "path": None,
            "frames": None,
            "frames_expected": None,
            "bytes": None,
            "sha256": None,
            "no_object_paths": [],
            "reason": f"worker 未返回结果（{failure_class}）：{type(exc).__name__}",
        },
    }


def _run_jobs(
    jobs: Sequence[EpisodeJob],
    gpu_ids: Sequence[str],
    workers: int,
    layout_name: str,
    jsonl_path: Path,
    max_attempts: int,
    max_tasks_per_child: int | None,
    cpu_plan: Mapping[str, tuple[int, ...] | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """每卡一个池，按剩余容量动态派发；失败 attempt+1 重新入队；池崩溃则重建。"""
    layout = get_layout(layout_name)
    context = mp.get_context("spawn")
    per_gpu = max(1, workers // len(gpu_ids))

    def new_pool(gpu: str) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=per_gpu,
            mp_context=context,
            initializer=_pool_init,
            initargs=(gpu, cpu_plan.get(gpu), str(SRC_ROOT)),
            max_tasks_per_child=max_tasks_per_child,
        )

    pools = {gpu: new_pool(gpu) for gpu in gpu_ids}
    capacity = {gpu: per_gpu for gpu in gpu_ids}
    pending: deque[EpisodeJob] = deque(jobs)
    inflight: dict[Future, tuple[str, EpisodeJob]] = {}
    succeeded: list[dict[str, Any]] = []
    exhausted: list[dict[str, Any]] = []
    total = len(jobs)
    # 连续的非任务性失败（真 bug、池崩溃）计数，用来避免对着同一个 bug 空转到 attempt 上限
    strikes: dict[tuple[str, int], int] = {}

    with jsonl_path.open("a", buffering=1, encoding="utf-8") as sink:

        def record(result: Mapping[str, Any]) -> None:
            sink.write(json.dumps(result, ensure_ascii=False) + "\n")

        while pending or inflight:
            while pending and any(capacity[gpu] > 0 for gpu in gpu_ids):
                gpu = max(gpu_ids, key=lambda item: capacity[item])
                if capacity[gpu] <= 0:
                    break
                job = pending.popleft()
                inflight[pools[gpu].submit(_worker, job)] = (gpu, job)
                capacity[gpu] -= 1

            if not inflight:
                break
            finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)

            broken: set[str] = set()
            for future in finished:
                gpu, job = inflight.pop(future)
                capacity[gpu] += 1
                try:
                    result = future.result()
                except BrokenProcessPool as exc:
                    broken.add(gpu)
                    result = _synth_failure(job, exc, "infra")
                except BaseException as exc:  # noqa: BLE001
                    result = _synth_failure(job, exc, "infra")
                record(result)
                key = (job.task, job.episode)
                if result.get("ok"):
                    strikes.pop(key, None)
                    succeeded.append(result)
                    print(
                        f"[{len(succeeded)}/{total}] {job.task}/episode_{job.episode} "
                        f"succeeded with seed {job.seed} (attempt {job.attempt}, "
                        f"{result.get('wall_s')}s)",
                        flush=True,
                    )
                    continue

                if result.get("failure_class") == "task":
                    strikes.pop(key, None)
                else:
                    strikes[key] = strikes.get(key, 0) + 1

                if strikes.get(key, 0) >= MAX_NON_TASK_STRIKES:
                    exhausted.append(result)
                    print(
                        f"    {job.task}/episode_{job.episode} 连续 {MAX_NON_TASK_STRIKES} 次非任务性失败"
                        f"（{result.get('error_type')}），判定为代码问题，放弃",
                        flush=True,
                    )
                elif job.attempt + 1 < max_attempts:
                    print(
                        f"    {job.task}/episode_{job.episode} seed {job.seed} failed "
                        f"({result.get('error_type')}), retrying attempt {job.attempt + 1}",
                        flush=True,
                    )
                    pending.append(job.bump(layout.seed(job.task, job.episode, job.attempt + 1)))
                else:
                    exhausted.append(result)
                    print(
                        f"    {job.task}/episode_{job.episode} 用尽 {max_attempts} 次 attempt，放弃",
                        flush=True,
                    )

            # 池整体崩溃（worker 段错误会让 in-flight 与 pending 的 future 全部失败）：
            # 重建该池，并把它名下未完成的 job 退回队列，否则一次段错误就会报废整批任务。
            for gpu in broken:
                print(f"    GPU {gpu} 的进程池已损坏，正在重建", flush=True)
                for future, (owner, job) in list(inflight.items()):
                    if owner != gpu:
                        continue
                    inflight.pop(future)
                    capacity[gpu] += 1
                    record(_synth_failure(job, RuntimeError("池重建，任务退回队列"), "infra"))
                    if job.attempt + 1 < max_attempts:
                        pending.appendleft(
                            job.bump(layout.seed(job.task, job.episode, job.attempt + 1))
                        )
                    else:
                        exhausted.append(_synth_failure(job, RuntimeError("池重建且已用尽 attempt"), "infra"))
                try:
                    pools[gpu].shutdown(wait=False, cancel_futures=True)
                except Exception:  # noqa: BLE001
                    pass
                pools[gpu] = new_pool(gpu)
                capacity[gpu] = per_gpu

    for pool in pools.values():
        try:
            pool.shutdown(wait=True)
        except Exception:  # noqa: BLE001
            pass
    return succeeded, exhausted


def _write_metadata(output: Path, task: str, records: Sequence[Mapping[str, Any]]) -> None:
    """写出与 src/robomme/env_metadata 同构的 metadata（字段：task/episode/seed/difficulty）。"""
    payload = {
        "env_id": task,
        "record_count": len(records),
        "records": [
            {
                "task": str(item["task"]),
                "episode": int(item["episode"]),
                "seed": int(item["seed"]),
                "difficulty": str(item["difficulty"]),
            }
            for item in sorted(records, key=lambda item: int(item["episode"]))
        ],
    }
    write_text_atomic(
        output / f"record_dataset_{task}_metadata.json",
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _video_status_counts(*record_groups: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """汇总四态视频状态；没有 ``video`` 字段的旧记录计入 ``unrecorded``。"""
    counts = {
        VIDEO_STATUS_COMPLETE: 0,
        VIDEO_STATUS_FRAME_MISMATCH: 0,
        VIDEO_STATUS_MISSING: 0,
        VIDEO_STATUS_NO_CLOSE: 0,
        "unrecorded": 0,
    }
    for records in record_groups:
        for item in records:
            video = item.get("video")
            status = video.get("status") if isinstance(video, Mapping) else None
            counts[status if status in counts else "unrecorded"] += 1
    return counts


def _cpu_plan(gpu_ids: Sequence[str], affinity: str) -> dict[str, tuple[int, ...] | None]:
    """把物理核按卡切分。exclusive 模式下每个池只能用自己那一段，用于压住 x264 的自动并行。"""
    if affinity == "none":
        return {gpu: None for gpu in gpu_ids}
    try:
        available = sorted(os.sched_getaffinity(0))
    except OSError:
        available = list(range(os.cpu_count() or 1))
    chunk = max(1, len(available) // len(gpu_ids))
    plan: dict[str, tuple[int, ...] | None] = {}
    for index, gpu in enumerate(gpu_ids):
        start = index * chunk
        end = len(available) if index == len(gpu_ids) - 1 else start + chunk
        plan[gpu] = tuple(available[start:end])
    return plan


def generate_dataset_newseed(
    output_dir: str | Path,
    env: str = "all",
    episodes: int = MAX_EPISODES,
    episode_start: int = 0,
    workers: int = DEFAULT_WORKERS,
    gpus: str | Sequence[str | int] = "0",
    difficulty_ratio: str = DEFAULT_DIFFICULTY_RATIO,
    layout_name: str = DEFAULT_LAYOUT,
    max_attempts: int = MAX_ATTEMPTS,
    limit_threads: bool = True,
    max_tasks_per_child: int | None = DEFAULT_MAX_TASKS_PER_CHILD,
    affinity: str = "none",
    sampling_config: str | Path | None = None,
    episode_specs: str | Path | None = None,
) -> dict[str, Any]:
    _ensure_layout()
    if episodes < 1:
        raise DatasetGenerationError("episodes 必须大于 0")
    if episode_start < 0:
        raise DatasetGenerationError("episode-start 必须不小于 0")
    if workers < 1:
        raise DatasetGenerationError("workers 必须大于 0")
    if not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise DatasetGenerationError(f"max-attempts 必须落在 1..{MAX_ATTEMPTS}")

    output = _prepare_output(output_dir)
    tasks = parse_tasks(env)
    gpu_ids = _parse_gpus(gpus)
    layout = get_layout(layout_name)
    cycle = parse_difficulty_ratio(difficulty_ratio)

    # 父进程只读一次配置：加载、校验、复制，不采样、不导入仿真。
    # 配置只覆盖四个任务，其余 12 个任务照原默认值生成。
    task_configs: dict[str, dict[str, Any]] = {}
    if sampling_config is not None:
        task_configs = load_sampling_config(sampling_config, REPO_ROOT)

    # 新值注入：父进程只读一次规格，校验、索引；建池之前就拒绝错误输入，绝不带进 worker。
    # 不传 --episode-specs 时 spec_groups 为空，下面所有分支都退回原路径。
    spec_groups: list[SpecGroup] = []
    if episode_specs is not None:
        single_difficulty = None
        if len(set(cycle)) == 1:
            single_difficulty = cycle[0]
        spec_groups = load_episode_specs(
            episode_specs,
            REPO_ROOT,
            output,
            task=tasks[0] if len(tasks) == 1 else None,
            difficulty=single_difficulty,
            episodes=list(range(episode_start, episode_start + episodes)),
        )
        if len(spec_groups) > 1:
            # 清单模式：任务、难度、输出根全部由清单决定，--env/--difficulty 不再参与
            tasks = sorted({group.task for group in spec_groups})

    # 护栏：episode 号太大时 seed 会越过下一代布局的 offset，与 test/val/heldout 的 seed 空间相撞。
    next_offsets = [item.offset for item in LAYOUTS.values() if item.offset > layout.offset]
    if next_offsets:
        seed_ceiling = min(next_offsets)
        if spec_groups:
            ceiling_checks = [(group.task, max(group.episodes)) for group in spec_groups]
        else:
            ceiling_checks = [(task, episode_start + episodes - 1) for task in tasks]
        for task, last_episode in ceiling_checks:
            max_seed = layout.seed(task, last_episode, MAX_ATTEMPTS - 1)
            if max_seed >= seed_ceiling:
                raise DatasetGenerationError(
                    f"{task} episode {last_episode} 的最大可能 seed {max_seed} "
                    f"越过下一代布局的 offset {seed_ceiling}，请缩小 episode 范围"
                )

    # 父进程在建池之前定好线程环境；spawn 的子进程会继承，
    # 并在重跑本模块顶层时（早于 import numpy）据此设置 OpenBLAS/libgomp。
    os.environ[LIMIT_THREADS_ENV] = "1" if limit_threads else "0"
    if limit_threads:
        _apply_thread_env("1")
    else:
        _clear_thread_env()

    if spec_groups:
        # 按 episode 轮转入队：同一时刻在跑的 job 分散在各任务上，避免整批堆在同一个任务里。
        jobs = []
        depth = max(len(group.episodes) for group in spec_groups)
        for index in range(depth):
            for group in spec_groups:
                if index >= len(group.episodes):
                    continue
                episode = group.episodes[index]
                jobs.append(
                    EpisodeJob(
                        task=group.task,
                        episode=episode,
                        attempt=0,
                        seed=layout.seed(group.task, episode, 0),
                        difficulty=group.difficulty,
                        output_root=group.output_root,
                        repo_root=str(REPO_ROOT),
                        sampling_config=copy.deepcopy(task_configs[group.task]) if group.task in task_configs else None,
                        # 每个 job 一份独立深拷贝：worker 之间、同一 worker 的前后两局之间不共享可变缓存
                        episode_spec=copy.deepcopy(dict(group.records[episode])),
                    )
                )
        for group in spec_groups:
            Path(group.output_root).mkdir(parents=True, exist_ok=True)
    else:
        jobs = [
            EpisodeJob(
                task=task,
                episode=episode,
                attempt=0,
                seed=layout.seed(task, episode, 0),
                difficulty=difficulty_for(episode, cycle),
                output_root=str(output),
                repo_root=str(REPO_ROOT),
                # 每个 job 拿一份独立副本，worker 之间、同一 worker 的前后两局之间互不共享
                sampling_config=copy.deepcopy(task_configs[task]) if task in task_configs else None,
            )
            for task in tasks
            for episode in range(episode_start, episode_start + episodes)
        ]

    parameters = {
        "output_dir": str(output),
        "env": env,
        "tasks": tasks,
        "episodes": episodes,
        "episode_start": episode_start,
        "workers": workers,
        "gpus": list(gpu_ids),
        "seed_layout": layout_name,
        "difficulty_ratio": difficulty_ratio,
        "difficulty_cycle": list(cycle),
        "max_attempts": max_attempts,
        "limit_threads": limit_threads,
        "max_tasks_per_child": max_tasks_per_child,
        "affinity": affinity,
        "save_video_for_recording": True,
        "sampling_config": str(sampling_config) if sampling_config is not None else None,
        "sampling_config_tasks": sorted(task_configs),
        "episode_specs": str(episode_specs) if episode_specs is not None else None,
        "episode_spec_groups": [
            {
                "task": group.task,
                "difficulty": group.difficulty,
                "spec_path": group.spec_path,
                "output_root": group.output_root,
                "episodes": list(group.episodes),
            }
            for group in spec_groups
        ],
        "requested_jobs": len(jobs),
    }
    write_text_atomic(
        output / "run_parameters.json",
        json.dumps(parameters, ensure_ascii=False, indent=2) + "\n",
    )
    if task_configs:
        # 额外配置作为运行目录里的独立快照留档；原 HDF5、原 metadata 结构不变
        write_text_atomic(
            output / "sampling_config_used.json",
            json.dumps(task_configs, ensure_ascii=False, indent=2) + "\n",
        )

    started = time.monotonic()
    succeeded, exhausted = _run_jobs(
        jobs=jobs,
        gpu_ids=gpu_ids,
        workers=workers,
        layout_name=layout_name,
        jsonl_path=output / "episode_results.jsonl",
        max_attempts=max_attempts,
        max_tasks_per_child=max_tasks_per_child,
        cpu_plan=_cpu_plan(gpu_ids, affinity),
    )
    elapsed = time.monotonic() - started

    if spec_groups:
        # 每组写到自己的输出根：同任务不同难度的 HDF5 文件名相同，metadata 也必须分开
        for group in spec_groups:
            group_records = [
                item
                for item in succeeded
                if item["task"] == group.task and item.get("difficulty") == group.difficulty
            ]
            if group_records:
                _write_metadata(Path(group.output_root), group.task, group_records)
    else:
        for task in tasks:
            task_records = [item for item in succeeded if item["task"] == task]
            if task_records:
                _write_metadata(output, task, task_records)

    summary = {
        "parameters": parameters,
        "requested_count": len(jobs),
        "success_count": len(succeeded),
        "exhausted_count": len(exhausted),
        "elapsed_s": round(elapsed, 1),
        "throughput_ep_per_min": round(len(succeeded) / (elapsed / 60), 2) if elapsed > 0 else None,
        "peak_rss_mb": max((item.get("peak_rss_mb") or 0 for item in succeeded), default=0),
        # 视频状态计数与 ok 判定分开统计：视频判定失败不改变任务结果，但必须如实汇总
        "video_status_counts": _video_status_counts(succeeded, exhausted),
    }
    write_text_atomic(
        output / "run_summary.json",
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    return summary


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="无 seed 独立生成：seed 由公式自算，失败自动 attempt+1 重试；"
        "另提供 --extract-config 与 --merge-only 两个辅助入口"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--extract-config",
        default=None,
        metavar="JSON",
        help="只读源码 AST，导出原版采样输入到该 JSON；配合 --check-config 则只核对不写入",
    )
    mode.add_argument(
        "--merge-only",
        action="store_true",
        help="只把每 episode 的 h5 合并成 record_dataset_{task}.h5，不生成",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="配合 --extract-config：只核对既有快照与当前工作树源码，不写入",
    )
    parser.add_argument(
        "--source-ref",
        default=None,
        help="配合 --extract-config --check-config：额外与该 Git 提交的原版操作元对照",
    )
    parser.add_argument(
        "--sampling-config",
        default=None,
        metavar="JSON",
        help="常规生成时显式传入四任务的原版采样输入；不传则走源码默认值",
    )
    parser.add_argument(
        "--episode-specs",
        default=None,
        metavar="JSON",
        help="新值注入：单份规格文件，或一次调用混跑多组的清单（顶层 manifest_version）；"
        "不传则走原随机路径，链路与改动前逐字相同",
    )
    parser.add_argument("--input-dir", default=None, help="--merge-only 的输入目录（生成输出目录）")
    parser.add_argument(
        "--delete-source",
        action="store_true",
        help="--merge-only：合并成功后删除每 episode 的源 h5（默认保留；合并期间两份并存，需要双倍空间）",
    )
    # 原为 required=True；三种模式分流后由常规生成与合并模式各自校验
    parser.add_argument("--output-dir", default=None, help="仓库内的输出目录")
    parser.add_argument("--env", "--environment", default="all", help="all 或逗号分隔的环境名")
    parser.add_argument("--episodes", type=int, default=MAX_EPISODES, help="每个环境的条数（配合 --episode-start）")
    parser.add_argument(
        "--episode-start",
        type=int,
        default=0,
        help="起始 episode 号（默认 0）；难度循环与 seed 都按绝对 episode 号计算，接续生成时口径自然延续",
    )
    parser.add_argument("--workers", "--max-workers", dest="workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--gpus", "--gpu", dest="gpus", default="0", help="逗号分隔的物理卡号，如 0,1")
    parser.add_argument(
        "--difficulty",
        dest="difficulty_ratio",
        default=DEFAULT_DIFFICULTY_RATIO,
        help="难度循环比例，三位数字对应 easy/medium/hard，如 211",
    )
    parser.add_argument("--layout", default=DEFAULT_LAYOUT, choices=sorted(LAYOUTS), help="seed 布局代")
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS, help="单个 episode 的最大 attempt 数")
    parser.add_argument(
        "--no-limit-threads",
        dest="limit_threads",
        action="store_false",
        help="不把每个 worker 的 CPU 线程压到 1（用于并行度标定的对照组）",
    )
    parser.add_argument(
        "--max-tasks-per-child",
        type=int,
        default=DEFAULT_MAX_TASKS_PER_CHILD,
        help="每个池进程跑多少 job 后回收，0 表示永不回收",
    )
    parser.add_argument(
        "--affinity",
        default="none",
        choices=("none", "per-gpu"),
        help="per-gpu 时把物理核按卡切分并绑定，用于压住 ffmpeg/x264 的自动并行",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)

    # 分流放在建池与导入仿真之前：提取与合并都不需要 GPU、worker 参数
    if args.extract_config is not None:
        try:
            report = run_extract_config(
                config_path=args.extract_config,
                repo_root=REPO_ROOT,
                check_only=args.check_config,
                source_ref=args.source_ref,
            )
        except SamplingConfigError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 0

    if args.check_config or args.source_ref is not None:
        print("ERROR: --check-config / --source-ref 只能配合 --extract-config 使用", file=sys.stderr)
        return 1

    if args.merge_only:
        if not args.input_dir:
            print("ERROR: --merge-only 需要 --input-dir", file=sys.stderr)
            return 1
        try:
            result = run_merge_only(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                env=args.env,
                delete_source=args.delete_source,
            )
        except MergeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if not args.output_dir:
        print("ERROR: 常规生成需要 --output-dir", file=sys.stderr)
        return 1
    try:
        summary = generate_dataset_newseed(
            output_dir=args.output_dir,
            env=args.env,
            episodes=args.episodes,
            episode_start=args.episode_start,
            workers=args.workers,
            gpus=args.gpus,
            difficulty_ratio=args.difficulty_ratio,
            layout_name=args.layout,
            max_attempts=args.max_attempts,
            limit_threads=args.limit_threads,
            max_tasks_per_child=args.max_tasks_per_child or None,
            affinity=args.affinity,
            sampling_config=args.sampling_config,
            episode_specs=args.episode_specs,
        )
    except (DatasetGenerationError, SamplingConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["exhausted_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
