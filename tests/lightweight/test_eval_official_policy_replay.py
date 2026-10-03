"""scripts/eval-official/policy_replay.py 的轻量测试（纯 CPU；假轨迹 + 本地假 websocket server，不起 GPU）。"""

from __future__ import annotations

import importlib.util
import json
import threading
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("v75_policy_replay_t", REPO_ROOT / "scripts" / "eval-official" / "policy_replay.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

pytest.importorskip("openpi_client")
pytest.importorskip("websockets")


# ─────────────────────────── 合成轨迹


def make_trace(policy: str, *, demo: int = 2, n_steps: int = 37, end_status: str = "success", n_model: int = 10,
               seed: int = 0, h: int = 20) -> dict:
    rng = np.random.default_rng(seed)
    img = lambda: rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)  # noqa: E731
    reset = {"front": [img() for _ in range(demo + 1)], "wrist": [img() for _ in range(demo + 1)],
             "joint": [rng.normal(size=7).astype(np.float32) for _ in range(demo + 1)],
             "gripper": [rng.normal(size=2).astype(np.float32) for _ in range(demo + 1)]}
    steps = []
    for k in range(n_steps):
        last = k == n_steps - 1
        steps.append(pr._step_rec([img()], [img()], rng.normal(size=7).astype(np.float32),
                                  rng.normal(size=2).astype(np.float32), terminated=last,
                                  status=end_status if last else "ongoing"))
    model = [rng.normal(size=(h if policy == "mme" else 30, 8)).astype(np.float64 if policy == "mme" else np.float32)
             for _ in range(n_model)]
    return {"policy": policy, "kind": "new", "rec": "synthetic",
            "identity": {"task": "PickXtimes", "source_episode": 3, "seed": 510300}, "goal": "do it",
            "reset": reset, "steps": steps, "model_actions": model, "exec_rows": [], "wire_sha": None,
            "wire_basis": "none", "final": {"status": end_status, "steps": n_steps}}


def _independent_mme(trace):
    """不经 policy_replay 的假客户端，直接用 mme_client.evaluate_one 走一遍并逐条打包（对照组）。"""
    mc = pr.load_module("mme_client")
    from openpi_client import msgpack_numpy

    env = pr.FakeEnv(trace)
    sent = []
    model = list(trace["model_actions"])

    class C:
        def __init__(self):
            self.p = msgpack_numpy.Packer()
            self._ws = self

        def close(self):
            pass

        def reset(self):
            sent.append(self.p.pack({"reset": True}))
            return {"reset_finished": True}

        def add_buffer(self, b):
            sent.append(self.p.pack(b))
            return {"add_buffer_finished": True}

        def infer(self, o):
            sent.append(self.p.pack(o))
            return {"actions": model.pop(0)}

    def reset_fn():
        obs, info = env.reset()
        return mc.pre_traj_from_reset(obs, info)

    res = mc.evaluate_one(C, env.step, reset_fn)
    return sent, env.exec_rows, res


def test_simulate_mme_equals_client_bytes():
    t = make_trace("mme", demo=2, n_steps=37)
    sim = pr.simulate(t)
    sent, rows, res = _independent_mme(t)
    assert [m["raw"] for m in sim["msgs"]] == sent
    assert sim["status"] == res["status"] == "success" and sim["steps"] == res["steps"] == 37
    assert [m["kind"] for m in sim["msgs"]][:3] == ["reset", "add_buffer", "infer"]
    assert sum(m["kind"] == "infer" for m in sim["msgs"]) == 3  # ceil(37/16)
    t["exec_rows"] = rows
    ex = pr.exec_compare(sim["exec_rows"], t["exec_rows"], sim, t["final"])
    assert ex["exec_equal"] and ex["count_sim"] == 37


def test_wire_mismatch_and_exhausted():
    t = make_trace("mme", n_steps=20)
    sim = pr.simulate(t)
    good = [pr.sha_bytes(m["raw"]) for m in sim["msgs"]]
    assert pr.wire_mismatch(sim["msgs"], good) == (0, None)
    bad = list(good)
    bad[3] = "0" * 64
    assert pr.wire_mismatch(sim["msgs"], bad) == (1, 3)
    assert pr.wire_mismatch(sim["msgs"], good[:-1])[0] == 1
    # 录下的环境步不够：新客户端逻辑要多走 → exhausted
    t2 = make_trace("mme", n_steps=20, end_status="ongoing")
    t2["steps"][-1]["terminated"] = False
    assert pr.simulate(t2)["exhausted"]
    # 模型输出不够
    t3 = make_trace("mme", n_steps=40, n_model=1)
    assert pr.simulate(t3)["exhausted"]


