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
    assert ra["status"] == "PENDING" and "N+N2:2/3" in ra["line"]
    d3 = _run(tmp_path, art, nfs, e0, "--final")
    ra3 = [e for e in d3["entries"] if e["name"] == "RELATIVE_ACCEPT"][0]
    assert ra3["status"] == "BLOCKED" and "blocked=yes" in ra3["line"], ra3["line"]
    d4 = _run(tmp_path, art, nfs, e0, "--partial")
    assert any(e["name"] == "PROD_VS_OFFICIAL" and "partial=yes" in e["line"] for e in d4["entries"])


VK_ERR = "Traceback (most recent call last):\n  File x\nRuntimeError: vk::PhysicalDevice::createDeviceUnique: ErrorInitializationFailed"


def test_incident_n2_merge_infra_and_vulkanfail(tmp_path):
    """GPU 计算模式事故：原队列里 B、C 被 0 步 infra 终态毒化，由补跑队列 N2 补上；*-vulkanfail-* 留档不进比较。"""
    art, nfs, e0 = _layout(tmp_path, n_complete=False, with_rec=False)
    vk = dict(infra=True, infra_reason="env_build", error=VK_ERR)
    # 原队列 done/：A 正常、B 与 C 毒化（与 results.jsonl 同 claim_token 的副本会被去重）
    qd = nfs / "queue" / "prod" / "smvla" / "done"
    for f in qd.glob("*.json"):
        f.unlink()
    docs = {"A_100": _new("A", 3, 100, "success", "N", claim_token="tA"),
            "B_200": _new("B", 7, 200, "error", "N", steps=0, seat="new4", claim_token="tB", **vk),
            "C_300": _new("C", 11, 300, "error", "N", steps=0, seat="new4", claim_token="tC", **vk)}
    for k, d in docs.items():
        (qd / f"{k}.json").write_text(json.dumps(dict(d, _claim={"x": 1}, _committed_at=1.0)))
    _w(art / "official-rec" / "N2" / "smvla" / "s-new1" / "smvla" / "results.jsonl",
       [_new("C", 11, 300, "success", "N2", claim_token="tC2")])
    # 事故留档：1 局真实 + 2 局 infra；若被误并入 E5，E5 的 A 会变成 fail
    _w(art / "official-rec" / "E5" / "smvla" / "s-ding-vulkanfail-0540" / "smvla" / "results.jsonl",
       [_new("A", 3, 100, "fail", "E5", seat="ding"), _new("B", 7, 200, "error", "E5", steps=0, seat="ding", **vk),
        _new("A", 3, 100, "error", "E5", steps=0, seat="ding", **vk)])
    _w(art / "official-rec" / "E5" / "smvla" / "s-ding" / "smvla" / "results.jsonl",
       [_new("A", 3, 100, "success", "E5", seat="ding"), _new("B", 7, 200, "fail", "E5", seat="ding")])
    # 旧官方启动器写下的 0 步 Vulkan error 行（排在真实结果之后）：必须剔除，不能覆盖 C 的 success
    o2 = nfs / "official" / "O2" / "smvla" / "s0" / "episodes-shard00of01.jsonl"
    with open(o2, "a") as fh:
        fh.write(json.dumps(dict(_smvla("C", 11, 300, "error", steps=0), error={"msg": VK_ERR})) + "\n")
    doc = _run(tmp_path, art, nfs, e0, "--partial")
    errs = [e["line"] for e in doc["entries"] if e["status"] == "ERROR"]
    assert not errs, errs
    o2m = [json.loads(l) for l in (tmp_path / "out" / "merged" / "O2-smvla-official.jsonl").read_text().splitlines()]
    assert len(o2m) == 3 and all(r["status"] != "error" for r in o2m)
    assert any(e["name"] == "INFRA" and "cond=O2 " in e["line"] and "n=1" in e["line"] and "incident=1" in e["line"] for e in doc["entries"])
    pm = [e for e in doc["entries"] if e["name"] == "PROD_MERGE" and "policy=smvla" in e["line"]][0]
    # 已有 results.jsonl 里 N 的 A、B（fail）；C 只在 N2
    assert "from_N=2" in pm["line"] and "from_N2=1" in pm["line"] and "poisoned_replaced=1" in pm["line"], pm["line"]
    assert "still_missing=0" in pm["line"] and "conflicts=0" in pm["line"]
    assert (tmp_path / "out" / "merged" / "NP-smvla.jsonl").read_text().count("\n") == 3
    q = [e for e in doc["entries"] if e["name"] == "QUEUE_CLAIM" and "queue=prod " in e["line"]][0]
    assert "infra_terminal=2" in q["line"]
    ra = [e for e in doc["entries"] if e["name"] == "RELATIVE_ACCEPT" and "policy=smvla" in e["line"]][0]
    assert ra["status"] == "INFO" and "partial" not in ra["line"], ra["line"]
    # infra 永不算结果：E5 用正常目录，A=success
    e5 = json.loads((tmp_path / "out" / "merged" / "E5-smvla.jsonl").read_text().splitlines()[0])
    assert e5["status"] == "success"
    inf = [e for e in doc["entries"] if e["name"] == "INFRA" and "cond=N " in e["line"] and "seat=new4" in e["line"]][0]
    assert "n=2" in inf["line"] and "zero_step=2" in inf["line"] and "incident=2" in inf["line"]
    assert "env_build|RuntimeError:vk::PhysicalDevice::createDeviceUnique" in inf["line"]
    inc = [e for e in doc["entries"] if e["name"] == "INCIDENT" and "vulkanfail" in e["line"]][0]
    assert "records=3" in inc["line"] and "real=1" in inc["line"] and "infra=2" in inc["line"] and "compared=excluded" in inc["line"]
    assert any(e["name"] == "INCIDENT" and "queue=prod" in e["line"] and "infra_terminal=2" in e["line"] and "replaced=1" in e["line"]
               for e in doc["entries"])
    tot = [e for e in doc["entries"] if e["line"].startswith("BUDGET_TOTAL")][0]
    assert "incident_infra_attempts=5" in tot["line"] and "retry_over_items=none" in tot["line"], tot["line"]  # 队列 2 + 官方 1 + 留档目录 2
    assert any(e["line"].startswith("BUDGET=INFO item=incident_infra_attempts attempts=0 unique=0 incident=5") for e in doc["entries"])


