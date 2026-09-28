"""``scripts/parity/hard_parity.py``（三侧对拍入口）的纯 CPU 测试：合成 h5，不起仿真。

覆盖：参数解析、每侧自检、逐对指标（setup／结构／四项容差／首个分叉步）、容差标定的下界与上界、
包归属判定、端到端 compare 的判定层与容差层（含超阈值即 FAIL、同失败不算相等）。
"""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from scripts.parity import hard_parity as H


def _h5(path: Path, seed: int, frames: int = 4, action_shift: float = 0.0, goal: str = "pick up the cube") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        ep = f.create_group("episode_0")
        s = ep.create_group("setup")
        s["seed"] = seed
        s["difficulty"] = b"easy"
        s["task_goal"] = np.array([goal.encode()])
        s["front_camera_intrinsic"] = np.eye(3)
        for i in range(frames):
            t = ep.create_group(f"timestep_{i}")
            t["action/joint_action"] = np.full(8, i + action_shift)
            t["obs/joint_state"] = np.zeros(7, dtype=np.float32)
            t["obs/gripper_state"] = np.zeros(2, dtype=np.float32)
            t["obs/front_rgb"] = np.zeros((4, 4, 3), dtype=np.uint8)
            t["obs/wrist_rgb"] = np.zeros((4, 4, 3), dtype=np.uint8)
            t["info/is_completed"] = i == frames - 1


def _side(root: Path, side: str, rows, success=True, **h5kw) -> Path:
    d = root / f"{side}-native"
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for r in rows:
        rel = f"episodes/{r['task']}_episode_{r['episode']}/hdf5_files/x.h5"
        if success:
            _h5(d / rel, r["seed"], **h5kw)
        lines.append({"side": side, "tier": r["difficulty"], "task": r["task"], "episode": r["episode"],
                      "seed": r["seed"], "success": success, "path": rel if success else None,
                      "sha256": H.sha256_file(d / rel) if success else None,
                      "env_module": f"robomme_hard.robomme_env.{r['task']}" if side == "H" else None,
                      "worker": "train_split_worker.run_one" if side == "H" else "official._worker",
                      "robomme_module": "/x/src/robomme/__init__.py"})
    (d / "identities.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines))
    return d


@pytest.fixture
def setup_dirs(tmp_path, monkeypatch):
    rows = [{"task": "BinFill", "episode": i, "seed": 100 + i, "difficulty": "easy"} for i in range(3)]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"rows_total": 3, "rows": rows}))
    monkeypatch.setattr(H, "LOCAL_H5_ROOT", tmp_path)
    monkeypatch.setattr(H, "COMPARE_ROOT", tmp_path / "compare")
    monkeypatch.setattr(H, "TOLERANCES", tmp_path / "tol.json")
    return tmp_path, rows, manifest


def test_parser_choices():
    parser = H.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["generate", "--side", "X", "--tier", "native", "--manifest", "m", "--src-root", "s", "--out", "o"])
    args = parser.parse_args(["compare", "--pair", "O:P", "--tier", "native", "--manifest", "m", "--calibrate"])
    assert args.calibrate and args.workers == 16


def test_calibrate_floor_and_ceiling():
    ok, result = H.calibrate([{"action_max": 0.0, "state_max": 0.0, "image_mad": 0.0, "frames_diff": 0}])
    assert ok and result["payload"]["action_max_rad"] == 0.005 and result["payload"]["frames_max"] == 5
    ok, result = H.calibrate([{"action_max": 0.2, "state_max": 0.0, "image_mad": 0.0, "frames_diff": 3}])
    assert not ok and result["ceiling_hit"] == ["action_max"]


def test_binding_rules():
    assert H._binding_ok("H", {"env_module": "robomme_hard.robomme_env.BinFill"})
    assert not H._binding_ok("H", {"env_module": "robomme.robomme_env.BinFill"})
    assert H._binding_ok("O", {"worker": "official._worker", "robomme_module": "/w/src/robomme/__init__.py"})
    assert not H._binding_ok("O", {"worker": "train_split_worker.run_one", "robomme_module": "/w/src/robomme/__init__.py"})


def test_compare_calibrate_then_pass_and_tol_fail(setup_dirs, capsys):
    root, rows, manifest = setup_dirs
    _side(root, "O", rows)
    _side(root, "P", rows, action_shift=0.001)
    assert H.main(["compare", "--pair", "O:P", "--tier", "native", "--manifest", str(manifest), "--calibrate",
                   "--workers", "2"]) == 0
    out = capsys.readouterr().out
    assert "PARITY_TOL_CALIB=PASS" in out and "PARITY_O_P=PASS" in out and "both_success=3" in out
    _side(root, "H", rows, action_shift=0.1)  # 0.1 rad 远超标定阈值 → 容差层 FAIL，判定层仍全等
    assert H.main(["compare", "--pair", "P:H", "--tier", "native", "--manifest", str(manifest), "--workers", "2"]) == 1
    out = capsys.readouterr().out
    assert "PARITY_P_H=FAIL" in out and "tol=FAIL" in out and "setup_equal=3" in out


def test_compare_same_failure_is_not_equal(setup_dirs, capsys):
    root, rows, manifest = setup_dirs
    _side(root, "O", rows, success=False)
    _side(root, "P", rows, success=False)
    (root / "tol.json").write_text(json.dumps({"action_max_rad": 0.01, "state_max": 0.01, "image_mad": 1, "frames_max": 5}))
    assert H.main(["compare", "--pair", "O:P", "--tier", "native", "--manifest", str(manifest), "--workers", "2"]) == 1
    assert "both_success=0" in capsys.readouterr().out


def test_compare_refuses_without_tolerance_file(setup_dirs):
    root, rows, manifest = setup_dirs
    _side(root, "P", rows)
    _side(root, "H", rows)
    with pytest.raises(H.ParityError, match="容差文件不存在"):
        H.main(["compare", "--pair", "P:H", "--tier", "native", "--manifest", str(manifest), "--workers", "2"])


def test_pair_metrics_setup_and_divergence(tmp_path):
    a, b = tmp_path / "a.h5", tmp_path / "b.h5"
    _h5(a, 1, frames=5)
    _h5(b, 1, frames=3, goal="other goal")
    m = H.pair_metrics(str(a), str(b))
    assert m["setup_equal"] is False and m["frames_diff"] == 2 and m["first_divergence"] is None and m["common"] == 3
