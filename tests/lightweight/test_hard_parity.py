"""``scripts/parity/hard_parity.py``（三侧对拍入口）的纯 CPU 测试：合成 h5，不起仿真。

覆盖：参数解析、每侧自检、逐对指标（setup／结构／四项容差／首个分叉步）、容差标定的下界与上界、
包归属判定、端到端 compare 的判定层与容差层（含超阈值即 FAIL、两侧同失败单列 both_fail）。
V7（0928 方案第二部分 §1.5）：P 侧须显式目录或 --p-anchor、--run-name 另起子目录、超容差按首个分叉步分
noise／fail（``_classify_over``）、5% 硬线、recovery_mode 不符即 FAIL、xhard0 身份核对（``check_xhard0``）。
"""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from scripts.parity import hard_parity as H


def _h5(path: Path, seed: int, frames: int = 4, action_shift: float = 0.0, goal: str = "pick up the cube",
        shift_from: int = 0) -> None:
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
            t["action/joint_action"] = np.full(8, i + (action_shift if i >= shift_from else 0.0))
            t["obs/joint_state"] = np.zeros(7, dtype=np.float32)
            t["obs/gripper_state"] = np.zeros(2, dtype=np.float32)
            t["obs/front_rgb"] = np.zeros((4, 4, 3), dtype=np.uint8)
            t["obs/wrist_rgb"] = np.zeros((4, 4, 3), dtype=np.uint8)
            t["info/is_completed"] = i == frames - 1


def _side(root: Path, side: str, rows, success=True, tier: str = "native", extra=None, **h5kw) -> Path:
    """合成一侧目录 ``<root>/<side>-<tier>``；``success`` 可为布尔或逐行列表，``extra`` 为逐行附加字段。"""
    d = root / f"{side}-{tier}"
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    flags = success if isinstance(success, list) else [success] * len(rows)
    extras = extra if isinstance(extra, list) else [extra or {}] * len(rows)
    for r, success, more in zip(rows, flags, extras):
        rel = f"episodes/{r['task']}_episode_{r['episode']}/hdf5_files/x.h5"
        if success:
            _h5(d / rel, r["seed"], **h5kw)
        lines.append({"side": side, "tier": r["difficulty"], "task": r["task"], "episode": r["episode"],
                      "seed": r["seed"], "success": success, "path": rel if success else None,
                      "sha256": H.sha256_file(d / rel) if success else None,
                      "env_module": f"robomme_hard.robomme_env.{r['task']}" if side == "H" else None,
                      "worker": "train_split_worker.run_one" if side == "H" else "official._worker",
                      "robomme_module": "/x/src/robomme/__init__.py", **more})
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


TOL = {"action_max_rad": 0.01, "state_max": 0.01, "image_mad": 1, "frames_max": 5}


def test_compare_calibrate_then_pass_and_tol_fail(setup_dirs, capsys):
    root, rows, manifest = setup_dirs
    _side(root, "O", rows)
    _side(root, "P", rows, action_shift=0.001)
    # V7：P 侧不给 --p-anchor 时须显式给目录（合成数据没有锚点登记）
    assert H.main(["compare", "--pair", "O:P", "--tier", "native", "--manifest", str(manifest), "--calibrate",
                   "--right", str(root / "P-native"), "--workers", "2"]) == 0
    out = capsys.readouterr().out
    assert "PARITY_TOL_CALIB=PASS" in out and "PARITY_O_P=PASS" in out and "both_success=3" in out
    _side(root, "H", rows, action_shift=0.1)  # 0.1 rad 远超标定阈值且从第 0 步起就分叉 → fail 类超容差
    assert H.main(["compare", "--pair", "P:H", "--tier", "native", "--manifest", str(manifest),
                   "--left", str(root / "P-native"), "--workers", "2"]) == 1
    out = capsys.readouterr().out
    assert "PARITY_P_H=FAIL" in out and "tol_over=3" in out and "noise=0" in out and "setup_equal=3" in out
    assert "hard_line_5pct=HIT" in out


