"""从HDF5完整操作轨迹回放，保留演示和显式判定边界。"""

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

from .workers import run_episode_process
from .staging import _run_staged
from .generate import _render_gpu_from_fingerprint

def replay_episode(path: str | Path, output_file: str | Path, *, timeout_seconds: float = 240) -> dict[str, Any]:
    """只依赖当前 HDF5 的规格和动作，完全不读取原版 metadata。"""
    expected = read_episode(path)
    from ..runtime import configure_runtime
    configure_runtime()
    if expected.runtime_fingerprint is None:
        raise RecordError("输入记录没有运行指纹，禁止进行认证回放")
    render_gpu = _render_gpu_from_fingerprint(expected.runtime_fingerprint)
    assert_identical(expected.runtime_fingerprint, runtime_fingerprint(render_gpu=render_gpu), path="runtime_fingerprint")
    spec = EpisodeSpec.from_dict(expected.episode_spec)
    target = output_path(output_file)
    actual, resumed = _run_staged(
        spec, target,
        lambda candidate, staging: run_episode_process(candidate, staging, replay_source=path, timeout_seconds=timeout_seconds, render_gpu=render_gpu),
        fingerprint=expected.runtime_fingerprint, content_hash=expected.content_hash,
    )
    assert_records_identical(expected, actual)
    return {"passed": True, "seed": spec.seed, "spec_hash": spec.spec_hash,
            "frame_count": len(actual.frames), "path": str(target), "resumed": resumed, "render_gpu": render_gpu}
