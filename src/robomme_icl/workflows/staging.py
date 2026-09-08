"""业务操作的staging生命周期，与物理执行解耦。"""

from __future__ import annotations

from pathlib import Path
import json
import os
import time
from typing import Any, Callable, Mapping, Sequence

import h5py

from ..errors import CandidateRejected, InfrastructureError
from ..specs import EpisodeSpec
from ..io.paths import output_path
from ..io.fingerprint import runtime_fingerprint, source_commit
from ..io.hdf5 import (
    EpisodeRecord, RecordError, ReproducibilityError, assert_identical,
    assert_records_identical, read_episode, write_episode,
)
from ..validation.reproducibility import check_terminal

from ..io.state import _bind_context, _validate_record, _prior_complete, _atomic_publish
from .workers import retry_same_spec

def _run_staged(
    spec: Any, target: Path, operation: Callable[[Any, Path], Path], *,
    fingerprint: dict[str, Any] | None, content_hash: str | None,
) -> tuple[EpisodeRecord, bool]:
    """基础设施失败留下独立 staging，再以完全相同 spec/seed 重试。"""
    target = output_path(target, create_parent=True)
    if target.exists():
        record = read_episode(target)
        _validate_record(record, spec, fingerprint=fingerprint, content_hash=content_hash, path=target)
        return record, True
    directory = target.parent / ".staging" / target.name
    _bind_context(directory / "context.json", {
        "schema_version": 1, "episode_spec": spec.to_dict(),
        "runtime_fingerprint": fingerprint, "expected_content_hash": content_hash,
    })
    # 重试计数不只取已存在文件：失败尚未来得及创建文件时也使用新的明确 attempt 名称。
    indices = [int(path.stem.split("_")[-1]) for path in directory.glob("attempt_*.h5")]
    next_index = [max(indices, default=-1) + 1]
    reused = [False]

    def attempt(candidate: Any) -> EpisodeRecord:
        if target.exists():
            record = read_episode(target)
            _validate_record(record, candidate, fingerprint=fingerprint, content_hash=content_hash, path=target)
            reused[0] = True
            return record
        previous = _prior_complete(list(directory.glob("attempt_*.h5")), candidate,
                                   fingerprint=fingerprint, content_hash=content_hash)
        if previous is not None:
            staging, record = previous
            reused[0] = True
        else:
            staging = directory / f"attempt_{next_index[0]:04d}.h5"
            next_index[0] += 1
            result = operation(candidate, staging)
            if Path(result).resolve() != staging.resolve():
                raise RecordError("执行器返回了非预期 staging 路径")
            record = read_episode(staging)
            _validate_record(record, candidate, fingerprint=fingerprint, content_hash=content_hash, path=staging)
        _atomic_publish(staging, target)
        return record

    return retry_same_spec(spec, attempt), reused[0]