def test_simulate_smvla_terminal_and_exec():
    t = make_trace("smvla", demo=1, n_steps=35)
    sim = pr.simulate(t)
    kinds = [m["kind"] for m in sim["msgs"]]
    assert kinds[:3] == ["reset", "observe", "infer"]
    assert kinds.count("infer") == 3 and kinds.count("observe") == 4
    assert sim["status"] == "success" and sim["steps"] == 35
    # 执行动作 = 模型输出前 16 行逐行 float64[:8]
    exp = [np.asarray(r, np.float64).reshape(-1)[:8] for a in t["model_actions"][:3] for r in a[:16]][:35]
    assert len(sim["exec_rows"]) == 35
    assert all(np.array_equal(x, y) and x.dtype == np.float64 for x, y in zip(sim["exec_rows"], exp))
    # 第一条 observe 的帧 = reset 全部帧
    obj = pr.unpackb(sim["msgs"][1]["raw"])
    assert len(obj["observe"]["frames"]) == 2


# ─────────────────────────── 新旧打包（旧源码用 ast 取函数，不执行模块其余部分）


OLD_UTILS = '''import cv2  # 不应被执行
import numpy as np

def pack_buffer(image_buffer, state_buffer, exec_start_idx=0):
    image_output = np.stack(image_buffer, axis=0).astype(np.uint8)[:, None]
    state_output = np.stack(state_buffer, axis=0).astype(np.float32)
    return {
        "images": image_output,
        "state": state_output,
        "add_buffer": True,
        "exec_start_idx": exec_start_idx,
    }
'''
OLD_RUNNER = '''from robomme.robomme_env import *  # 不应被执行
import numpy as np

def pack_state(joint_state, gripper_state):
    return np.concatenate([joint_state, gripper_state[:1]], axis=0, dtype=np.float32)
'''


def test_old_mme_module_payload_equal(tmp_path):
    (tmp_path / "utils.py").write_text(OLD_UTILS)
    (tmp_path / "env_runner.py").write_text(OLD_RUNNER)
    mod, shas = pr.old_mme_module(tmp_path)
    t = make_trace("mme", n_steps=30)
    a = [m["raw"] for m in pr.simulate(t)["msgs"]]
    b = [m["raw"] for m in pr.simulate(t, mod=mod)["msgs"]]
    assert a == b and set(shas) == {"utils.py", "env_runner.py"}
    # 旧打包若把状态存成 float64，字节必然不同（检出力）
    (tmp_path / "utils.py").write_text(OLD_UTILS.replace("astype(np.float32)", "astype(np.float64)"))
    mod2, _ = pr.old_mme_module(tmp_path)
    c = [m["raw"] for m in pr.simulate(t, mod=mod2)["msgs"]]
    assert c != a


def test_old_smvla_module_model_inputs_equal():
    src = REPO_ROOT / "scripts" / "eval-official" / "smvla_client.py"  # 其中五个函数逐行照抄旧 robomme_env.py
    mod, _ = pr.old_smvla_module(src)
    t = make_trace("smvla", n_steps=20)
    new = pr.simulate(t, keep_objects=True)
    old = pr.simulate(t, mod=mod, keep_objects=True)
    a = pr.smvla_model_inputs(new["msgs"], via_wire=True)
    b = pr.smvla_model_inputs(old["msgs"], via_wire=False)
    assert a == b and any(x.startswith("infer:") for x in a)


# ─────────────────────────── 假 server 回放


