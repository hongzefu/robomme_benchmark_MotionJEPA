"""scripts/eval-official/step6_summary.py 的轻量测试：合成的迷你产物布局（纯 CPU；环境栈一项用录制器真编码 ffv1）。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("v75_step6", REPO_ROOT / "scripts" / "eval-official" / "step6_summary.py")
s6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s6)

SMALL = [("A", 3, 100), ("B", 7, 200)]
FULL = SMALL + [("C", 11, 300)]
LAYERS = ("identity", "pre_demo_state", "demo_frames", "reset_obs", "post_demo_state",
          "step_frames", "step_obs", "step_state", "step_status")


def _w(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def _smvla(task, ep, seed, status, steps=100, shard=0):
    return {"checkpoint": "ck", "elapsed_s": 10.0, "error": None, "max_steps": 1300, "seed": seed, "shard": shard,
            "source_episode": ep, "status": status, "steps": steps, "task": task, "task_success": status == "success",
            "video": None, "video_error": None}


def _new(task, ep, seed, status, cond, steps=100, seat="new1", **kw):
    r = {"task": task, "source_episode": ep, "seed": seed, "identity": {"tier": "xhard0", "seed": seed, "source_episode": ep},
         "policy": "smvla", "cond": cond, "status": status, "task_success": status == "success", "steps": steps, "error": None,
         "timing": {"episode_wall_s": 60.0, "env": {"step_mean_s": 0.01}}, "seat": seat, "attempt": 1, "canary": False,
         "infra": False, "rec_dir": None}
    r.update(kw)
    return r


def _frames(seed: int, n: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, size=(n, 16, 16, 3), dtype=np.uint8)


def _env_cell(art: Path, cell: str) -> None:
    rows = []
    for i, (t, ep, seed) in enumerate(SMALL):
        demo = _frames(seed, 2)
        init = _frames(seed + 1, 1)[0]
        joint = np.full((3, 7), seed / 1000, dtype=np.float32)
        grip = np.full((3, 2), 0.04, dtype=np.float32)
        npz = art / "env" / cell / "arrays" / f"{t}.npz"
        npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(npz, **{"demo_frames/front": demo, "demo_frames/wrist": demo, "reset_obs/front_init": init,
                                    "reset_obs/wrist_init": init, "reset_obs/joint_state_list": joint,
                                    "reset_obs/gripper_state_list": grip})
        rows.append({"task": t, "source_episode": ep, "seed": seed, "builder_episode": i, "error": None, "order_index": i,
                     "npz": f"arrays/{t}.npz", "cell": cell, "wall_s": 2.0 + i, "timing": {"make_env_s": 1.0, "demo_s": 0.5},
                     "layers": {L: {"digest": f"d-{L}-{t}", "keys": {"k": f"v-{t}"}} for L in LAYERS}})
    _w(art / "env" / cell / "rows.jsonl", rows)


def _official_rec(root: Path, t: str, ep: int, seed: int, *, bump: int = 0, state_bump: float = 0.0) -> None:
    """用真录制器写一局官方 reset 录制：演示帧 + 初始帧、reset_state（关节 7 + 夹爪 1）。"""
    R = s6.rec_mod()
    rec = R.EpisodeRecorder(root / f"{t}_{ep}_{seed}", {"task": t, "seed": seed, "source_episode": ep, "never_degrade": True},
                            encode_async=False, free_gib_fn=lambda _p: 10000.0)
    rec.set_phase("reset")
    frames = np.concatenate([_frames(seed, 2), _frames(seed + 1, 1)])
    if bump:
        frames[-1] = np.clip(frames[-1].astype(np.int16) + bump, 0, 255).astype(np.uint8)
    fi = rec.add_frames("front", frames, tag="reset")
    wi = rec.add_frames("wrist", frames, tag="reset")
    st = np.concatenate([np.full((3, 7), seed / 1000, dtype=np.float32), np.full((3, 1), 0.04, dtype=np.float32)], axis=1)
    st[-1, 0] += state_bump
    rec.add_array("reset_state", st)
    rec.add_event({"kind": "reset", "ok": True, "front_idx": [fi[0], fi[-1]], "wrist_idx": [wi[0], wi[-1]]})
    rec.set_phase("run")
    rec.close({"status": "fail"})


def _layout(tmp: Path, *, n_complete: bool = True, with_rec: bool = True):
    art, nfs = tmp / "art", tmp / "nfs"
    art.mkdir(parents=True)
    (art / "identities-small48.json").write_text(json.dumps([{"task": t, "source_episode": e, "seed": s} for t, e, s in SMALL]))
    (art / "identities-full192.json").write_text(json.dumps([{"task": t, "source_episode": e, "seed": s} for t, e, s in FULL]))
    _env_cell(art, "C1")
    _env_cell(art, "C2")
    e0 = _w(tmp / "e0" / "episodes-shard00of01.jsonl",
            [_smvla("A", 3, 100, "success"), _smvla("B", 7, 200, "fail"), _smvla("C", 11, 300, "success")])
    _w(nfs / "official" / "O1" / "smvla" / "s0" / "episodes-shard00of01.jsonl",
       [_smvla("A", 3, 100, "success"), _smvla("B", 7, 200, "success"), _smvla("C", 11, 300, "success")])
    _w(nfs / "official" / "O2" / "smvla" / "s0" / "episodes-shard00of01.jsonl",
       [_smvla("A", 3, 100, "fail"), _smvla("B", 7, 200, "fail"), _smvla("C", 11, 300, "success")])
    _w(nfs / "official" / "R1smoke" / "smvla" / "s0" / "episodes-shard00of01.jsonl",
       [_smvla("A", 3, 100, "success"), _smvla("B", 7, 200, "fail")])
    if with_rec:
        rroot = nfs / "stage" / "R1smoke" / "smvla" / "s0" / "rec"
        _official_rec(rroot, "A", 3, 100)
        _official_rec(rroot, "B", 7, 200, bump=10, state_bump=0.5)
    # 正式跑法：两席 + 暂存区逐字重复一份 + 一条基础设施失败（后被正常局取代）+ 一局金丝雀（状态故意不同）
    main_rows = [_new("B", 7, 200, "error", "N", infra=True), _new("A", 3, 100, "success", "N"), _new("B", 7, 200, "fail", "N")]
    _w(art / "official-rec" / "N" / "smvla" / "s-new1" / "smvla" / "results.jsonl", main_rows)
    _w(nfs / "stage" / "N" / "smvla" / "s-new1" / "smvla" / "results.jsonl", main_rows[1:2])
    n2 = [_new("A", 3, 100, "fail", "N", seat="jia", canary=True)]
    if n_complete:
        n2.append(_new("C", 11, 300, "success", "N", seat="new2"))
    _w(art / "official-rec" / "N" / "smvla" / "s-new2" / "smvla" / "results.jsonl", n2)
    # 5.1 本机两格
    _w(art / "newiface" / "E1" / "smvla" / "results.jsonl", [_new("A", 3, 100, "success", "E1"), _new("B", 7, 200, "fail", "E1")])
    _w(art / "newiface" / "E2" / "smvla" / "results.jsonl", [_new("A", 3, 100, "fail", "E2"), _new("B", 7, 200, "fail", "E2")])
    # 第 4 步
    rep = {"comparisons": [{"det": "off", "mode": "same", "bitwise": True, "max_abs": 0.0, "first_diff_step": None, "ref": {"side": "below"}},
                           {"det": "on", "mode": "restart", "bitwise": True, "max_abs": 0.0, "first_diff_step": None, "ref": {"side": "below"}},
                           {"det": "off", "mode": "restart", "bitwise": False, "max_abs": 0.05, "first_diff_step": 2, "ref": {"side": "above"}}],
           "det_rule": {"det_bitwise": True, "slowdown_pct": 5.0, "default": "on", "infer_ms_off": 100.0, "infer_ms_on": 105.0},
           "rng_restored_all": True, "gpu_busy_events": 0}
    (art / "replay" / "P1" / "smvla").mkdir(parents=True)
    (art / "replay" / "P1" / "smvla" / "report.json").write_text(json.dumps(rep))
    (art / "replay" / "iface").mkdir(parents=True)
    (art / "replay" / "iface" / "o1-smvla.json").write_text(json.dumps(
        {"policy": "smvla", "payload_equal": True, "payload_mismatch": 0, "wire_mismatch_vs_official": None, "action": {},
         "exec_new_vs_official": {"exec_equal": True}}))
    # 队列（建好但未完成）
    s6.cq_mod().main(["init", "--queue", str(nfs / "queue" / "prod"), "--policy", "smvla",
                      "--identities", str(art / "identities-full192.json"), "--order", "forward"])
    return art, nfs, e0


def _run(tmp: Path, art: Path, nfs: Path, e0: Path, *extra: str) -> dict:
    out = tmp / "out"
    s6.main(["--art", str(art), "--nfs", str(nfs), "--out", str(out), "--e0-smvla", str(e0),
             "--e0-mme", str(tmp / "nope" / "*.jsonl"), *extra])
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def test_empty_layout_all_pending(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    (art / "identities-small48.json").write_text(json.dumps([{"task": t, "source_episode": e, "seed": s} for t, e, s in SMALL]))
    (art / "identities-full192.json").write_text(json.dumps([{"task": t, "source_episode": e, "seed": s} for t, e, s in FULL]))
    doc = _run(tmp_path, art, tmp_path / "nfs", tmp_path / "missing-e0.jsonl")
    assert not [e for e in doc["entries"] if e["status"] == "ERROR"], [e["line"] for e in doc["entries"] if e["status"] == "ERROR"]
    names = {e["name"] for e in doc["entries"] if e["status"] == "PENDING"}
    for n in ("ENV_DIGEST_PARITY", "OBSERVER_SMOKE", "OFFICIAL_NOISE", "EVAL_PARITY", "RELATIVE_ACCEPT", "POLICY_REPLAY", "IFACE_OPEN", "CANARY"):
        assert n in names
    for f in s6.FRAGMENTS:
        assert (tmp_path / "out" / "fragments" / f"{f}.md").exists()


def test_full_layout_verdicts(tmp_path):
    art, nfs, e0 = _layout(tmp_path)
    doc = _run(tmp_path, art, nfs, e0)
    errs = [e["line"] for e in doc["entries"] if e["status"] == "ERROR"]
    assert not errs, errs
    line = lambda e: e["line"]  # noqa: E731
    # 2.1
    p = [e for e in doc["entries"] if e["name"] == "ENV_DIGEST_PARITY" and "pair=C1:C2" in e["line"]][0]
    assert p["status"] == "INFO" and "compared=2" in p["line"] and "first_diff=-" in p["line"]
    # 环境栈：A 全同；B 初始帧 +10、状态末行 +0.5
    st = [e for e in doc["entries"] if e["name"] == "ENV_STACK" and "src=R1" in e["line"] and "policy=smvla" in e["line"]][0]
    assert st["status"] == "INFO", st["line"]
    assert "demo_count_equal=2/2" in st["line"] and "state_max_abs=0.5" in st["line"]
    init_mad = float(st["line"].split("init_mad_max=")[1].split()[0])
    assert 9.0 < init_mad <= 10.0  # +10 后截断到 255，均值略低于 10
    assert "frames_sha_equal=10/12" in st["line"]
    # E0 自比
    assert any("E0_SELF=INFO policy=smvla compared=3" in line(e) and "sanity=ok" in line(e) for e in doc["entries"])
    # 官方噪声带三对
    noise = [e for e in doc["entries"] if e["name"] == "OFFICIAL_NOISE" and e["status"] == "INFO"]
    assert len(noise) == 3
    assert any("pair=历史:重跑一" in e["line"] and "f2s=1" in e["line"] for e in noise)
    # 正式跑法：金丝雀与 infra 行不进比较；逐字重复不算重复终态
    ra = [e for e in doc["entries"] if e["name"] == "RELATIVE_ACCEPT"][0]
    assert ra["status"] == "INFO" and "inside=" in ra["line"], ra["line"]
    pvo = [e for e in doc["entries"] if e["name"] == "PROD_VS_OFFICIAL" and "ref=历史" in e["line"]][0]
    assert "compared=3" in pvo["line"] and "s2f=0" in pvo["line"] and "f2s=0" in pvo["line"]
    merged = (tmp_path / "out" / "merged" / "N-smvla.jsonl").read_text().splitlines()
    assert len(merged) == 3
    can = [e for e in doc["entries"] if e["name"] == "CANARY"][0]
    assert can["status"] == "INFO" and "status_eq_N=0/1" in can["line"] and "seats=jia" in can["line"]
    assert any(e["name"] == "EXTRA_SAMPLE" for e in doc["entries"])
    # 5.1
    ep = [e for e in doc["entries"] if e["name"] == "EVAL_PARITY" and "pair=E1:E2" in e["line"] and e["status"] == "INFO"]
    assert ep and "s2f=1" in ep[0]["line"]
    assert any(e["name"] == "EVAL_PARITY" and "pair=R1:E1" in e["line"] and e["status"] == "INFO" for e in doc["entries"])
    assert any(e["name"] == "EVAL_VS_E0" and "cond=E1" in e["line"] and e["status"] == "INFO" for e in doc["entries"])
    assert any(e["name"] == "EVAL_PARITY" and "pair=E1:E3" in e["line"] and e["status"] == "PENDING" for e in doc["entries"])
    # 第 4 步
    pr = [e for e in doc["entries"] if e["name"] == "POLICY_REPLAY" and "cond=P1" in e["line"] and e["status"] == "INFO"]
    assert any("det=off" in e["line"] and "mode=restart" in e["line"] and "bitwise=0/1" in e["line"] for e in pr)
    dr = [e for e in doc["entries"] if e["name"] == "DET_RULE" and "cond=P1" in e["line"]][0]
    assert "default=on" in dr["line"] and "recheck=same" in dr["line"]
    assert any(e["name"] == "IFACE_OPEN" and e["status"] == "INFO" and "payload_equal=yes" in e["line"] for e in doc["entries"])
    # 队列未完成 → PENDING；预算
    q = [e for e in doc["entries"] if e["name"] == "QUEUE_CLAIM" and "policy=smvla" in e["line"]][0]
    assert q["status"] == "PENDING" and "missing=3" in q["line"]
    b = [e for e in doc["entries"] if e["line"].startswith("BUDGET=INFO item=5.2_正式跑法")][0]
    assert "attempts=4" in b["line"] and "unique=3" in b["line"]
    assert any(e["line"].startswith("BUDGET=INFO item=5.2_金丝雀 attempts=1") for e in doc["entries"])
    # 留档片段
    md = (tmp_path / "out" / "fragments" / "prod-vs-official.md").read_text(encoding="utf-8")
    assert "RELATIVE_ACCEPT" in md and "5.2 正式跑法" in md


def test_idempotent_and_final_blocks(tmp_path):
    art, nfs, e0 = _layout(tmp_path, n_complete=False, with_rec=False)
    d1 = _run(tmp_path, art, nfs, e0)
    d2 = _run(tmp_path, art, nfs, e0)
    assert [e["line"] for e in d1["entries"]] == [e["line"] for e in d2["entries"]]
    ra = [e for e in d1["entries"] if e["name"] == "RELATIVE_ACCEPT"][0]
    assert ra["status"] == "PENDING" and "N:2/3" in ra["line"]
    d3 = _run(tmp_path, art, nfs, e0, "--final")
    ra3 = [e for e in d3["entries"] if e["name"] == "RELATIVE_ACCEPT"][0]
    assert ra3["status"] == "BLOCKED" and "blocked=yes" in ra3["line"], ra3["line"]
    d4 = _run(tmp_path, art, nfs, e0, "--partial")
    assert any(e["name"] == "PROD_VS_OFFICIAL" and "partial=yes" in e["line"] for e in d4["entries"])
