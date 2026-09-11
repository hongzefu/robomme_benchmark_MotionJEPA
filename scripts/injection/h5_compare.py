"""HDF5 全字段逐位比较核（新值注入链路的对拍判据）。

从 ``tests/_shared/native_sampling_parity.py`` 抽出，供 ``scripts/injection/campaign.py``
的 ``compare`` 子命令使用；``tests/_shared/native_sampling_parity.py`` 反向 import 本模块并
re-export，parity 线的调用方与归档命令零改动。本模块不依赖 ``tests/``。

判据：遍历实际落盘树，逐 group / dataset / attribute 比较全集、dtype、shape、字符串编码与
逐元素内容；浮点按原 dtype 的位模式比较，不设容差。不比较 HDF5 容器封装字节。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import h5py
import numpy as np


class ParityError(RuntimeError):
    """对拍工具的输入不完整或不可比较。"""


# ── HDF5 遍历与指纹 ────────────────────────────────────────────────────────────


def _walk(handle: h5py.Group, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """按名称排序深度优先遍历，产出 (路径, 对象)；attribute 单独产出。"""
    for name in sorted(handle.attrs.keys()):
        yield f"{prefix}@{name}", handle.attrs[name]
    for name in sorted(handle.keys()):
        path = f"{prefix}/{name}" if prefix else name
        node = handle[name]
        if isinstance(node, h5py.Group):
            yield path, node
            yield from _walk(node, path)
        else:
            for attr in sorted(node.attrs.keys()):
                yield f"{path}@{attr}", node.attrs[attr]
            yield path, node


def _dataset_signature(node: h5py.Dataset) -> dict[str, Any]:
    dtype = np.dtype(node.dtype)
    signature: dict[str, Any] = {
        "kind": "dataset",
        "dtype": dtype.str,
        "shape": list(node.shape),
    }
    if h5py.check_string_dtype(dtype) is not None:
        info = h5py.check_string_dtype(dtype)
        signature["string_encoding"] = info.encoding
        signature["string_length"] = info.length
    return signature


def _raw_bytes(value: Any) -> bytes:
    """取内容的原始字节：浮点按位模式，字符串逐元素编码，不做四舍五入。"""
    if isinstance(value, np.ndarray):
        if value.dtype == object or h5py.check_string_dtype(value.dtype) is not None:
            return b"\x00".join(
                item.encode("utf-8") if isinstance(item, str) else bytes(item)
                for item in value.reshape(-1).tolist()
            )
        return np.ascontiguousarray(value).tobytes()
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (np.generic,)):
        return np.asarray(value).tobytes()
    return repr(value).encode("utf-8")



def _first_element_difference(left: Any, right: Any) -> str | None:
    """定位第一个不同的元素；可量化字段附最大绝对差，仅作差异描述，不参与判定。"""
    left_array = np.asarray(left)
    right_array = np.asarray(right)
    if left_array.shape != right_array.shape:
        return f"shape {left_array.shape} != {right_array.shape}"
    if left_array.dtype != right_array.dtype:
        return f"dtype {left_array.dtype} != {right_array.dtype}"
    if left_array.dtype.kind in "fc":
        # 位模式比较：NaN 与 -0.0 都按原样区分，不设容差
        raw_left = left_array.tobytes()
        raw_right = right_array.tobytes()
        if raw_left == raw_right:
            return None
        flat_left = left_array.reshape(-1)
        flat_right = right_array.reshape(-1)
        for index in range(flat_left.size):
            if flat_left[index].tobytes() != flat_right[index].tobytes():
                delta = float(np.max(np.abs(flat_left.astype(np.float64) - flat_right.astype(np.float64))))
                return (
                    f"首个不同元素 [{index}]：{flat_left[index]!r} != {flat_right[index]!r}"
                    f"（最大绝对差 {delta:g}，仅作描述）"
                )
        return "位模式不同但逐元素相同（不应发生）"
    if np.array_equal(left_array, right_array):
        return None
    flat_left = left_array.reshape(-1)
    flat_right = right_array.reshape(-1)
    for index in range(flat_left.size):
        if flat_left[index] != flat_right[index]:
            return f"首个不同元素 [{index}]：{flat_left[index]!r} != {flat_right[index]!r}"
    return "内容不同但逐元素相同（不应发生）"


def compare_h5(reference: str | Path, candidate: str | Path) -> list[str]:
    """逐元素比较两份 HDF5 的实际落盘内容，返回差异描述列表（空表示一致）。"""
    left_path, right_path = Path(reference), Path(candidate)
    for path in (left_path, right_path):
        if not path.is_file():
            raise ParityError(f"缺少 HDF5：{path}")
    differences: list[str] = []
    with h5py.File(left_path, "r") as left, h5py.File(right_path, "r") as right:
        left_entries = dict(_walk(left))
        right_entries = dict(_walk(right))
        left_names = set(left_entries) | {f"@{name}" for name in left.attrs}
        right_names = set(right_entries) | {f"@{name}" for name in right.attrs}
        for missing in sorted(left_names - right_names):
            differences.append(f"{missing}: 候选缺少该对象")
        for extra in sorted(right_names - left_names):
            differences.append(f"{extra}: 候选多出该对象")
        for name in sorted(left_names & right_names):
            if name.startswith("@"):
                left_value = left.attrs[name[1:]]
                right_value = right.attrs[name[1:]]
                detail = _first_element_difference(left_value, right_value)
                if detail:
                    differences.append(f"{name}: {detail}")
                continue
            left_node = left_entries[name]
            right_node = right_entries[name]
            if isinstance(left_node, h5py.Group) != isinstance(right_node, h5py.Group):
                differences.append(f"{name}: 一侧是 group、一侧不是")
                continue
            if isinstance(left_node, h5py.Group):
                continue
            if isinstance(left_node, h5py.Dataset):
                left_signature = _dataset_signature(left_node)
                right_signature = _dataset_signature(right_node)
                if left_signature != right_signature:
                    differences.append(f"{name}: 签名不同 {left_signature} != {right_signature}")
                    continue
                detail = _first_element_difference(left_node[()], right_node[()])
                if detail:
                    differences.append(f"{name}: {detail}")
                continue
            detail = _first_element_difference(left_node, right_node)
            if detail:
                differences.append(f"{name}: {detail}")
    return differences


# ── 运行目录级比较 ────────────────────────────────────────────────────────────