def _serve(handler):
    from websockets.sync.server import serve

    srv = serve(handler, "127.0.0.1", 0, compression=None, max_size=None)
    port = srv.socket.getsockname()[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, port


def _mme_handler(noise: bool, with_infer_ms: bool = True):
    from openpi_client import msgpack_numpy

    counter = {"n": 0}

    def handler(ws):
        p = msgpack_numpy.Packer()
        ws.send(p.pack({"fake": "mme"}))
        counter["n"] += 1
        conn = counter["n"]
        for raw in ws:
            obj = msgpack_numpy.unpackb(raw)
            if obj.get("reset"):
                ws.send(p.pack({"reset_finished": True, "reset_time_ms": 1.0}))
            elif obj.get("add_buffer"):
                ws.send(p.pack({"add_buffer_finished": True, "add_buffer_time_ms": 1.0}))
            else:
                s = np.asarray(obj["observation/state"], np.float64)
                a = np.tile(s, (20, 1)) + (1e-3 * conn if noise else 0.0)
                ws.send(p.pack({"actions": a, "infer_time_ms": 5.0} if with_infer_ms else {"actions": a}))

    return handler


def _smvla_handler():
    from openpi_client import msgpack_numpy

    def handler(ws):
        p = msgpack_numpy.Packer()
        ws.send(p.pack({"det": False}))
        for raw in ws:
            obj = msgpack_numpy.unpackb(raw)
            rep = {"req_sha": pr.sha_bytes(raw)}
            if "reset" in obj:
                rep.update(reset_finished=True, rng_matches_ref=True, rng={"x": "y"})
            elif "observe" in obj:
                rep.update(observe_finished=True, n=len(obj["observe"]["frames"]))
            else:
                s = np.asarray(obj["infer"]["state"], np.float32)
                rep.update(actions_full=np.tile(s, (30, 1)), actions=np.tile(s, (16, 1)), infer_ms=7.0, subtask="x")
            ws.send(p.pack(rep))

    return handler


@pytest.mark.parametrize("policy", ["mme", "smvla"])
def test_replay_same_server_bitwise(tmp_path, policy, capsys):
    t = make_trace(policy, n_steps=40)
    sim = pr.simulate(t)
    inp = tmp_path / "in"
    pr.write_inputs(inp, t, sim, {})
    srv, port = _serve(_mme_handler(False) if policy == "mme" else _smvla_handler())
    try:
        rc = pr.main(["replay", "--policy", policy, "--inputs", str(inp), "--port", str(port), "--repeats", "2",
                      "--tag", "det-off/same/A", "--out", str(tmp_path / "out")])
    finally:
        srv.shutdown()
    assert rc == 0
    rep0 = tmp_path / "out" / "det-off" / "same" / "A" / "rep0"
    tm = json.loads((rep0 / "timing.json").read_text())
    assert tm["infers"] == 3 and tm["rng_restored"] is True and tm["protocol_bad"] == 0
    x = pr._load_actions(rep0)
    assert x.shape == ((3, 20, 8) if policy == "mme" else (3, 30, 8))
    pr.main(["compare", "--a", str(rep0), "--b", str(rep0.parent / "rep1"), "--cond", "L1", "--policy", policy,
             "--mode", "same", "--det", "off", "--out", str(tmp_path / "out" / "compare" / "x.json")])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("POLICY_REPLAY=INFO cond=L1") and "bitwise=yes" in line and "neq=0" in line


def test_replay_noisy_server_detects_diff(tmp_path):
    t = make_trace("mme", n_steps=40)
    inp = tmp_path / "in"
    pr.write_inputs(inp, t, pr.simulate(t), {})
    srv, port = _serve(_mme_handler(True))
    try:
        pr.main(["replay", "--policy", "mme", "--inputs", str(inp), "--port", str(port), "--repeats", "2",
                 "--tag", "g", "--out", str(tmp_path / "out")])
    finally:
        srv.shutdown()
    r = pr.compare_dirs(tmp_path / "out" / "g" / "rep0", tmp_path / "out" / "g" / "rep1")
    assert not r["bitwise"] and r["first_diff_step"] == 0 and r["neq"] == 3 * 20 * 8
    assert r["max_abs"] == pytest.approx(1e-3)


def test_read_inputs_detects_corruption(tmp_path):
    t = make_trace("mme", n_steps=20)
    pr.write_inputs(tmp_path, t, pr.simulate(t), {})
    b = bytearray((tmp_path / "messages.bin").read_bytes())
    b[-1] ^= 1
    (tmp_path / "messages.bin").write_bytes(bytes(b))
    with pytest.raises(RuntimeError):
        pr.read_inputs(tmp_path)


# ─────────────────────────── 确定性标志默认值规则与汇总


def test_det_rule():
    assert pr.det_rule([True, True], 100.0, 109.0)["default"] == "on"
    assert pr.det_rule([True, True], 100.0, 111.0)["default"] == "off"
    assert pr.det_rule([True, False], 100.0, 100.0)["default"] == "off"
    assert pr.det_rule([], 100.0, 100.0)["default"] == "off"
    assert pr.det_rule([True], None, 100.0)["default"] == "off"


def test_report(tmp_path, capsys):
    root = tmp_path
    for det, ms in (("off", 100.0), ("on", 105.0)):
        d = root / f"det-{det}" / "same" / "A" / "rep0"
        d.mkdir(parents=True)
        (d / "timing.json").write_text(json.dumps({"server_ms": [900.0, 200.0, 150.0] + [ms] * 10, "rng_restored": True}))
        # 编译缓存那几次不计入测速
        c = root / f"det-{det}" / "cache-cold" / "A" / "rep0"
        c.mkdir(parents=True)
        (c / "timing.json").write_text(json.dumps({"server_ms": [1.0] * 20, "rng_restored": True}))
    (root / "compare").mkdir()
    (root / "compare" / "a.json").write_text(json.dumps({"det": "on", "mode": "same", "bitwise": True}))
    (root / "compare" / "b.json").write_text(json.dumps({"det": "on", "mode": "restart", "bitwise": True}))
    (root / "compare" / "c.json").write_text(json.dumps({"det": "off", "mode": "same", "bitwise": False}))
    pr.main(["report", "--root", str(root), "--cond", "L1", "--policy", "mme"])
    out = capsys.readouterr().out
    assert "DET_RULE=INFO policy=mme det_bitwise=yes slowdown_pct=5.00 default=on" in out
    assert "POLICY_REPLAY_DONE cond=L1 policy=mme" in out
    rep = json.loads((root / "report.json").read_text())
    assert rep["rng_restored_all"] is True


# ─────────────────────────── 复审修正：测速口径、run_id、预热随机状态、GPU 占用、脚本环境


def test_mme_reply_without_infer_ms_uses_rtt(tmp_path, capsys):
    t = make_trace("mme", n_steps=100)  # 7 次推理：跳过前 3 次后仍有稳态样本
    inp = tmp_path / "in"
    pr.write_inputs(inp, t, pr.simulate(t), {})
    srv, port = _serve(_mme_handler(False, with_infer_ms=False))
    try:
        for det in ("off", "on"):
            assert pr.main(["replay", "--policy", "mme", "--inputs", str(inp), "--port", str(port), "--repeats", "1",
                            "--tag", f"det-{det}/same/A", "--out", str(tmp_path), "--run-id", "R1"]) == 0
    finally:
        srv.shutdown()
    tm = json.loads((tmp_path / "det-off" / "same" / "A" / "rep0" / "timing.json").read_text())
    assert tm["timing_basis"] == "rtt_ms" and tm["run_id"] == "R1"
    assert all(x != x for x in tm["server_ms"])  # server 没回耗时 → NaN
    assert len(tm["det_ms"]) == 7 and all(x == x and x > 0 for x in tm["det_ms"])
    (tmp_path / "compare").mkdir()
    (tmp_path / "compare" / "a.json").write_text(json.dumps({"det": "on", "mode": "same", "bitwise": True, "run_id": "R1"}))
    pr.main(["report", "--root", str(tmp_path), "--cond", "L1", "--policy", "mme", "--run-id", "R1"])
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if l.startswith("DET_RULE=INFO")][0]
    assert "slowdown_pct=n/a" not in line and "infer_ms_off=None" not in line and "basis=rtt_ms" in line


