"""完整保存帧数据，并以类型、形状和字节进行严格认证。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

import h5py
import numpy as np

from ..errors import ReproducibilityError as SharedReproducibilityError
from .paths import output_path


SCHEMA_VERSION = 2


class RecordError(RuntimeError):
    """记录不完整、版本不符或内容摘要错误。"""


class ReproducibilityError(RecordError, SharedReproducibilityError):
    """同一规格产生了不同的帧，不能换候选掩盖差异。"""


@dataclass(frozen=True)
class EpisodeRecord:
    """独立回放需要的规格快照和有序帧。"""

    episode_spec: dict[str, Any]
    spec_hash: str
    frames: list[dict[str, Any]]
    content_hash: str
    runtime_fingerprint: dict[str, Any] | None = None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _tagged_hash(value: Any, digest: Any) -> None:
    """类型标签与长度前缀避免不同树结构拥有相同字节拼接。"""
    def add(data: bytes) -> None:
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)

    if value is None:
        add(b"none")
    elif isinstance(value, np.ndarray):
        if value.dtype.hasobject or value.dtype.kind not in "biufc":
            raise TypeError(f"不支持记录的数组类型：{value.dtype}")
        add(b"array")
        add(value.dtype.str.encode())
        add(_json(list(value.shape)).encode())
        add(np.ascontiguousarray(value).tobytes())
    elif isinstance(value, np.generic):
        add(b"numpy_scalar")
        _tagged_hash(np.asarray(value), digest)
    elif isinstance(value, Mapping):
        add(b"mapping")
        if any(not isinstance(key, str) for key in value):
            raise TypeError("记录字典只接受字符串键")
        add(str(len(value)).encode())
        for key in sorted(value):
            add(key.encode())
            _tagged_hash(value[key], digest)
    elif isinstance(value, (list, tuple)):
        add(b"tuple" if isinstance(value, tuple) else b"list")
        add(str(len(value)).encode())
        for child in value:
            _tagged_hash(child, digest)
    elif isinstance(value, bytes):
        add(b"bytes")
        add(value)
    elif isinstance(value, (str, bool, int, float)):
        add(type(value).__name__.encode())
        add(_json(value).encode())
    else:
        raise TypeError(f"不支持记录的值类型：{type(value).__name__}")


def tree_hash(value: Any) -> str:
    digest = hashlib.sha256()
    _tagged_hash(value, digest)
    return digest.hexdigest()


def assert_identical(expected: Any, actual: Any, *, path: str = "frames") -> None:
    """遇到第一处差异即给出字段路径；浮点同样不使用容差。"""
    if isinstance(expected, np.ndarray):
        if not isinstance(actual, np.ndarray):
            raise ReproducibilityError(f"{path}: 数组类型不同")
        if expected.dtype != actual.dtype or expected.shape != actual.shape:
            raise ReproducibilityError(
                f"{path}: dtype/shape 不同：{expected.dtype}{expected.shape} != {actual.dtype}{actual.shape}"
            )
        if np.ascontiguousarray(expected).tobytes() != np.ascontiguousarray(actual).tobytes():
            raise ReproducibilityError(f"{path}: 数组字节不同")
        return
    if isinstance(expected, np.generic):
        if type(expected) is not type(actual):
            raise ReproducibilityError(f"{path}: NumPy 标量类型不同")
        assert_identical(np.asarray(expected), np.asarray(actual), path=path)
        return
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping) or set(expected) != set(actual):
            raise ReproducibilityError(f"{path}: 字典字段不同")
        for key in sorted(expected):
            assert_identical(expected[key], actual[key], path=f"{path}/{key}")
        return
    if isinstance(expected, (list, tuple)):
        if type(expected) is not type(actual) or len(expected) != len(actual):
            raise ReproducibilityError(f"{path}: 序列类型或长度不同")
        for index, (left, right) in enumerate(zip(expected, actual)):
            assert_identical(left, right, path=f"{path}/{index}")
        return
    if type(expected) is not type(actual) or tree_hash(expected) != tree_hash(actual):
        raise ReproducibilityError(f"{path}: 标量类型或值不同")


def _write_node(parent: h5py.Group, name: str, value: Any) -> None:
    if isinstance(value, np.ndarray):
        # 无损压缩不会改变原始 RGB 和数值字节，减少两次认证的存储开销。
        options = {"compression": "lzf", "shuffle": True} if value.ndim > 0 and value.nbytes >= 1024 else {}
        node = parent.create_dataset(name, data=value, **options)
        node.attrs["kind"] = "array"
    elif isinstance(value, np.generic):
        node = parent.create_dataset(name, data=value)
        node.attrs["kind"] = "numpy_scalar"
    elif isinstance(value, Mapping):
        node = parent.create_group(name)
        node.attrs["kind"] = "mapping"
        node.attrs["keys"] = _json(sorted(value))
        for key in sorted(value):
            _write_node(node, quote(key, safe="") or "%EMPTY", value[key])
    elif isinstance(value, (list, tuple)):
        node = parent.create_group(name)
        node.attrs["kind"] = "tuple" if isinstance(value, tuple) else "list"
        node.attrs["length"] = len(value)
        for index, child in enumerate(value):
            _write_node(node, f"{index:08d}", child)
    elif value is None:
        node = parent.create_group(name)
        node.attrs["kind"] = "none"
    elif isinstance(value, bytes):
        node = parent.create_dataset(name, data=np.frombuffer(value, dtype=np.uint8))
        node.attrs["kind"] = "bytes"
    else:
        node = parent.create_dataset(name, data=_json(value), dtype=h5py.string_dtype("utf-8"))
        node.attrs["kind"] = "json_scalar"


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _read_node(node: h5py.Group | h5py.Dataset) -> Any:
    kind = _text(node.attrs["kind"])
    if kind == "array":
        return np.asarray(node[()], dtype=node.dtype)
    if kind == "numpy_scalar":
        return node[()]
    if kind == "mapping":
        return {key: _read_node(node[quote(key, safe="") or "%EMPTY"]) for key in json.loads(node.attrs["keys"])}
    if kind in {"list", "tuple"}:
        values = [_read_node(node[f"{index:08d}"]) for index in range(int(node.attrs["length"]))]
        return tuple(values) if kind == "tuple" else values
    if kind == "none":
        return None
    if kind == "bytes":
        return node[()].tobytes()
    if kind == "json_scalar":
        return json.loads(_text(node[()]))
    raise RecordError(f"未知 HDF5 节点类型：{kind}")


def write_episode(
    path: str | Path, spec: Any, frames: Sequence[dict[str, Any]], *,
    runtime_fingerprint: dict[str, Any] | None = None, source_commit: str | None = None,
) -> Path:
    """独占创建文件，写入失败保留不完整证据，绝不覆盖已有产物。"""
    target = output_path(path, create_parent=True)
    payload = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec)
    spec_hash = spec.spec_hash if hasattr(spec, "spec_hash") else payload["spec_hash"]
    frame_list = list(frames)
    if not frame_list:
        raise RecordError("不能记录空 episode")
    content_hash = tree_hash({"episode_spec": payload, "frames": frame_list, "runtime_fingerprint": runtime_fingerprint})
    with h5py.File(target, "x") as handle:
        handle.attrs["schema_version"] = SCHEMA_VERSION
        handle.attrs["complete"] = False
        setup = handle.create_group("setup")
        setup.create_dataset("episode_spec", data=_json(payload), dtype=h5py.string_dtype("utf-8"))
        setup.create_dataset("spec_hash", data=spec_hash, dtype=h5py.string_dtype("utf-8"))
        setup.create_dataset("env_id", data=spec.env_id if hasattr(spec, "env_id") else payload["env_id"])
        setup.create_dataset("seed", data=int(spec.seed if hasattr(spec, "seed") else payload["seed"]))
        setup.create_dataset("runtime_fingerprint", data=_json(runtime_fingerprint), dtype=h5py.string_dtype("utf-8"))
        setup.create_dataset("source_commit", data=source_commit or "", dtype=h5py.string_dtype("utf-8"))
        _write_node(handle, "steps", frame_list)
        handle.attrs["content_hash"] = content_hash
        handle.attrs["complete"] = True
        handle.flush()
    return target


def read_episode(path: str | Path) -> EpisodeRecord:
    """每次读取均重新计算帧摘要，损坏文件不能当作断点完成项。"""
    target = output_path(path)
    try:
        with h5py.File(target, "r") as handle:
            if int(handle.attrs.get("schema_version", -1)) != SCHEMA_VERSION:
                raise RecordError(f"不支持的 HDF5 schema：{target}")
            if not bool(handle.attrs.get("complete", False)):
                raise RecordError(f"不完整的 HDF5，已保留原文件：{target}")
            payload = json.loads(_text(handle["setup/episode_spec"][()]))
            spec_hash = _text(handle["setup/spec_hash"][()])
            frames = _read_node(handle["steps"])
            content_hash = _text(handle.attrs["content_hash"])
            fingerprint = json.loads(_text(handle["setup/runtime_fingerprint"][()]))
            if str(payload.get("spec_hash", spec_hash)) != spec_hash:
                raise RecordError(f"规格摘要字段不一致：{target}")
            if int(handle["setup/seed"][()]) != int(payload["seed"]) or _text(handle["setup/env_id"][()]) != payload["env_id"]:
                raise RecordError(f"setup seed/env_id 与规格快照不一致：{target}")
            if tree_hash({"episode_spec": payload, "frames": frames, "runtime_fingerprint": fingerprint}) != content_hash:
                raise RecordError(f"HDF5 内容摘要不匹配：{target}")
            if not frames:
                raise RecordError(f"HDF5 没有帧：{target}")
            return EpisodeRecord(payload, spec_hash, frames, content_hash, fingerprint)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise RecordError(f"无法读取 HDF5，已保留原文件：{target}：{exc}") from exc


def assert_records_identical(left: EpisodeRecord, right: EpisodeRecord) -> None:
    if left.spec_hash != right.spec_hash:
        raise ReproducibilityError("两次运行的 spec_hash 不同")
    assert_identical(left.episode_spec, right.episode_spec, path="episode_spec")
    assert_identical(left.runtime_fingerprint, right.runtime_fingerprint, path="runtime_fingerprint")
    assert_identical(left.frames, right.frames)