def _fake_rec(d: Path, task: str, seed: int, steps: int, created: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"task": task, "seed": seed, "created": created}))
    (d / "frames-front.jsonl").write_text("")
    (d / "summary.json").write_text(json.dumps({"summary": {"steps": steps}}))
    return d


def test_pick_rec_skips_incident_and_matches_steps(tmp_path):
    root = tmp_path / "E7" / "mme"
    good = _fake_rec(root / "s-ding" / "mme" / "rec" / "A_100", "A", 100, 50, "2026-09-30T06:00")
    _fake_rec(root / "s-ding-vulkanfail-0540" / "mme" / "rec" / "A_100", "A", 100, 50, "2026-09-30T09:00")
    _fake_rec(root / "s-ding2" / "mme" / "rec" / "A_100", "A", 100, 7, "2026-09-30T08:00")
    idx = s6.build_rec_index([root])
    assert all("vulkanfail" not in str(c) for c in idx[("A", 100)])
    assert s6.pick_rec(idx[("A", 100)], 50) == good          # 步数相符优先
    assert s6.pick_rec(idx[("A", 100)], None).name == "A_100" and "s-ding2" in str(s6.pick_rec(idx[("A", 100)], None))  # 否则取最新


def test_incident_signatures_and_rec_remap_and_n3(tmp_path):
    assert s6.is_incident_record({"status": "error", "steps": 0, "error": "websockets ConnectionRefusedError"})
    assert s6.is_incident_record({"status": "error", "steps": 0, "error": "CUDA Out Of Memory"})
    assert not s6.is_incident_record({"status": "error", "steps": 12, "error": "vulkan"})
    assert not s6.is_incident_record({"status": "fail", "steps": 0, "error": "vulkan"})
    assert s6.infra_signature({"error": "svulkan2 EXCLUSIVE"}) == "svulkan2"
    art, nfs, e0 = _layout(tmp_path, n_complete=False, with_rec=False)
    # N 的 C 被毒化；N3 补上；N 的 A 记录 rec_dir 指向失效的节点 /tmp，应重映射到 results.jsonl 旁 rec/<同名>
    seat = art / "official-rec" / "N" / "smvla" / "s-new9" / "smvla"
    _fake_rec(seat / "rec" / "A_100", "A", 100, 100, "x")
    _w(seat / "results.jsonl", [_new("A", 3, 100, "success", "N", seat="new9", rec_dir="/tmp/v75-N-new9/smvla/rec/A_100"),
                                _new("C", 11, 300, "error", "N", seat="new9", steps=0, infra=True, infra_reason="env_build", error=VK_ERR)])
    _w(art / "official-rec" / "N3" / "smvla" / "s-new3" / "smvla" / "results.jsonl", [_new("C", 11, 300, "success", "N3", seat="new3")])
    doc = _run(tmp_path, art, nfs, e0, "--partial")
    assert not [e for e in doc["entries"] if e["status"] == "ERROR"]
    pm = [e for e in doc["entries"] if e["name"] == "PROD_MERGE" and "policy=smvla" in e["line"]][0]
    assert "from_N3=1" in pm["line"] and "poisoned_replaced=1" in pm["line"] and "still_missing=0" in pm["line"], pm["line"]
    n = {(r["task"], r["seed"]): r for r in map(json.loads, (tmp_path / "out" / "merged" / "N-smvla.jsonl").read_text().splitlines())}
    assert any(r["rec_dir"] == str(seat / "rec" / "A_100") for r in n.values())
    assert all(r["rec_dir"] for r in n.values())  # 找不到录制的写 MISSING 占位，不回退目录索引
    ep = [e for e in doc["entries"] if e["name"] == "ENV_DIGEST_PARITY" and "pair=C1:C2" in e["line"]][0]
    assert "name_only=0" in ep["line"] and "key_set_diff=0" in ep["line"]
    b = [e for e in doc["entries"] if e["line"].startswith("BUDGET=INFO item=5.2_正式跑法")][0]
    assert "incident=1" in b["line"] and "retry_over=no" in b["line"], b["line"]


