# -*- coding: utf-8 -*-
"""轻量测试：append_train_metadata 的合并逻辑（纯文件操作，秒级完成）。

覆盖三种情形：正常追加、episode 重叠拒绝、合并后不连续拒绝；
以及 CLI 两阶段语义——任一 task 校验失败时不落任何文件。

运行（使用 uv）：
    uv run python tests/lightweight/test_append_train_metadata.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]

REPO_ROOT = find_repo_root(__file__)
sys.path.insert(0, str(REPO_ROOT / "scripts" / "data-generation-newSeed" / "utils"))

from append_train_metadata import (  # noqa: E402
    AppendMetadataError,
    main,
    merge_records,
)


def _payload(task: str, episodes: list[int]) -> dict:
    return {
        "env_id": task,
        "record_count": len(episodes),
        "records": [
            {"task": task, "episode": episode, "seed": 8000 + episode * 100, "difficulty": "easy"}
            for episode in episodes
        ],
    }


def test_merge_appends_and_recounts() -> None:
    merged = merge_records("ButtonUnmask", _payload("ButtonUnmask", [0, 1]), _payload("ButtonUnmask", [2, 3]))
    assert merged["record_count"] == 4
    assert [item["episode"] for item in merged["records"]] == [0, 1, 2, 3]
    assert merged["records"][2]["seed"] == 8200


def test_merge_rejects_overlap() -> None:
    with pytest.raises(AppendMetadataError, match="重叠"):
        merge_records("ButtonUnmask", _payload("ButtonUnmask", [0, 1]), _payload("ButtonUnmask", [1, 2]))


def test_merge_rejects_gap() -> None:
    with pytest.raises(AppendMetadataError, match="不连续"):
        merge_records("ButtonUnmask", _payload("ButtonUnmask", [0, 1]), _payload("ButtonUnmask", [3, 4]))


def test_merge_rejects_env_id_mismatch() -> None:
    with pytest.raises(AppendMetadataError, match="env_id"):
        merge_records("ButtonUnmask", _payload("VideoUnmask", [0]), _payload("ButtonUnmask", [1]))


def _write(directory: Path, task: str, episodes: list[int]) -> Path:
    path = directory / f"record_dataset_{task}_metadata.json"
    path.write_text(json.dumps(_payload(task, episodes), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_cli_appends_all_tasks(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "train"
    input_dir = tmp_path / "generated"
    metadata_dir.mkdir()
    input_dir.mkdir()
    for task in ("ButtonUnmask", "VideoUnmask"):
        _write(metadata_dir, task, [0, 1])
        _write(input_dir, task, [2, 3])

    code = main(
        [
            "--input-dir", str(input_dir),
            "--metadata-dir", str(metadata_dir),
            "--env", "ButtonUnmask,VideoUnmask",
        ]
    )
    assert code == 0
    for task in ("ButtonUnmask", "VideoUnmask"):
        payload = json.loads((metadata_dir / f"record_dataset_{task}_metadata.json").read_text(encoding="utf-8"))
        assert payload["record_count"] == 4
        assert [item["episode"] for item in payload["records"]] == [0, 1, 2, 3]


def test_cli_two_phase_writes_nothing_on_any_failure(tmp_path: Path) -> None:
    """第二个 task 校验失败时，第一个 task 也必须原样未动。"""
    metadata_dir = tmp_path / "train"
    input_dir = tmp_path / "generated"
    metadata_dir.mkdir()
    input_dir.mkdir()
    _write(metadata_dir, "ButtonUnmask", [0, 1])
    _write(input_dir, "ButtonUnmask", [2, 3])          # 本身合法
    _write(metadata_dir, "VideoUnmask", [0, 1])
    _write(input_dir, "VideoUnmask", [1, 2])           # 与既有 ep1 重叠 → 整体拒绝

    code = main(
        [
            "--input-dir", str(input_dir),
            "--metadata-dir", str(metadata_dir),
            "--env", "ButtonUnmask,VideoUnmask",
        ]
    )
    assert code == 1
    payload = json.loads((metadata_dir / "record_dataset_ButtonUnmask_metadata.json").read_text(encoding="utf-8"))
    assert payload["record_count"] == 2, "整体拒绝时不允许写入任何文件"


def test_cli_dry_run_writes_nothing(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "train"
    input_dir = tmp_path / "generated"
    metadata_dir.mkdir()
    input_dir.mkdir()
    _write(metadata_dir, "ButtonUnmask", [0, 1])
    _write(input_dir, "ButtonUnmask", [2, 3])

    code = main(
        [
            "--input-dir", str(input_dir),
            "--metadata-dir", str(metadata_dir),
            "--env", "ButtonUnmask",
            "--dry-run",
        ]
    )
    assert code == 0
    payload = json.loads((metadata_dir / "record_dataset_ButtonUnmask_metadata.json").read_text(encoding="utf-8"))
    assert payload["record_count"] == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
