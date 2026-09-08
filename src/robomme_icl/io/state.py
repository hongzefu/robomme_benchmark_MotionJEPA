"""恢复身份、完整产物核对与原子发布，不创建环境。"""

from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Any, Sequence

import h5py

from ..errors import CandidateRejected
from ..io.paths import output_path
from ..io.hdf5 import (
    EpisodeRecord,
    RecordError,
    ReproducibilityError,
    assert_identical,
    assert_records_identical,
    read_episode,
)
from ..validation.reproducibility import check_terminal


def _exclusive_json(path: Path, payload: Any) -> None:
    target = output_path(path, create_parent=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise RecordError(f"恢复记录损坏，已保留原文件：{path}：{exc}") from exc


def _bind_context(path: Path, expected: dict[str, Any]) -> None:
    """首次运行固定恢复身份；代码、配置或配额变化必须另用新目录。"""
    path = output_path(path, create_parent=True)
    if path.exists():
        assert_identical(expected, _read_json(path), path=f"恢复上下文/{path.name}")
    else:
        if any(path.parent.iterdir()):
            raise RecordError(
                f"已有产物缺少恢复上下文，无法证明配置和运行指纹相同：{path.parent}"
            )
        _exclusive_json(path, expected)


def _complete_record(path: Path) -> EpisodeRecord | None:
    """只跳过明确未完成的 staging；有完成标记但摘要坏了必须停止。"""
    path = output_path(path)
    try:
        with h5py.File(path, "r") as handle:
            complete = bool(handle.attrs.get("complete", False))
    except OSError:
        # 写到一半的 HDF5 可能还没有有效文件头，保留它并换明确的新 attempt 文件。
        return None
    return read_episode(path) if complete else None


def _validate_record(
    record: EpisodeRecord,
    spec: Any,
    *,
    fingerprint: dict[str, Any] | None = None,
    content_hash: str | None = None,
    path: str | Path = "record",
) -> None:
    if record.spec_hash != spec.spec_hash:
        raise RecordError(f"已有记录规格不符，拒绝覆盖：{path}")
    assert_identical(spec.to_dict(), record.episode_spec, path="episode_spec")
    if fingerprint is not None:
        assert_identical(
            fingerprint, record.runtime_fingerprint, path="runtime_fingerprint"
        )
    try:
        check_terminal(record.frames)
    except CandidateRejected as exc:
        raise RecordError(f"完整缓存记录的终态非法，已保留原文件：{path}") from exc
    if content_hash is not None and record.content_hash != content_hash:
        raise ReproducibilityError(f"正式生成与认证内容不同，记录已保留：{path}")


def _prior_complete(
    paths: Sequence[Path],
    spec: Any,
    *,
    fingerprint: dict[str, Any] | None,
    content_hash: str | None = None,
) -> tuple[Path, EpisodeRecord] | None:
    """未知退出状态下，完整产物可复用；多个完整产物也必须相互一致。"""
    result = None
    for path in sorted(paths):
        record = _complete_record(path)
        if record is None:
            continue
        _validate_record(
            record, spec, fingerprint=fingerprint, content_hash=content_hash, path=path
        )
        if result is None:
            result = (path, record)
        else:
            assert_records_identical(result[1], record)
    return result


def _atomic_publish(staging: Path, target: Path) -> None:
    """同仓库内已关闭的完整文件原子发布，绝不替换已存在的最终路径。"""
    staging, target = output_path(staging), output_path(target, create_parent=True)
    with staging.open("rb") as stream:
        os.fsync(stream.fileno())
    # 同一目标旁的 staging 与目标处于同一文件系统；硬链接创建是原子的且不覆盖。
    # staging 保留作为执行证据，两个名字都实际存储在本仓库内。
    os.link(staging, target)
    descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
