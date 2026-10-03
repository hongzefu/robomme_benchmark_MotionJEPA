"""scripts/eval-official/compare.py 的轻量测试（纯 CPU、合成数据为主，身份规则用真实清单）。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("v75_compare", REPO_ROOT / "scripts" / "eval-official" / "compare.py")
cmp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmp)


def _w(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _mme(task, ep, seed, status, steps, attempt=1, shard=0):
    return {"task": task, "source_episode": ep, "seed": seed, "status": status, "task_success": status == "success",
            "steps": steps, "error": None, "max_steps": 1300, "attempt": attempt, "shard": shard, "video": "x.mp4"}


def _smvla(task, ep, seed, status, steps, shard=0):
    return {"checkpoint": "ck", "elapsed_s": 10.0 + steps / 100, "error": None, "max_steps": 1300, "seed": seed, "shard": shard,
            "source_episode": ep, "status": status, "steps": steps, "task": task, "task_success": status == "success",
            "video": None, "video_error": None}


def _new(task, ep, seed, status, steps):
    return {"task": task, "source_episode": ep, "seed": seed, "identity": {"tier": "xhard0", "seed": seed, "source_episode": ep},
            "policy": "mme", "cond": "N", "status": status, "task_success": status == "success", "steps": steps, "error": None,
            "timing": {"reset_s": 1.0, "policy": {"infer_s": 0.5}}, "seat": "甲", "attempt": 1}


# ---------------- 加载器 ----------------


def test_loaders_three_formats_and_last_final_wins(tmp_path):
    _w(tmp_path / "mme" / "s0" / "episodes.jsonl", [
        _mme("A", 3, 100, "error", 5, attempt=1),
        _mme("A", 3, 100, "success", 50, attempt=2),
        _mme("A", 7, 101, "fail", 70),
        {"task": "A", "source_episode": 11, "seed": 102, "status": "ongoing", "steps": 3, "attempt": 1},
    ])
    t, st = cmp.load_results(str(tmp_path / "mme"))
    assert t[("A", 100)]["status"] == "success" and t[("A", 100)]["attempt"] == 2
    assert t[("A", 100)]["format"] == "mme"
    assert ("A", 102) not in t
    assert st == {"files": 1, "lines": 4, "non_final": 1, "superseded": 1, "records": 2}

    _w(tmp_path / "sm" / "episodes-shard00of10.jsonl", [_smvla("A", 3, 100, "timeout", 1344)])
    _w(tmp_path / "sm" / "episodes-shard01of10.jsonl", [_smvla("A", 7, 101, "success", 400, shard=1)])
    t2, _ = cmp.load_results(str(tmp_path / "sm" / "episodes-shard*.jsonl"))
    assert t2[("A", 100)]["format"] == "smvla" and t2[("A", 100)]["timing"]["elapsed_s"] == pytest.approx(23.44)
    assert len(t2) == 2

    _w(tmp_path / "new" / "results.jsonl", [_new("A", 3, 100, "fail", 90)])
    t3, _ = cmp.load_results(str(tmp_path / "new"))
    assert t3[("A", 100)]["format"] == "new" and t3[("A", 100)]["source_episode"] == 3


# ---------------- 统计 ----------------


def test_mcnemar_exact_values():
    assert cmp.mcnemar_exact(5, 0) == pytest.approx(0.0625)
    assert cmp.mcnemar_exact(0, 0) == 1.0
    assert cmp.mcnemar_exact(3, 3) == 1.0
    # b=1,c=9: 2*(1+10)/1024
    assert cmp.mcnemar_exact(1, 9) == pytest.approx(22 / 1024)


def test_bootstrap_deterministic_and_zero():
    rng = np.random.default_rng(1)
    a = rng.integers(0, 2, 60).astype(float)
    b = rng.integers(0, 2, 60).astype(float)
    assert cmp.paired_bootstrap_ci(a, b) == cmp.paired_bootstrap_ci(a, b)
    assert cmp.paired_bootstrap_ci(a, a) == (0.0, 0.0)


def _tab(rows):
    return {(r[0], r[1]): {"task": r[0], "seed": r[1], "source_episode": 3, "status": r[2], "steps": r[3], "src": "t", "rec_dir": None}
            for r in rows}


def test_transition_matrix_and_zero_keys():
    a = _tab([("A", 1, "success", 10), ("A", 2, "fail", 20), ("A", 3, "fail", 30), ("A", 4, "success", 40), ("A", 5, "timeout", 1301)])
    b = _tab([("A", 1, "fail", 12), ("A", 2, "success", 20), ("A", 3, "error", None), ("A", 4, "success", 44), ("A", 5, "fail", 50)])
    r = cmp.compare_tables(a, b)
    assert (r["s2f"], r["f2s"], r["new_err"], r["lost_err"], r["new_timeout"], r["lost_timeout"]) == (1, 1, 1, 0, 0, 1)
    assert r["status_matrix"]["success"]["fail"] == 1
    assert r["status_matrix"]["timeout"]["fail"] == 1
    # 零计数也显式存在（P4）
    for sa in cmp.STATUSES:
        assert set(r["status_matrix"][sa]) == set(cmp.STATUSES)
    assert r["status_matrix"]["error"]["error"] == 0
    # 步数只比两边都是 success/fail 的身份：1、2、4
    assert r["steps_compared"] == 3 and r["steps_diff_p50"] == 2.0
    assert r["sr_diff_pp"] == pytest.approx(0.0)
    assert r["granularity_pp_per_episode"] == pytest.approx(20.0)
    js = json.loads(cmp.dumps(r))
    for k in ("s2f", "f2s", "new_err", "lost_err", "new_timeout", "lost_timeout", "missing_a", "missing_b"):
        assert k in js


def test_compare_with_identity_keys_reports_missing():
    a = _tab([("A", 1, "success", 10)])
    b = _tab([("A", 1, "success", 10), ("A", 2, "fail", 5)])
    r = cmp.compare_tables(a, b, keys=[("A", 1), ("A", 2)])
    assert r["compared"] == 1 and r["missing_a"] == 1 and r["missing_b"] == 0


# ---------------- 相对标准 ----------------


def _pairres(s2f, f2s, sr, hw, compared=192, missing_a=0, missing_b=0):
    return {"s2f": s2f, "f2s": f2s, "sr_diff_pp": sr, "ci95_pp": [sr - hw, sr + hw], "ci_half_width_pp": hw, "compared": compared,
            "missing_a": missing_a, "missing_b": missing_b, "flips": []}


def test_relative_accept_inside_and_outside():
    noise = [("历史:重跑一", _pairres(2, 3, 0.52, 2.0)), ("历史:重跑二", _pairres(4, 1, -1.56, 2.1)), ("重跑一:重跑二", _pairres(3, 2, -0.52, 2.2))]
    ok = cmp.relative_accept(noise, _pairres(4, 3, -0.52, 2.5))
    assert ok["inside"] and not ok["extra_sample_trigger"] and ok["note"] is None
    # 边界：等于最大翻转数、等于最小 sr 仍在内
    edge = cmp.relative_accept(noise, _pairres(4, 3, -1.56, 1.0))
    assert edge["inside"]
    assert not cmp.relative_accept(noise, _pairres(5, 0, -1.0, 1.0))["inside"]  # s2f 超
    assert not cmp.relative_accept(noise, _pairres(0, 4, 0.0, 1.0))["inside"]  # f2s 超
    out_sr = cmp.relative_accept(noise, _pairres(1, 1, 1.04, 1.0))
    assert not out_sr["inside"] and out_sr["cond_s2f"] and out_sr["cond_f2s"] and not out_sr["cond_sr"]
    assert cmp.relative_accept(noise, _pairres(0, 0, 0.0, 4.5))["extra_sample_trigger"]


def test_relative_accept_all_zero_official_flips():
    noise = [(k, _pairres(0, 0, 0.0, 0.0)) for k in ("历史:重跑一", "历史:重跑二", "重跑一:重跑二")]
    main = _pairres(1, 0, -0.52, 0.5)
    main["flips"] = [{"task": "A", "seed": 1, "status_a": "success", "status_b": "fail"}]
    r = cmp.relative_accept(noise, main)
    assert r["note"] == "官方重跑无翻转" and r["official_all_zero_flips"]
    # 不套退化区间：inside 不给 yes/no
    assert r["inside"] is None and r["prod_flips"] == main["flips"]
    r0 = cmp.relative_accept(noise, _pairres(0, 0, 0.0, 0.0))
    assert r0["inside"] is None and r0["prod_flips"] == []


def test_relative_accept_blocks_on_missing_or_unequal_compared():
    noise = [("历史:重跑一", _pairres(2, 3, 0.52, 2.0)), ("历史:重跑二", _pairres(4, 1, -1.56, 2.1)), ("重跑一:重跑二", _pairres(3, 2, -0.52, 2.2))]
    r = cmp.relative_accept(noise, _pairres(0, 0, 0.0, 1.0, compared=191, missing_b=1))
    assert r["blocked"] and r["inside"] is None and len(r["blocking"]) == 2
    noise2 = [noise[0], noise[1], ("重跑一:重跑二", _pairres(3, 2, -0.52, 2.2, compared=190))]
    r2 = cmp.relative_accept(noise2, _pairres(0, 0, 0.0, 1.0))
    assert r2["blocked"] and any("compared 不一致" in b for b in r2["blocking"])


def test_relative_accept_cli_blocked_exit_nonzero(tmp_path, capsys):
    ids = [{"task": "A", "seed": s} for s in (1, 2, 3)]
    (tmp_path / "ids.json").write_text(json.dumps(ids))
    full = [_mme("A", 3 + 4 * i, s, "success", 10) for i, s in enumerate((1, 2, 3))]
    for n in ("e0", "o1", "o2"):
        _w(tmp_path / n / "episodes.jsonl", full)
    _w(tmp_path / "prod" / "results.jsonl", [_new("A", 3, 1, "success", 10), _new("A", 7, 2, "fail", 10)])
    rc = cmp.main(["relative-accept", "--policy", "mme", "--identities", str(tmp_path / "ids.json"),
                   *sum(([f"--{n}", str(tmp_path / n)] for n in ("e0", "o1", "o2", "prod")), [])])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc != 0 and "inside=n/a" in last and "blocked=yes" in last
    with pytest.raises(SystemExit):
        cmp.main(["relative-accept", "--policy", "mme", *sum(([f"--{n}", str(tmp_path / n)] for n in ("e0", "o1", "o2", "prod")), [])])


# ---------------- 开环动作差 ----------------


def test_action_diff_metrics(tmp_path):
    a = np.zeros((5, 2), dtype=np.float32)
    a[:, 0] = [0, 1, 2, 3, 4]  # 维 0 范围 4
    b = a.copy()
    b[3, 0] += 0.5
    b[4, 1] = 0.1  # 维 1 范围 0 → rel inf
    r = cmp.action_diff(a, b)
    assert r["first_diff_step"] == 3 and r["neq"] == 2
    assert r["dim_max_abs"] == pytest.approx([0.5, 0.1], rel=1e-6)
    assert r["dim_max_rel"][0] == pytest.approx(0.125) and np.isinf(r["dim_max_rel"][1])
    assert r["dim_mean_abs"][0] == pytest.approx(0.1)
    same = cmp.action_diff(a, a)
    assert same["neq"] == 0 and same["first_diff_step"] is None and same["max_rel"] == 0.0
    # 长度不同、前缀相同：分叉步 = 较短长度
    assert cmp.action_diff(a, a[:3])["first_diff_step"] == 3


def test_first_divergence_uses_env_step(tmp_path):
    x = np.zeros((4, 8))
    y = x.copy()
    y[2, 0] = 1.0
    for side, arr in (("a", x), ("b", y)):
        d = tmp_path / side / "ep"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"task": "A", "seed": 1}))
        np.savez(d / "arrays.npz", exec_action=arr, **{"exec_action.step": np.array([0, 16, 32, 48])})
    tab = _tab([("A", 1, "success", 10)])
    rows = [{"task": "A", "seed": 1}]
    fd = cmp.first_divergence(rows, tab, tab, str(tmp_path / "a"), str(tmp_path / "b"))
    assert rows[0]["first_div"] == 32 and rows[0]["first_div_index"] == 2 and fd["unit"] == "env_step"
    assert cmp.to_env_step(2, None, None) == 2


def test_freeze_empty_group_and_no_overwrite(tmp_path, monkeypatch, capsys):
    f = tmp_path / "x.txt"
    f.write_text("x")
    monkeypatch.setattr(cmp, "e0_file_groups", lambda: {"manifest": [f], "videos": []})
    out = tmp_path / "m.json"
    ns = cmp.build_parser().parse_args(["freeze", "--out", str(out)])
    assert cmp.cmd_freeze(ns) == 1 and "E0_FREEZE=FAIL" in capsys.readouterr().out
    monkeypatch.setattr(cmp, "e0_file_groups", lambda: {"manifest": [f]})
    assert cmp.cmd_freeze(ns) == 0 and out.exists()
    assert cmp.cmd_freeze(ns) == 1  # 已存在，拒绝覆盖
    assert cmp.cmd_freeze(cmp.build_parser().parse_args(["freeze", "--out", str(out), "--force"])) == 0
    assert cmp.cmd_freeze(cmp.build_parser().parse_args(["freeze", "--out", str(out), "--check"])) == 0


def test_load_array_layouts(tmp_path):
    x = np.arange(12, dtype=np.float32).reshape(4, 3)
    d1 = tmp_path / "r1"
    d1.mkdir()
    np.savez(d1 / "arrays.npz", exec_action=x, **{"exec_action.step": np.arange(4)})
    d2 = tmp_path / "r2" / "arrays"
    d2.mkdir(parents=True)
    np.save(d2 / "exec_action.npy", x)
    d3 = tmp_path / "r3.npz"
    np.savez(d3, **{f"exec_action/{i}": x[i] for i in range(4)})
    for p in (d1, tmp_path / "r2", d3):
        arr, _ = cmp.load_array(p, "exec_action")
        assert np.array_equal(arr, x)


def test_action_diff_cli_line(tmp_path, capsys):
    x = np.zeros((3, 8))
    np.savez(tmp_path / "a.npz", model_action=x)
    np.savez(tmp_path / "b.npz", model_action=x + 0.05)
    cmp.main(["action-diff", "--a", str(tmp_path / "a.npz"), "--b", str(tmp_path / "b.npz"), "--cond", "same", "--policy", "mme", "--mode", "same"])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("POLICY_REPLAY=INFO cond=same policy=mme det=no mode=same")
    assert "vs_action_max=above" in line and "first_diff_step=0" in line


# ---------------- 身份 ----------------


def test_small48_rule_real_manifest():
    rows = cmp.load_xhard0_rows()
    small = cmp.select_small48(rows)
    assert len(small) == 48
    pick = [r["episode"] for r in small if r["task"] == "PickXtimes"]
    assert pick == [3, 7, 11]
    assert all([r["episode"] for r in small if r["task"] == t] == [3, 7, 11] for t in {r["task"] for r in rows})


def test_build_identities_synthetic(tmp_path):
    xrows = [{"task": "A", "episode": ep, "seed": 1000 + ep} for ep in (3, 7, 11, 15)]
    man = [{"task": "A", "source_episode": ep, "seed": 1000 + ep, "shard": ep % 2} for ep in (15, 3, 11, 7)]
    f0 = _w(tmp_path / "m0.jsonl", [_mme("A", 11, 1011, "fail", 1, shard=1), _mme("A", 3, 1003, "fail", 1, shard=1), _mme("A", 7, 1007, "fail", 1, shard=1), _mme("A", 15, 1015, "fail", 1, shard=1)])
    s0 = _w(tmp_path / "s0.jsonl", [_smvla("A", ep, 1000 + ep, "fail", 1, shard=1) for ep in (3, 7, 11, 15)])
    full, small, problems = cmp.build_identities(xrows, man, [f0], [s0])
    # 规模不足 192/48 会报问题，但逐身份字段应正确
    assert any("192" in p for p in problems)
    e = {x["source_episode"]: x for x in full}
    assert e[11]["e0_mme_order"] == 0 and e[3]["e0_mme_order"] == 1 and e[15]["builder_episode"] == 3
    assert [x["source_episode"] for x in small] == [3, 7, 11]
    # seed 不符被发现
    man[0]["seed"] = 9
    _, _, p2 = cmp.build_identities(xrows, man, [f0], [s0])
    assert any("seed 不符" in p for p in p2)


def test_shuffle_order_deterministic():
    full = [{"task": "A", "seed": i} for i in range(20)]
    assert cmp.shuffle_order(full) == cmp.shuffle_order(full)
    assert cmp.shuffle_order(full) != full


def test_summarize_speed():
    recs = [_new("A", 3, 1, "fail", 5), _new("A", 7, 2, "fail", 5)]
    recs[1]["timing"]["reset_s"] = 3.0
    s = cmp.summarize_speed(recs, "seat")
    assert s["甲"]["reset_s"]["p50"] == 2.0 and s["甲"]["policy.infer_s"]["n"] == 2
