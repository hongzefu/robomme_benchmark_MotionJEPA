#!/usr/bin/env python3
"""newtask-v2 三路对拍的测试侧工具：证据编码、HDF5 全字段比较与离线比较入口。

本模块只服务测试与对拍留档，产品生成路径（``scripts/generate_dataset_newseed.py``、
``src/robomme``）不导入它；它也不使用 ``tests/_shared/dataset_generation.py``
——后者会自动换 seed、另写求解循环，不能用于逐位对拍。

三路口径（方案第四步 4.0）：

* A：固定原版，来自 ``94449db`` 的 detached worktree，入口为原路径脚本
* B：新版不传 ``--sampling-config``
* C：新版显式传入冻结的原值配置

HDF5 判据（4.3）：遍历实际落盘树，逐 group / dataset / attribute 比较全集、dtype、
shape、字符串编码与逐元素内容；浮点按原 dtype 的位模式比较，不设容差。
不比较 HDF5 容器封装字节（group 默认 ``track_times=True``），也不比较带时间戳的视频文件。

离线比较入口（须在仓库根目录执行，``tests`` 是命名空间包）：

    uv run --no-sync python -m tests._shared.native_sampling_parity compare \\
        --reference <证据包或运行目录> --candidate <同上> --output <新目录>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator, Sequence

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


def h5_fingerprint(path: str | Path) -> dict[str, Any]:
    """整份 HDF5 的结构与内容指纹：路径 → 签名（含内容 SHA-256）。"""
    source = Path(path)
    if not source.is_file():
        raise ParityError(f"缺少 HDF5：{source}")
    entries: dict[str, Any] = {}
    with h5py.File(source, "r") as handle:
        for name in sorted(handle.attrs.keys()):
            entries[f"@{name}"] = {
                "kind": "attribute",
                "sha256": hashlib.sha256(_raw_bytes(handle.attrs[name])).hexdigest(),
            }
        for node_path, node in _walk(handle):
            if isinstance(node, h5py.Group):
                entries[node_path] = {"kind": "group"}
            elif isinstance(node, h5py.Dataset):
                signature = _dataset_signature(node)
                signature["sha256"] = hashlib.sha256(_raw_bytes(node[()])).hexdigest()
                entries[node_path] = signature
            else:
                entries[node_path] = {
                    "kind": "attribute",
                    "sha256": hashlib.sha256(_raw_bytes(node)).hexdigest(),
                }
    return {"file": source.name, "entries": entries}


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


def episode_files(run_dir: str | Path) -> dict[str, Path]:
    """列出一个生成输出目录里的逐 episode HDF5，键为文件名。"""
    root = Path(run_dir)
    hdf5_dir = root / "hdf5_files"
    if not hdf5_dir.is_dir():
        raise ParityError(f"缺少 hdf5_files 目录：{hdf5_dir}")
    return {path.name: path for path in sorted(hdf5_dir.glob("*.h5"))}


def compare_runs(reference: str | Path, candidate: str | Path) -> dict[str, Any]:
    """比较两个生成输出目录里的全部逐 episode HDF5。"""
    left = episode_files(reference)
    right = episode_files(candidate)
    result: dict[str, Any] = {
        "reference": str(reference),
        "candidate": str(candidate),
        "reference_files": sorted(left),
        "candidate_files": sorted(right),
        "missing_in_candidate": sorted(set(left) - set(right)),
        "extra_in_candidate": sorted(set(right) - set(left)),
        "files": {},
    }
    for name in sorted(set(left) & set(right)):
        differences = compare_h5(left[name], right[name])
        result["files"][name] = {
            "difference_count": len(differences),
            "differences": differences[:50],
        }
    result["passed"] = (
        not result["missing_in_candidate"]
        and not result["extra_in_candidate"]
        and all(item["difference_count"] == 0 for item in result["files"].values())
        and bool(result["files"])
    )
    return result


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="newtask-v2 三路对拍的离线比较")
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare", help="比较两个生成输出目录的 HDF5 全字段内容")
    compare.add_argument("--reference", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--output", default=None, help="把结果写到该目录的 result.json")
    args = parser.parse_args(argv)

    result = compare_runs(args.reference, args.candidate)
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