def test_timing_basis():
    assert pr.timing_basis("mme", [5.0, 5.0], [7.0, 8.0]) == ("rtt_ms", [7.0, 8.0])
    assert pr.timing_basis("smvla", [5.0, 6.0], [7.0, 8.0]) == ("server_infer_ms", [5.0, 6.0])
    assert pr.timing_basis("smvla", [float("nan")], [7.0]) == ("rtt_ms", [7.0])
    assert pr.server_infer_ms({"server_timing": {"infer_ms": 3}}) == 3.0
    assert pr.server_infer_ms({"actions": 1}) != pr.server_infer_ms({"actions": 1})  # NaN


def test_report_filters_run_id_and_records_warmup_busy(tmp_path, capsys):
    root = tmp_path
    for rid, bit in (("OLD", False), ("NEW", True)):
        d = root / "det-on" / "same" / "A" / f"rep{rid}"
        d.mkdir(parents=True)
        (d / "timing.json").write_text(json.dumps({"det_ms": [1.0] * 10, "timing_basis": "rtt_ms", "rng_restored": bit,
                                                   "run_id": rid}))
        (root / "compare").mkdir(exist_ok=True)
        (root / "compare" / f"{rid}.json").write_text(json.dumps({"det": "on", "mode": "same", "bitwise": bit, "run_id": rid}))
    (root / "server-logs").mkdir()
    (root / "server-logs" / "metadata-detoff-same-NEW.json").write_text(
        json.dumps({"det": False, "warmup": {"rng_restored": True, "rng_consumed_by_warmup": True}}))
    (root / "server-logs" / "metadata-detoff-same-OLD.json").write_text(json.dumps({"warmup": {"rng_restored": False}}))
    (root / "gpu-busy.jsonl").write_text(json.dumps({"run_id": "NEW", "foreign": "123:500"}) + "\n"
                                         + json.dumps({"run_id": "OLD", "foreign": "9:1"}) + "\n")
    pr.main(["report", "--root", str(root), "--cond", "L1", "--policy", "smvla", "--run-id", "NEW"])
    rep = json.loads((root / "report.json").read_text())
    assert len(rep["comparisons"]) == 1 and rep["det_rule"]["det_bitwise"] is True
    assert rep["rng_restored_all"] is True and rep["smvla_warmup_rng_all"] is True
    assert rep["gpu_busy_events"] == 1 and rep["gpu_busy"][0]["foreign"] == "123:500"
    assert "gpu_busy_events=1" in capsys.readouterr().out