def test_budget_retry_over_counts_incidents(tmp_path):
    art, nfs, e0 = _layout(tmp_path, n_complete=True, with_rec=False)
    vk = [_new("A", 3, 100, "error", "E1", steps=0, infra=True, infra_reason="env_build", error=VK_ERR, claim_token=f"t{i}")
          for i in range(13)]
    _w(art / "official-rec" / "E1" / "smvla" / "s-x-vulkanfail-0100" / "smvla" / "results.jsonl",
       vk + [_new("B", 7, 200, "fail", "E1", seat="x")])
    doc = _run(tmp_path, art, nfs, e0)
    b = [e for e in doc["entries"] if e["line"].startswith("BUDGET=INFO item=5.1_换条件评估")][0]
    assert "attempts=5" in b["line"] and "incident=13" in b["line"] and "retry_over=yes" in b["line"], b["line"]
    tot = [e for e in doc["entries"] if e["line"].startswith("BUDGET_TOTAL")][0]
    assert "retry_over_items=5.1_换条件评估" in tot["line"], tot["line"]


def test_stack_mad_none_when_counts_differ(tmp_path):
    art, nfs, e0 = _layout(tmp_path, with_rec=False)
    rroot = nfs / "stage" / "R1smoke" / "smvla" / "s0" / "rec"
    _official_rec(rroot, "A", 3, 100)
    # B：官方多录了一帧（4 帧 vs 新 3 帧）
    R = s6.rec_mod()
    rec = R.EpisodeRecorder(rroot / "B_7_200", {"task": "B", "seed": 200, "never_degrade": True}, encode_async=False,
                            free_gib_fn=lambda _p: 10000.0)
    rec.set_phase("reset")
    fr = np.concatenate([_frames(200, 2), _frames(999, 1), _frames(201, 1)])
    fi = rec.add_frames("front", fr, tag="reset")
    wi = rec.add_frames("wrist", fr, tag="reset")
    rec.add_array("reset_state", np.zeros((4, 8), np.float32))
    rec.add_event({"kind": "reset", "ok": True, "front_idx": [fi[0], fi[-1]], "wrist_idx": [wi[0], wi[-1]]})
    rec.set_phase("run")
    rec.close({})
    doc = _run(tmp_path, art, nfs, e0, "--sections", "env_stack")
    det = json.loads((tmp_path / "out" / "detail" / "env-stack-R1-C1-smvla.json").read_text())["per_identity"]["B/200"]
    assert det["front"]["count_equal"] is False and det["front"]["mad_max"] is None and det["front"]["init_mad"] == 0.0
    st = [e for e in doc["entries"] if e["name"] == "ENV_STACK" and "src=R1" in e["line"] and "smvla" in e["line"]][0]
    assert "demo_count_equal=1/2" in st["line"]


