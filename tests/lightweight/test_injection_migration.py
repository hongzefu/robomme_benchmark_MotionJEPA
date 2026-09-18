"""小夹具演练迁移中断与恢复，不故意破坏真实运行。"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from scripts.injection._migrate_run10 import move_entries, translate
from scripts.injection.candidates.io import CandidateError, load_candidates
from scripts.injection.rollout.state import ROOT, StateError, file_sha


def fixture():
    parent = ROOT / "artifacts/test-tmp"
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="migration-", dir=parent))
    entries = []
    for index in range(3):
        path = root / "old" / f"{index}.bin"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(bytes([index]) * 4096)
        entries.append({"source": str(path.relative_to(root)), "target": f"new/{index}.bin",
                        "bytes": path.stat().st_size, "sha256": file_sha(path)})
    return root, entries


def test_resume_after_move_before_full_completion():
    root, entries = fixture()
    journal = root / "journal.jsonl"
    with pytest.raises(InterruptedError):
        move_entries(root, entries, journal, stop_after=1)
    assert not (root / entries[0]["source"]).exists()
    assert (root / entries[0]["target"]).exists()
    assert move_entries(root, entries, journal) == 2
    assert move_entries(root, entries, journal) == 0
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    moves = [r["source"] for r in rows if r["action"] == "moved"]
    assert len(moves) == len(set(moves)) == 3
    for entry in entries:
        assert file_sha(root / entry["target"]) == entry["sha256"]
    print("MIGRATION_RECOVERY=PASS duplicate_moves=0 overwritten=0")


def test_both_sides_exist_never_overwrites():
    root, entries = fixture()
    target = root / entries[0]["target"]
    target.parent.mkdir()
    target.write_bytes("用户内容".encode("utf-8"))
    with pytest.raises(StateError, match="冲突"):
        move_entries(root, entries, root / "journal.jsonl")
    assert target.read_bytes() == "用户内容".encode("utf-8")
    assert (root / entries[0]["source"]).exists()


def test_changed_target_refuses_resume():
    root, entries = fixture()
    with pytest.raises(InterruptedError):
        move_entries(root, entries, root / "journal.jsonl", stop_after=1)
    (root / entries[0]["target"]).write_bytes(b"x" * 4096)
    with pytest.raises(StateError, match="散列"):
        move_entries(root, entries, root / "journal.jsonl")


def test_translate_only_active_fields():
    old, new = "/旧/run/file.h5", "/新/run/file.h5"
    row = {"h5_path": old, "video": {"path": old, "no_object_paths": [old]}, "error": old,
           "discarded": [{"path": old}], "role": "primary", "seed": 16000}
    result = translate(row, {old: new}, {})
    assert result["h5_path"] == result["video"]["path"] == result["video"]["no_object_paths"][0] == new
    assert result["error"] == result["discarded"][0]["path"] == old
    assert result["role"] == "primary" and result["seed"] == 16000


def test_candidate_entry_blocked_until_migration_complete():
    root, _ = fixture()
    path = root / "candidates/candidates.jsonl"
    path.parent.mkdir()
    shutil.copyfile(ROOT / "artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl", path)
    state = root / "rollout/logs/migration/state.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"state":"in_progress"}')
    with pytest.raises(CandidateError, match="迁移"):
        load_candidates(path, repo_root=ROOT)
    assert len(load_candidates(path, repo_root=ROOT, allow_migrating=True)[1]) == 3400
    state.write_text('{"state":"complete"}')
    assert len(load_candidates(path, repo_root=ROOT)[1]) == 3400