EVAL_DIR = REPO_ROOT / "scripts" / "eval-official"


@pytest.mark.parametrize("script", ["run_seat.sh", "run_policy_replay.sh"])
def test_server_branches_clean_env_and_smvla_det(script):
    s = (EVAL_DIR / script).read_text()
    for v in ("XLA_FLAGS", "JAX_COMPILATION_CACHE_DIR", "JAX_PERSISTENT_CACHE_MIN_ENTRY_SIZE_BYTES",
              "JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS", "CUBLAS_WORKSPACE_CONFIG"):
        assert f"-u {v}" in s
    assert s.count('exec setsid env "${CLEAN_ENV[@]}" "${NOPROXY_ENV[@]}"') == 2  # MME 与 SMVLA 两个 server 分支
    assert 'detarg=(--det) && extra=(CUBLAS_WORKSPACE_CONFIG=:4096:8)' in s
    assert '"${detarg[@]}"' in s


def test_driver_lock_busy_and_run_id():
    s = (EVAL_DIR / "run_policy_replay.sh").read_text()
    assert "SLURM_JOB_ID" in s and "gpu$GPU.lock" in s and "flock 9" in s
    assert "WARN_GPU_BUSY" in s and "--query-compute-apps=pid,used_memory" in s
    assert 'rm -rf "$OUT/compare" "$OUT"/det-*' in s
    assert s.count('--run-id "$RUN_ID"') >= 3


# ─────────────────────────── 官方 MME 多局分片：代理根目录下多条连接，按 sha 序列匹配本局


def _write_official_mme_episode(ep_dir: Path, trace: dict) -> list[str]:
    """按 mme_client_wrap 钩子的布局写一局官方录制（EpisodeRecorder 真编码帧）；返回本局发出 sha 序列。"""
    R = pr.load_module("recorder")
    sim = pr.simulate(trace)
    rec = R.EpisodeRecorder(ep_dir, {"policy": "mme", "side": "official-observer", "task": "BinFill",
                                     "source_episode": 31, "seed": 543100, "never_degrade": True})
    rec.set_phase("reset")
    r = trace["reset"]
    fi = rec.add_frames("front", np.stack(r["front"]), tag="reset")
    wi = rec.add_frames("wrist", np.stack(r["wrist"]), tag="reset")
    st = np.stack([np.concatenate([j, g[:1]]).astype(np.float32) for j, g in zip(r["joint"], r["gripper"])])
    rec.add_array("reset_state", st)
    rec.add_event({"kind": "reset", "task_goal": trace["goal"], "front_idx": [fi[0], fi[-1]], "wrist_idx": [wi[0], wi[-1]]})
    rec.set_phase("run")
    shas = [pr.sha_bytes(m["raw"]) for m in sim["msgs"]]
    for i, s in enumerate(shas):
        rec.add_event({"kind": "ws", "conn": 0, "dir": "send", "idx": i, "sha256": s})
    for k, a in enumerate(sim["exec_rows"]):
        s = trace["steps"][k]
        rec.add_array("exec_action", a, step=k)
        f = rec.add_frames("front", s["front"][0], tag="step")[0]
        w = rec.add_frames("wrist", s["wrist"][0], tag="step")[0]
        rec.add_array("state", np.concatenate([s["joint"], s["gripper"][:1]]).astype(np.float32), step=k)
        rec.add_event({"kind": "step", "k": k, "stop": s["terminated"], "status": s["status"], "front_idx": f, "wrist_idx": w})
    assert rec.close({"return": sim["status"], "steps": sim["steps"]})["RECORDER_VERIFY"] == "PASS"
    return shas