def test_canary_reruns_and_killtest(tmp_path):
    art, nfs, e0 = _layout(tmp_path, with_rec=False)
    # N 里 jia 的金丝雀已有；ding 只有 infra 金丝雀，后由 C 补跑成功；K 的金丝雀被杀 → infra；K 的队列局不能进 PROD
    _w(art / "official-rec" / "N" / "smvla" / "s-ding" / "smvla" / "results.jsonl",
       [_new("B", 7, 200, "error", "N", seat="ding", canary=True, infra=True, infra_reason="env_build", steps=0, error=VK_ERR)])
    _w(art / "official-rec" / "C" / "smvla" / "s-ding" / "smvla" / "results.jsonl", [_new("B", 7, 200, "fail", "C", seat="ding", canary=True)])
    _w(art / "official-rec" / "K" / "smvla" / "s-new1" / "smvla" / "results.jsonl",
       [_new("A", 3, 100, "error", "K", seat="new1", canary=True, infra=True, infra_reason="ConnectionClosed", steps=16),
        _new("C", 11, 300, "fail", "K", seat="new1", claim_token="k1")])
    log = nfs / "state" / "main" / "logs" / "N-smvla-s-new1.log"
    log.parent.mkdir(parents=True)
    log.write_text("SERVER_START policy=smvla\nSERVER_READY ready_s=1\nSERVER_KILLED_FOR_TEST\nSERVER_DIED pid=1\n"
                   "SERVER_START policy=smvla\nSERVER_READY ready_s=2\nQUEUE_CLAIM=PASS dup=0 missing=0 requeued=4 done=192 total=192\n"
                   "SEAT_DONE policy=smvla cond=N seat=new1 done=46 errors=0 infra=3 queue_check=PASS\n")
    doc = _run(tmp_path, art, nfs, e0)
    assert not [e for e in doc["entries"] if e["status"] == "ERROR"]
    can = [e for e in doc["entries"] if e["name"] == "CANARY" and "policy=smvla" in e["line"]][0]
    assert "from=ding:C,jia:N" in can["line"] and "seats_missing_real=new1,new2" in can["line"], can["line"]
    ci = [e for e in doc["entries"] if e["name"] == "CANARY_INFRA" and "policy=smvla" in e["line"]][0]
    assert "n=2" in ci["line"] and "new1:K:A/100:ConnectionClosed" in ci["line"]
    pvo = [e for e in doc["entries"] if e["name"] == "PROD_VS_OFFICIAL" and "ref=历史" in e["line"]][0]
    assert "s2f=0" in pvo["line"] and "f2s=0" in pvo["line"]  # K 的 C=fail 没进正式跑法
    kt = [e for e in doc["entries"] if e["name"] == "KILLTEST" and "policy=smvla" in e["line"]][0]
    assert "server_killed=yes server_restarted=yes requeued=4 done=46 errors=0" in kt["line"], kt["line"]
    assert any(e["name"] == "KILLTEST" and e["status"] == "PENDING" and "policy=mme" in e["line"] for e in doc["entries"])
    b = [e for e in doc["entries"] if e["line"].startswith("BUDGET=INFO item=5.2_金丝雀")][0]
    assert "attempts=4" in b["line"] and "unique=3" in b["line"], b["line"]
    assert any(e["line"].startswith("BUDGET=INFO item=其他_杀server测试 attempts=1") for e in doc["entries"])
