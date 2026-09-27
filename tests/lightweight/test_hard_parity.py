"""`scripts/parity/hard_parity.py` 的参数解析、dry-run 命令与 H5 校验反例。"""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from scripts.parity import hard_parity as H

S3_DIR = H.ROOT / "artifacts/newtask-v6/v6-s3-20260926-01"


def _rows():
    rows = [{"task": "BinFill", "episode": 0, "seed": 7, "difficulty": "easy", "recovery_mode": None}]
    rows += [{"task": "PickXtimes", "episode": i, "seed": 100 + i, "difficulty": "hard", "recovery_mode": None}
             for i in range(143)]
    return rows


def _args(tmp_path: Path, *extra: str):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"source_ref": "x", "rows": _rows()}))
    return ["run", "--env-package", "robomme_hard", "--manifest", str(manifest), "--base", str(tmp_path / "base"),
            "--official-root", str(tmp_path / "official"), "--output", str(tmp_path / "out"), *extra]


def test_parser_requires_env_package_choice(tmp_path):
    parser = H.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--manifest", "m", "--base", "b", "--official-root", "o", "--output", "x"])
    with pytest.raises(SystemExit):
        parser.parse_args(_args(tmp_path)[:2] + ["robomme_v2"] + _args(tmp_path)[3:])
    args = parser.parse_args(_args(tmp_path))
    assert args.env_package == "robomme_hard" and args.workers == 1 and args.gpus == "0" and not args.dry_run


def test_dry_run_prints_commands_and_writes_nothing(tmp_path, capsys):
    assert H.main(_args(tmp_path, "--dry-run")) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "# env CUDA_VISIBLE_DEVICES=0 ROBOMME_ENV_PACKAGE=robomme_hard"
    assert lines[1].endswith(f"--output {tmp_path / 'out' / 'smoke'}")
    assert " compare --run base=" in lines[3]
    assert not (tmp_path / "out").exists()


@pytest.mark.skipif(not (S3_DIR / "launch.json").is_file(), reason="S3 产物不在本机")
def test_dry_run_matches_s3_run_commands(capsys):
    """指向 S3 原目录时，两条 run 命令与 S3 运行器实际拼出的 argv 逐字相同。"""
    manifest = H.ROOT / "scripts/configs/newtask-v3/subset_manifest.json"
    base = H.ROOT / "artifacts/newtask-v6/v1/base"
    official = H.ROOT / "artifacts/train-parity/local-smoke-01/official-src"
    H.main(["run", "--env-package", "robomme", "--manifest", str(manifest), "--base", str(base),
            "--official-root", str(official), "--output", str(S3_DIR), "--dry-run"])
    lines = capsys.readouterr().out.splitlines()
    for part, line in zip(("smoke", "remaining"), lines[1:3]):
        expected = ["uv", "run", "--no-sync", "python", str(H.ENTRY), "run",
                    "--manifest", str(S3_DIR / f"{part}_manifest.json"), "--paths", "B",
                    "--workers", "1", "--gpus", "0", "--official-root", str(official),
                    "--output", str(S3_DIR / part)]
        assert line == " ".join(expected)


def test_split_rows_rejects_wrong_count():
    with pytest.raises(H.ParityError):
        H.split_rows(_rows()[:10])
    first, rest = H.split_rows(_rows())
    assert len(first) == 1 and len(rest) == 143


def _write_h5(root: Path, row: dict, *, difficulty=None, completed=True, empty=False):
    folder = root / "B" / H.identity(row) / "hdf5_files"
    folder.mkdir(parents=True)
    path = folder / f"{row['task']}_ep{row['episode']}_seed{row['seed']}.h5"
    if empty:
        path.write_bytes(b"")
        return
    with h5py.File(path, "w") as handle:
        ep = handle.create_group(f"episode_{row['episode']}")
        ep["setup/seed"] = row["seed"]
        ep["setup/difficulty"] = (difficulty or row["difficulty"]).encode()
        ep["timestep_0/info/is_completed"] = np.bool_(False)
        ep["timestep_1/info/is_completed"] = np.bool_(completed)


ROW = {"task": "BinFill", "episode": 0, "seed": 7, "difficulty": "easy"}


def test_validate_h5_accepts_good(tmp_path):
    _write_h5(tmp_path, ROW)
    assert H.validate_h5(tmp_path, [ROW], "t")["timestep_count"] == 2


@pytest.mark.parametrize("case", ["missing", "difficulty", "incomplete", "empty"])
def test_validate_h5_rejects(tmp_path, case):
    if case == "missing":
        (tmp_path / "B").mkdir()
    else:
        _write_h5(tmp_path, ROW, difficulty="hard" if case == "difficulty" else None,
                  completed=case != "incomplete", empty=case == "empty")
    with pytest.raises(H.ParityError):
        H.validate_h5(tmp_path, [ROW], "t")