def _write_proxy_conn(d: Path, shas: list[str], actions: list[np.ndarray]) -> None:
    """按 mme_proxy 记账布局写一条连接目录（只有 events 与 arrays）。"""
    d.mkdir(parents=True)
    ev = [{"kind": "msg", "dir": "c2s", "idx": i, "sha256": s, "seq": i} for i, s in enumerate(shas)]
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    keys = {f"s2c.actions__{k:05d}": np.asarray(a) for k, a in enumerate(actions)}
    np.savez(d / "arrays.npz", **keys)
    (d / "arrays-index.jsonl").write_text("".join(
        json.dumps({"key": k, "name": "s2c.actions", "k": i, "step": 3 + 2 * i}) + "\n" for i, k in enumerate(keys)))


def test_official_mme_multi_episode_proxy_root(tmp_path, capsys):
    R = pr.load_module("recorder")
    try:
        R.find_ffmpeg()
    except Exception:
        pytest.skip("无 ffmpeg")
    root = tmp_path / "rec"
    t_other = make_trace("mme", n_steps=30, seed=1)
    t_me = make_trace("mme", n_steps=40, seed=2, end_status="fail")
    shas = _write_official_mme_episode(root / "BinFill_31_543100", t_me)
    other = [pr.sha_bytes(m["raw"]) for m in pr.simulate(t_other)["msgs"]]
    px = root / "proxy"
    _write_proxy_conn(px / "conn-111-0000", [], [])  # 观察器预检连接：无消息
    _write_proxy_conn(px / "conn-111-0001", other, t_other["model_actions"])  # 别的局
    _write_proxy_conn(px / "conn-111-0002", shas[:3], t_me["model_actions"][:1])  # 同局前缀（被截断的重试连接）
    _write_proxy_conn(px / "conn-111-0003", shas, t_me["model_actions"])  # 本局
    _write_proxy_conn(px / "conn-111-0004", other, t_other["model_actions"])
    out = tmp_path / "B-mme"
    rc = pr.main(["build-inputs", "--policy", "mme", "--rec", str(root / "BinFill_31_543100"), "--proxy-rec", str(px),
                  "--kind", "official", "--out", str(out)])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 0 and line.startswith("BUILD_INPUTS=PASS") and "mismatch=0" in line and "exec_equal=True" in line
    assert json.loads((out / "meta.json").read_text())["proxy_rec"].endswith("conn-111-0003")
    # 不给 --proxy-rec：在 <rec>/../proxy 自动匹配
    assert pr.main(["build-inputs", "--policy", "mme", "--rec", str(root / "BinFill_31_543100"), "--kind", "official",
                    "--out", str(tmp_path / "auto")]) == 0
    # 显式给错单个连接目录：报错，不静默产出
    with pytest.raises(RuntimeError):
        pr.load_trace("mme", root / "BinFill_31_543100", "official", str(px / "conn-111-0001"))
    # iface-open 同样能用代理根目录
    old = tmp_path / "old"
    old.mkdir()
    (old / "utils.py").write_text(OLD_UTILS)
    (old / "env_runner.py").write_text(OLD_RUNNER)
    capsys.readouterr()
    pr.main(["iface-open", "--policy", "mme", "--rec-official", str(root / "BinFill_31_543100"), "--proxy-rec", str(px),
             "--old-src", str(old), "--out", str(tmp_path / "i.json")])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert "payload_equal=yes" in line and "exec_equal=yes" in line and "wire_mismatch=0" in line
