#!/usr/bin/env python3
"""轻量测试：eval_video_mover 对官方路线（xhard0 旧入口）记录的支持（不读 HDF5、不占 GPU）。

官方路线记录没有 ``episode``／``tier``，只有 ``source_episode``；``--tier`` 给档位。用临时目录伪造暂存视频与记录，
以子进程跑一轮 ``--once``，核对目标路径、sha256、NFS 副本删除与 ``moved.jsonl`` 字段。

    uv run --no-sync python -m pytest tests/lightweight/test_eval_video_mover_official.py -q
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
MOVER = REPO_ROOT / "scripts" / "injection-dev" / "eval_video_mover.py"


def _run(tmp: Path, records: list[dict], *extra: str) -> subprocess.CompletedProcess:
    log = tmp / "episodes.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in records))
    return subprocess.run(
        [sys.executable, str(MOVER), "--policy", "mmevla", "--records-glob", str(log), "--stage", str(tmp / "stage"),
         "--dest", str(tmp / "dest"), "--stable-sec", "0", "--interval", "0.1", "--once", *extra],
        capture_output=True, text=True, timeout=60)


def test_official_records_use_source_episode_and_tier(tmp_path):
    stage = tmp_path / "stage" / "0"
    stage.mkdir(parents=True)
    video = stage / "StopCube_xhard0_3_520300.mp4"
    video.write_bytes(b"fake-mp4-bytes")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    rec = {"task": "StopCube", "source_episode": 3, "seed": 520300, "status": "success", "attempt": 1,
           "video": str(video)}
    proc = _run(tmp_path, [rec], "--tier", "xhard0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = tmp_path / "dest" / "xhard0" / "StopCube" / "StopCube_xhard0_3_520300.mp4"
    assert out.exists() and not video.exists()
    row = json.loads((tmp_path / "dest" / "moved.jsonl").read_text().splitlines()[0])
    assert (row["episode"], row["tier"], row["sha256"]) == (3, "xhard0", digest)


def test_official_last_terminal_row_wins(tmp_path):
    stage = tmp_path / "stage" / "0"
    stage.mkdir(parents=True)
    video = stage / "BinFill_xhard0_7_540700.mp4"
    video.write_bytes(b"x")
    base = {"task": "BinFill", "source_episode": 7, "seed": 540700, "video": str(video)}
    proc = _run(tmp_path, [{**base, "status": "error"}, {**base, "status": "fail", "attempt": 2}], "--tier", "xhard0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    row = json.loads((tmp_path / "dest" / "moved.jsonl").read_text().splitlines()[0])
    assert row["status"] == "fail"