def test_compare_both_fail_counted_separately(setup_dirs, capsys):
    """V7（§1.5）：两侧同样没产出单列 both_fail，不算不一致；另打 PARITY_BOTH_FAIL=REVIEW 供人工复核。"""
    root, rows, manifest = setup_dirs
    _side(root, "O", rows, success=False)
    _side(root, "P", rows, success=False)
    (root / "tol.json").write_text(json.dumps(TOL))
    assert H.main(["compare", "--pair", "O:P", "--tier", "native", "--manifest", str(manifest),
                   "--right", str(root / "P-native"), "--workers", "2"]) == 0
    out = capsys.readouterr().out
    assert "both_success=0" in out and "both_fail=3" in out and "PARITY_BOTH_FAIL=REVIEW" in out


def test_compare_one_side_failure_is_not_equal(setup_dirs, capsys):
    root, rows, manifest = setup_dirs
    _side(root, "O", rows)
    _side(root, "P", rows, success=[True, False, True])
    (root / "tol.json").write_text(json.dumps(TOL))
    assert H.main(["compare", "--pair", "O:P", "--tier", "native", "--manifest", str(manifest),
                   "--right", str(root / "P-native"), "--workers", "2"]) == 1
    out = capsys.readouterr().out
    assert "PARITY_O_P=FAIL" in out and "success_equal=2" in out and "both_fail=0" in out


def test_compare_refuses_without_tolerance_file(setup_dirs):
    root, rows, manifest = setup_dirs
    _side(root, "P", rows)
    _side(root, "H", rows)
    with pytest.raises(H.ParityError, match="容差文件不存在"):
        H.main(["compare", "--pair", "P:H", "--tier", "native", "--manifest", str(manifest),
                "--left", str(root / "P-native"), "--workers", "2"])


def test_compare_p_side_requires_anchor_or_dir(setup_dirs):
    root, rows, manifest = setup_dirs
    _side(root, "O", rows)
    _side(root, "P", rows)
    with pytest.raises(H.ParityError, match="--p-anchor"):
        H.main(["compare", "--pair", "O:P", "--tier", "native", "--manifest", str(manifest), "--workers", "2"])


def test_compare_unregistered_anchor_fails(setup_dirs, monkeypatch, capsys):
    root, rows, manifest = setup_dirs
    _side(root, "O", rows)
    monkeypatch.setattr(H, "ANCHORS", root / "anchors.json")  # 空登记表
    assert H.main(["compare", "--pair", "O:P", "--tier", "native", "--manifest", str(manifest),
                   "--p-anchor", "no-such-tag", "--workers", "2"]) == 1
    assert "PARITY_ANCHOR=FAIL tag=no-such-tag" in capsys.readouterr().out


def test_compare_roots_and_run_name(setup_dirs, capsys):
    """--h5-root／--compare-root 显式目录；比对目录已存在时拒绝，--run-name 另起子目录。"""
    root, rows, manifest = setup_dirs
    h5_root, compare_root = root / "h5x", root / "cmpx"
    _side(h5_root, "O", rows)
    _side(h5_root, "H", rows)
    (root / "tol.json").write_text(json.dumps(TOL))
    argv = ["compare", "--pair", "O:H", "--tier", "native", "--manifest", str(manifest), "--h5-root", str(h5_root),
            "--compare-root", str(compare_root), "--workers", "2"]
    assert H.main(argv) == 0
    assert (compare_root / "OH-native" / "h5_pairs.jsonl").is_file()
    capsys.readouterr()
    with pytest.raises(H.ParityError, match="--run-name"):
        H.main(argv)
    assert H.main(argv + ["--run-name", "r2"]) == 0
    assert (compare_root / "OH-native" / "r2" / "h5_pairs.jsonl").is_file()


def test_classify_over_cases():
    """B3：setup／结构／成功与否都相等且首个分叉步 > 0 才算 noise；其余一律 fail。"""
    base = {"setup_equal": True, "schema_equal": True, "success_same": True, "first_divergence": 5}
    assert H._classify_over(base) == "noise"
    assert H._classify_over({**base, "first_divergence": 0}) == "fail"
    assert H._classify_over({**base, "first_divergence": None}) == "fail"
    assert H._classify_over({**base, "setup_equal": False}) == "fail"
    assert H._classify_over({**base, "schema_equal": False}) == "fail"
    assert H._classify_over({**base, "success_same": False}) == "fail"
    assert H._classify_over({k: v for k, v in base.items() if k != "success_same"}) == "fail"


def _many_rows(n):
    return [{"task": "BinFill", "episode": i, "seed": 500 + i, "difficulty": "easy"} for i in range(n)]


def _merge_sides(target: Path, parts: list[Path]) -> None:
    """把几段合成目录（各自 identities.jsonl 与 h5）合并成一侧目录。"""
    target.mkdir(parents=True)
    lines = []
    for part in parts:
        lines += [t for t in (part / "identities.jsonl").read_text().splitlines() if t.strip()]
        for f in part.rglob("*.h5"):
            dest = target / f.relative_to(part)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    (target / "identities.jsonl").write_text("".join(t + "\n" for t in lines))


@pytest.mark.parametrize("n_over", [1, 2])
def test_compare_noise_and_5pct_hard_line(tmp_path, monkeypatch, capsys, n_over):
    """21 局：1 局 noise 类超容差（≤5%）→ PASS；2 局超容差（>5%）→ 5% 硬线 FAIL，不论分类。"""
    monkeypatch.setattr(H, "TOLERANCES", tmp_path / "tol.json")
    (tmp_path / "tol.json").write_text(json.dumps(TOL))
    rows = _many_rows(21)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"rows_total": len(rows), "rows": rows}))
    root = tmp_path / "h5"
    _side(root, "O", rows)
    # 前 n_over 局从第 2 步起才分叉（setup／结构／成功与否相同）→ noise 类
    noisy = _side(tmp_path / "a", "H", rows[:n_over], action_shift=0.5, shift_from=2)
    clean = _side(tmp_path / "b", "H", rows[n_over:])
    _merge_sides(root / "H-native", [noisy, clean])
    rc = H.main(["compare", "--pair", "O:H", "--tier", "native", "--manifest", str(manifest), "--h5-root", str(root),
                 "--compare-root", str(tmp_path / "cmp"), "--workers", "2"])
    out = capsys.readouterr().out
    assert f"noise={n_over}" in out and "tol_over=0" in out
    if n_over == 1:
        assert rc == 0 and "PARITY_O_H=PASS" in out and "hard_line_5pct=ok" in out
    else:
        assert rc == 1 and "PARITY_O_H=FAIL" in out and "hard_line_5pct=HIT" in out


def test_compare_recovery_mode_mismatch_fails(setup_dirs, capsys):
    """xhard0：两侧 recovery_mode 不同（官方按 episode 号定）即判定层 FAIL。"""
    root, rows, manifest = setup_dirs
    _side(root, "O", rows, tier="xhard0", extra=[{"recovery_mode": "xy"}, {"recovery_mode": "off"}, {"recovery_mode": "off"}])
    _side(root, "H", rows, tier="xhard0", extra=[{"recovery_mode": "off"}] * 3)
    (root / "tol.json").write_text(json.dumps(TOL))
    assert H.main(["compare", "--pair", "O:H", "--tier", "xhard0", "--manifest", str(manifest), "--workers", "2"]) == 1
    out = capsys.readouterr().out
    assert "recovery_mismatch=1" in out and "shape=16x1x12" in out


def test_pair_metrics_setup_and_divergence(tmp_path):
    a, b = tmp_path / "a.h5", tmp_path / "b.h5"
    _h5(a, 1, frames=5)
    _h5(b, 1, frames=3, goal="other goal")
    m = H.pair_metrics(str(a), str(b))
    assert m["setup_equal"] is False and m["frames_diff"] == 2 and m["first_divergence"] is None and m["common"] == 3
