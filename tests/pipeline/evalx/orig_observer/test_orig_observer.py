"""S7 原侧只读观测器（1005-eval-video-phase2-all-models-rerun-plan.md 第二部分一节 S7）。

全部用 CPU 替身：假 ``InProcSimPool``／``BatchedEvalPolicy``（按原版 ``SimEnvService.step`` 语义逐行执行、``consumed``
截取）、假 ``EnvRunner``（照原版返回 ``((img, wrist, state), stop, status)``，环境异常返回 ``(None, None, None)``）、
假 websocket 连接与策略客户端；局循环照原版 ``run_group``／``eval_each_episode`` 的控制流手写。

覆盖：钩子不改返回值；写出的 trace 与 ``arrays.npz`` 过 ``trace_contract.contract_problems``／``assert_renderable`` 与
``gate2_compare`` 的 ``TraceIndex``／``compare_traces`` 读取；float64 精度、部分动作块、错误后成功、孤儿目录、
重复终态、续跑；钩子异常不外抛但 ``observer_hook_errors`` 递增；透明性对账的清单覆盖与日志封口；
``OBSERVER_COMPLETE`` 在对账 FAIL／检查器崩溃／缺报告／封口超时时判 FAIL 而评估退出码不变；启动器在提交不符或
工作树脏时 ``RUN_BLOCKED``；预算预约失败 ``RUN_BLOCKED reason=budget``。
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
import types
from pathlib import Path

import numpy as np
import pytest

from tests._support.loaders import REPO, load_script
from tests.pipeline.evalx.report import trace_contract as tc

OBS = REPO / "scripts" / "eval-official" / "orig_observer"
TASK, SRC, SEED = "PickXtimes", 3, 510300
KEY = f"{TASK}_xhard0_{SEED}"
SEEDS = {(TASK, SRC): SEED}


def _wrap(name: str):
    return load_script(f"eval-official/orig_observer/{name}.py", fresh=True)


def _img(k: int, cam: int = 0) -> np.ndarray:
    return np.full((4, 6, 3), (k * 7 + cam * 3) % 251, dtype=np.uint8)


def _st(k: int) -> np.ndarray:
    return (np.arange(8, dtype=np.float32) * np.float32(0.1) + np.float32(k)).astype(np.float32)


def _actions(n: int = 20, base: float = 0.1) -> np.ndarray:
    """float32 动作块（0.1 等值在 float32 下不可精确表示，用来核 float64 换算精度）。"""
    return (np.arange(n * 8, dtype=np.float32).reshape(n, 8) * np.float32(base) + np.float32(base)).astype(np.float32)


def _gate2():
    return load_script("eval-official/gate2_compare.py")


def _rows(ep: Path) -> list[dict]:
    return [json.loads(x) for x in (ep / "trace.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


# ══════════════════════════════════════════════════════════════════════ SimpleMemVLA 替身


class FakeSimService:
    """照原版 ``SimEnvService.step``：动作块整体转 float64，逐行 ``step_one``，环境报错即停（该步无观测）。"""

    def __init__(self, *, success_at=None, error_at=None, max_steps=1300, demo=2, frames_per_step=1):
        self.success_at, self.error_at, self.max_steps = success_at, error_at, max_steps
        self.demo, self.fps = demo, frames_per_step
        self.count = 0
        self.received: list[np.ndarray] = []

    def reset(self, spec):
        frames = [{"front": _img(-k), "wrist": _img(-k, 1)} for k in range(self.demo, -1, -1)]
        return {"ok": True, "episode": spec["episode"], "instruction": "pick the cube three times",
                "frames": frames, "states": [_st(-k) for k in range(self.demo, -1, -1)], "max_steps": self.max_steps}

    def step(self, payload):
        chunk = np.asarray(payload["action_chunk"], dtype=np.float64)
        frames, states, consumed, error, status = [], [], 0, None, "ongoing"
        for action in chunk:
            self.received.append(np.asarray(action, dtype=np.float64).reshape(-1)[:8].copy())
            self.count += 1
            consumed += 1
            if self.count == self.error_at:
                status, error = "error", "boom"
                break
            for r in range(self.fps):
                frames.append({"front": _img(self.count * 10 + r), "wrist": _img(self.count * 10 + r, 1)})
                states.append(_st(self.count * 10 + r))
            if self.count == self.success_at:
                status = "success"
            elif self.count >= self.max_steps:
                status = "timeout"
            if status != "ongoing":
                break
        return {"frames": frames, "states": states, "consumed": consumed,
                "done": status in ("success", "fail", "timeout", "error"), "success": status == "success",
                "status": status, "error_message": error}


def make_smvla_classes(service: FakeSimService, *, pool_error_at_call=None):
    class InProcSimPool:
        def __init__(self):
            self.calls = 0
            self.returned: list = []

        def reset(self, specs):
            out = [service.reset(specs[0])]
            self.returned.append(out)
            return out

        def step(self, action_chunks, active):
            self.calls += 1
            if self.calls == pool_error_at_call:
                out = [{"error": "step_exc: 线程超时"}]
            else:
                out = [service.step({"action_chunk": action_chunks[0]})]
            self.returned.append(out)
            return out

    class BatchedEvalPolicy:
        def __init__(self):
            self.n = 0
            self.returned: list = []

        def generate_batch(self, processed_list, state_norm_list):
            self.n += 1
            out = [(_actions(20, 0.1 * self.n), f"subtask-{self.n}")]
            self.returned.append(out)
            return out

    return InProcSimPool, BatchedEvalPolicy


def fake_run_group(args, pool, batched, buffer_factory, normalize_state, task, specs,
                   video_dir=None, video_quota=None, details=None, video_path_fn=None):
    """原版 ``run_group`` 控制流的 CPU 复刻（组大小 1）。"""
    details[:] = [dict(status=None, steps=0, error=None, video=None, video_error=None)]
    r = pool.reset(specs)[0]
    if not (isinstance(r, dict) and r.get("ok")):
        details[0].update(status="error", error=f"reset 失败：{r}")
        return [None]
    hard_bound = max(1, -(-int(args.max_steps) // args.execute_horizon)) + 2
    for _ in range(hard_bound):
        acts, _sub = batched.generate_batch([{}], [None])[0]
        res = pool.step([acts[: args.execute_horizon]], [0])[0]
        if "error" in res:
            details[0].update(status="error", error=res["error"])
            return [False]
        details[0]["steps"] += int(res.get("consumed", 0) or 0)
        if res.get("done"):
            details[0].update(status=str(res.get("status")), error=res.get("error_message"))
            return [bool(res.get("success"))]
    details[0].update(status="timeout")
    return [False]


def run_smvla(wrap, root: Path, service: FakeSimService, **kw):
    """装钩子、跑一局；返回 (钩子版返回值, details, pool, policy)。"""
    wrap._state["root"] = root
    wrap.ERR.root = root
    Pool, Policy = make_smvla_classes(service, **kw)
    wrap._patch_pool(types.SimpleNamespace(InProcSimPool=Pool))
    wrap._patch_policy(types.SimpleNamespace(BatchedEvalPolicy=Policy))
    pool, policy = Pool(), Policy()
    details: list = []
    args = types.SimpleNamespace(max_steps=service.max_steps, execute_horizon=16)
    rg = wrap._wrap_run_group(fake_run_group, SEEDS)
    ret = rg(args, pool, policy, None, None, TASK, [{"task": TASK, "episode": SRC}], details=details,
             video_path_fn=None)
    return ret, details, pool, policy


def test_smvla_success_partial_chunk_float64_and_readers(tmp_path):
    wrap = _wrap("smvla_wrap")
    svc = FakeSimService(success_at=20)
    ret, details, pool, policy = run_smvla(wrap, tmp_path, svc)
    # 钩子不改返回值：run_group 返回、details 与未挂钩复刻逐项相同
    svc2 = FakeSimService(success_at=20)
    P2, B2 = make_smvla_classes(svc2)
    d2: list = []
    ret2 = fake_run_group(types.SimpleNamespace(max_steps=1300, execute_horizon=16), P2(), B2(), None, None, TASK,
                          [{"task": TASK, "episode": SRC}], details=d2)
    assert ret == ret2 == [True] and details == d2
    assert all(np.array_equal(a, b) for a, b in zip(svc.received, svc2.received))
    ep = tmp_path / f"{KEY}.a1"
    tc.assert_renderable(ep)
    tc.assert_counts_consistent(ep, {"exec_steps": details[0]["steps"], "status": "success"})
    rows = _rows(ep)
    head, end = rows[0], rows[-1]
    assert head["route"] == "smvla/orig"
    assert head["identity"] == {"task": TASK, "tier": "xhard0", "seed": SEED, "source_episode": SRC, "key": KEY,
                                "dataset": "test-hard0", "attempt": 1}
    steps = [r for r in rows if r["kind"] == "step"]
    assert len(steps) == 20 == details[0]["steps"]  # 16 + 部分动作块 4
    assert end["steps_attempted"] == 20 and end["steps_observed"] == 20 and end["observer_hook_errors"] == 0
    assert end["demo_frames"] == 2 and end["frames_recorded"] == 23
    assert all(s["terminated"] == "NOT_OBSERVED" and s["truncated"] == "NOT_OBSERVED" for s in steps)
    assert [s["status"] for s in steps if s["status"] != "NOT_OBSERVED"] == ["ongoing", "success"]
    assert steps[0]["subgoal"] == "subtask-1" and steps[16]["subgoal"] == "subtask-2"
    # arrays.npz：float64、等于环境实际收到的行（float32 → float64 精确换算，不经 float32 往返）
    with np.load(ep / "arrays.npz") as z:
        assert sorted(z.files) == [f"exec_action__{i:05d}" for i in range(20)]
        for i in range(20):
            a = z[f"exec_action__{i:05d}"]
            assert a.dtype == np.float64 and a.shape == (8,)
            assert a.tobytes() == svc.received[i].tobytes()
    assert {s["action"]["dtype"] for s in steps} == {"<f8"}
    # 请求／回复：每次决策一条 infer 请求与完整动作块
    reqs = [r for r in rows if r["kind"] == "request"]
    resps = [r for r in rows if r["kind"] == "response"]
    assert [r["step"] for r in reqs] == [0, 16] and [r["name"] for r in reqs] == ["infer", "infer"]
    assert resps[0]["actions"]["shape"] == [20, 8] and resps[0]["actions"]["dtype"] == "<f4"
    # 原始帧：reset 全部帧 + 每步一帧
    fj = json.loads((ep / "frames" / "frames.json").read_text())
    assert fj["streams"]["front"]["count"] == 23 and fj["missing_steps"] == []
    # gate2_compare 读取：按身份索引找到、自比全同
    g2 = _gate2()
    idx = g2.TraceIndex(tmp_path)
    assert idx.lookup({"task": TASK, "source_episode": SRC, "seed": SEED, "attempt": 1}) == ep / "trace.jsonl"
    assert g2.compare_traces(rows, rows)["identical"] is True


def test_smvla_exec_rows_matches_service_conversion():
    sa = load_script("eval-official/orig_observer/step_arrays.py", fresh=True)
    chunk = _actions(16)
    rows = sa.smvla_exec_rows(chunk, 5)
    assert len(rows) == 5
    ref = np.asarray(chunk, dtype=np.float64)
    for j, r in enumerate(rows):
        assert r.dtype == np.float64 and r.tobytes() == np.asarray(ref[j], np.float64).reshape(-1)[:8].tobytes()
        assert not np.shares_memory(r, chunk)
    assert sa.smvla_exec_rows(chunk, 0) == []


def test_smvla_error_then_success_resume_and_adapter(tmp_path):
    wrap = _wrap("smvla_wrap")
    ret, details, _, _ = run_smvla(wrap, tmp_path, FakeSimService(error_at=5))
    assert ret == [False] and details[0]["status"] == "error" and details[0]["steps"] == 5
    ep1 = tmp_path / f"{KEY}.a1"
    assert tc.contract_problems(ep1) == []
    rows1 = _rows(ep1)
    st = [r for r in rows1 if r["kind"] == "step"]
    assert st[-1]["observed"] is False and "env_step_error" in st[-1]["missing_reason"]
    assert rows1[-1]["status"] == "error" and rows1[-1]["steps_observed"] == 4 and rows1[-1]["steps_attempted"] == 5
    tc.assert_counts_consistent(ep1, {"exec_steps": 5, "status": "error"})
    # 续跑：新进程（重新加载模块）接着编号
    wrap2 = _wrap("smvla_wrap")
    ret2, details2, _, _ = run_smvla(wrap2, tmp_path, FakeSimService(success_at=7))
    assert ret2 == [True]
    ep2 = tmp_path / f"{KEY}.a2"
    tc.assert_renderable(ep2)
    assert _rows(ep2)[0]["identity"]["attempt"] == 2
    log = tmp_path / "episodes-shard00of10.jsonl"
    log.write_text("".join(json.dumps({"task": TASK, "source_episode": SRC, "seed": SEED, "status": d[0]["status"],
                                       "steps": d[0]["steps"]}) + "\n" for d in (details, details2)))
    ora = load_script("eval-official/orig_observer/orig_results_adapter.py", fresh=True)
    res = ora.build(ora.read_log([log]), tmp_path, policy="smvla")
    assert res["ORIG_ATTEMPTS"] == "PASS"
    (item,) = res["identities"]
    assert item["attempt"] == 2 and item["status"] == "success" and item["trace_path"] == str(ep2 / "trace.jsonl")
    assert res["counts"]["orphan"] == 0


def test_smvla_pool_error_and_reset_failure(tmp_path):
    wrap = _wrap("smvla_wrap")
    ret, details, _, _ = run_smvla(wrap, tmp_path, FakeSimService(success_at=40), pool_error_at_call=2)
    assert ret == [False] and details[0]["steps"] == 16
    ep = tmp_path / f"{KEY}.a1"
    end = _rows(ep)[-1]
    assert end["status"] == "error" and end["steps_attempted"] == 16 and end["pool_errors"]
    assert tc.contract_problems(ep) == []

    class BadReset(FakeSimService):
        def reset(self, spec):
            return {"ok": False, "reason": "reset_failed: x"}

    ret, details, _, _ = run_smvla(wrap, tmp_path, BadReset())
    ep2 = tmp_path / f"{KEY}.a2"
    end = _rows(ep2)[-1]
    assert ret == [None] and end["status"] == "error" and end["no_frame"] is True and end["frames_recorded"] == 0
    assert tc.contract_problems(ep2) == []


def test_smvla_hook_exception_is_contained_and_counted(tmp_path, monkeypatch):
    wrap = _wrap("smvla_wrap")

    def boom(*a, **k):
        raise RuntimeError("注入的钩子异常")

    monkeypatch.setattr(wrap.SA, "smvla_exec_rows", boom)
    ret, details, pool, _ = run_smvla(wrap, tmp_path, FakeSimService(success_at=20))
    assert ret == [True] and details[0]["status"] == "success" and details[0]["steps"] == 20
    end = _rows(tmp_path / f"{KEY}.a1")[-1]
    assert end["observer_hook_errors"] == 2 and end["status"] == "success"
    lines = (tmp_path / "hook-errors.jsonl").read_text().splitlines()
    assert len(lines) == 2 and wrap.ERR.count == 2
    # 判定器据此判 FAIL
    ost = load_script("eval-official/orig_observer/observer_status.py", fresh=True)
    st = ost.evaluate(tmp_path, policy="smvla")
    assert st["OBSERVER_COMPLETE"] == "FAIL" and st["hook_errors"] == 2


def test_smvla_frames_per_step_takes_last_frame(tmp_path):
    wrap = _wrap("smvla_wrap")
    run_smvla(wrap, tmp_path, FakeSimService(success_at=3, frames_per_step=2))
    ep = tmp_path / f"{KEY}.a1"
    steps = [r for r in _rows(ep) if r["kind"] == "step"]
    tw = load_script("eval-official/trace_writer.py")
    assert [s["front_sha256"] for s in steps] == [tw.image_sha256(_img(k * 10 + 1)) for k in (1, 2, 3)]
    tc.assert_renderable(ep)


# ══════════════════════════════════════════════════════════════════════ MME 替身


def make_mme_classes(*, error_at=None, success_at=None, max_steps=1300, demo=2):
    class FakeWS:
        """假 websocket 连接：send 记下原始载荷，recv 依次返回预置回包。"""

        def __init__(self):
            self.sent: list = []
            self.replies: collections.deque = collections.deque()

        def send(self, message):
            self.sent.append(message)

        def recv(self):
            return self.replies.popleft() if self.replies else b"\x80"

    class EnvRunner:
        def __init__(self, env_id, episode_id):
            self.env_id, self.episode_id, self.count = env_id, episode_id, 0
            self.received: list = []

        def get_init_obs(self):
            k = list(range(demo, -1, -1))
            return {"images": [_img(-i) for i in k], "wrist_images": [_img(-i, 1) for i in k],
                    "states": [_st(-i) for i in k], "task_goal": "pick the cube three times"}

        def step(self, action):
            self.received.append(action)
            self.count += 1
            if self.count == error_at:
                return (None, None, None), True, "error"
            st = "success" if self.count == success_at else "ongoing"
            return (_img(self.count), _img(self.count, 1), _st(self.count)), st == "success", st

    class MMEVLAWebsocketClientPolicy:
        def __init__(self):
            self._ws = FakeWS()
            self.n = 0

        def reset(self):
            self._ws.send(b"reset-payload")
            self._ws.recv()
            return {"reset_finished": True}

        def add_buffer(self, buffer):
            self._ws.send(b"buffer-" + str(buffer["n"]).encode())
            self._ws.recv()

        def infer(self, obs):
            self.n += 1
            self._ws.send(b"infer-" + str(self.n).encode())
            self._ws.recv()
            return {"actions": _actions(16, 0.01 * self.n)}

    class EpisodeEvaluator:
        def __init__(self):
            self.args = types.SimpleNamespace(max_steps=max_steps, obs_horizon=16)
            self.last_steps = 0

        def eval_each_episode(self, env_runner, subgoal_predictor=None, video_save_dir=None):
            client = MMEVLAWebsocketClientPolicy()
            client.reset()
            pre = env_runner.get_init_obs()
            plan: collections.deque = collections.deque()
            count, flag = 0, "unknown"
            while True:
                if not plan:
                    client.add_buffer({"n": count})
                    plan.extend(client.infer({"state": pre["states"][-1]})["actions"])
                action = plan.popleft()
                obs, stop, flag = env_runner.step(action)
                count += 1
                self.last_steps = count
                if count > self.args.max_steps:
                    flag = "timeout"
                    break
                img, wrist, state = obs
                img.copy()  # 原版 recorder.record(image=img.copy())：无观测步在此抛 AttributeError
                if stop:
                    break
            if flag == "unknown":
                return "unknown"
            return flag

    return EnvRunner, MMEVLAWebsocketClientPolicy, EpisodeEvaluator, FakeWS


def setup_mme(wrap, root: Path, **kw):
    wrap._state["root"] = root
    wrap.ERR.root = root
    Runner, Client, Evaluator, WS = make_mme_classes(**kw)
    wrap._patch_env_runner(types.SimpleNamespace(EnvRunner=Runner))
    wrap._patch_ws(types.SimpleNamespace(ClientConnection=WS))
    wrap._patch_policy_client(types.SimpleNamespace(MMEVLAWebsocketClientPolicy=Client))
    wrap._patch_evaluator(types.SimpleNamespace(EpisodeEvaluator=Evaluator), SEEDS)
    return Runner, Evaluator


def test_mme_success_trace_requests_transport(tmp_path):
    wrap = _wrap("mme_client_wrap")
    Runner, Evaluator = setup_mme(wrap, tmp_path, success_at=20)
    runner = Runner(TASK, SRC)
    assert Evaluator().eval_each_episode(runner) == "success"
    ep = tmp_path / f"{KEY}.a1"
    tc.assert_renderable(ep)
    tc.assert_counts_consistent(ep, {"exec_steps": 20, "status": "success"})
    rows = _rows(ep)
    assert rows[0]["route"] == "mme/orig"
    steps = [r for r in rows if r["kind"] == "step"]
    assert len(steps) == 20 and all(s["subgoal"] is None for s in steps)
    assert all(s["terminated"] == "NOT_OBSERVED" for s in steps) and steps[-1]["status"] == "success"
    reqs = [r for r in rows if r["kind"] == "request"]
    assert [r["name"] for r in reqs][:3] == ["reset", "add_buffer", "infer"]
    assert reqs[2]["sha256"] == hashlib.sha256(b"infer-1").hexdigest() and reqs[2]["nbytes"] == len(b"infer-1")
    assert [r["step"] for r in reqs if r["name"] == "infer"] == [0, 16]
    with np.load(ep / "arrays.npz") as z:
        assert z["exec_action__00000"].dtype == np.float32 and len(z.files) == 20
        assert z["exec_action__00000"].tobytes() == runner.received[0].tobytes()
    tlog = list(tmp_path.glob("client-transport-*.jsonl"))
    recs = [json.loads(x) for x in tlog[0].read_text().splitlines()]
    assert {r["episode"] for r in recs} == {ep.name} and recs[0]["dir"] == "send"
    g2 = _gate2()
    assert g2.TraceIndex(tmp_path).lookup({"task": TASK, "source_episode": SRC, "seed": SEED}) == ep / "trace.jsonl"
    assert g2.compare_traces(rows, rows)["identical"] is True


def test_mme_hook_returns_identical_objects(tmp_path):
    """钩子拿到原函数的返回值原样返回（同一对象），交给原函数的动作也是同一对象。"""
    wrap = _wrap("mme_client_wrap")
    setup_mme(wrap, tmp_path)
    sentinel = ((_img(1), _img(1, 1), _st(1)), False, "ongoing")
    init = {"images": [_img(0)], "wrist_images": [_img(0, 1)], "states": [_st(0)], "task_goal": "g"}
    seen = []

    class E:
        env_id, episode_id = TASK, SRC

        def get_init_obs(self):
            return init

        def step(self, action):
            seen.append(action)
            return sentinel

    wrap._patch_env_runner(types.SimpleNamespace(EnvRunner=E))
    a = np.ones(8, np.float32)
    assert E().get_init_obs() is init
    assert E().step(a) is sentinel and seen[0] is a


def test_mme_timeout_omits_last_frame(tmp_path):
    wrap = _wrap("mme_client_wrap")
    Runner, Evaluator = setup_mme(wrap, tmp_path, max_steps=5)
    assert Evaluator().eval_each_episode(Runner(TASK, SRC)) == "timeout"
    ep = tmp_path / f"{KEY}.a1"
    end = _rows(ep)[-1]
    assert end["steps_attempted"] == 6 and end["omitted_timeout_frames"] == 1
    assert end["frames_recorded"] == 2 + 1 + 6 - 1
    tc.assert_renderable(ep)


def test_mme_env_exception_missing_step_and_error(tmp_path):
    wrap = _wrap("mme_client_wrap")
    Runner, Evaluator = setup_mme(wrap, tmp_path, error_at=4)
    with pytest.raises(AttributeError):  # 原版 img.copy() 的异常原样上抛
        Evaluator().eval_each_episode(Runner(TASK, SRC))
    ep = tmp_path / f"{KEY}.a1"
    rows = _rows(ep)
    assert tc.contract_problems(ep) == []
    st = [r for r in rows if r["kind"] == "step"]
    assert st[-1]["observed"] is False and st[-1]["step"] == 4 and rows[-1]["status"] == "error"
    assert rows[-1]["exception"].startswith("AttributeError") and rows[-1]["observer_hook_errors"] == 0
    fj = json.loads((ep / "frames" / "frames.json").read_text())
    assert fj["missing_steps"] == [4]


def test_mme_unknown_flag_is_error(tmp_path):
    wrap = _wrap("mme_client_wrap")
    Runner, Evaluator = setup_mme(wrap, tmp_path)

    class E(Evaluator):
        def eval_each_episode(self, env_runner, *a, **k):  # 原版 has_api_error 早退：返回 unknown
            env_runner.get_init_obs()
            return "unknown"

    wrap._patch_evaluator(types.SimpleNamespace(EpisodeEvaluator=E), SEEDS)
    assert E().eval_each_episode(Runner(TASK, SRC)) == "unknown"
    end = _rows(tmp_path / f"{KEY}.a1")[-1]
    assert end["status"] == "error" and end["success_flag"] == "unknown"


def test_mme_hook_exception_contained(tmp_path, monkeypatch):
    wrap = _wrap("mme_client_wrap")
    Runner, Evaluator = setup_mme(wrap, tmp_path, success_at=3)
    monkeypatch.setattr(wrap.OE.OrigEpisode, "on_response", lambda self, a: (_ for _ in ()).throw(ValueError("x")))
    assert Evaluator().eval_each_episode(Runner(TASK, SRC)) == "success"
    end = _rows(tmp_path / f"{KEY}.a1")[-1]
    assert end["observer_hook_errors"] == 1 and end["status"] == "success"


# ══════════════════════════════════════════════════════════════════════ attempt 映射


def _trace(root: Path, attempt: int, status: str | None, key: str = KEY):
    tw = load_script("eval-official/trace_writer.py")
    ep = root / f"{key}.a{attempt}"
    ident = {"task": TASK, "tier": "xhard0", "seed": SEED, "source_episode": SRC, "key": key, "dataset": "test-hard0",
             "attempt": attempt}
    w = tw.TraceWriter(ep / "trace.jsonl", route="mme/orig", identity=ident, max_steps=1300)
    w.log_demo([_img(0)], [_img(0, 1)], [_st(0)], ["goal"])
    if status is not None:
        w.close(status=status, terminal_reason=status, demo_frames=0, steps_attempted=0, steps_observed=0,
                frames_recorded=1, observer_hook_errors=0)
    return ep


def _log(path: Path, statuses: list[str]):
    path.write_text("".join(json.dumps({"task": TASK, "source_episode": SRC, "seed": SEED, "status": s}) + "\n"
                            for s in statuses))
    return path


def test_adapter_orphan_duplicate_terminal_and_mismatch(tmp_path):
    ora = load_script("eval-official/orig_observer/orig_results_adapter.py", fresh=True)
    # 孤儿：a1 中途被杀（无 end），a2 error，a3 success；日志两行
    _trace(tmp_path, 1, None)
    _trace(tmp_path, 2, "error")
    _trace(tmp_path, 3, "success")
    _trace(tmp_path, 1, "fail", key="Other_xhard0_1")
    log = _log(tmp_path / "episodes.jsonl", ["error", "success"])
    res = ora.build(ora.read_log([log]), tmp_path, policy="mme")
    assert res["ORIG_ATTEMPTS"] == "PASS"
    (item,) = res["identities"]
    assert item["attempt"] == 3 and item["row_index"] == 1 and item["terminal_rows"] == 1
    reasons = sorted((o["key"], o["attempt"], o["reason"]) for o in res["orphans"])
    assert reasons == sorted([(KEY, 1, "no_end_line"), ("Other_xhard0_1", 1, "identity_not_in_log")])
    # 重复终态：取最后一条终态行
    d2 = tmp_path / "dup"
    _trace(d2, 1, "success")
    _trace(d2, 2, "fail")
    res = ora.build(ora.read_log([_log(d2 / "e.jsonl", ["success", "fail"])]), d2, policy="mme")
    assert res["identities"][0]["attempt"] == 2 and res["identities"][0]["status"] == "fail"
    # 状态不符 → FAIL
    d3 = tmp_path / "mis"
    _trace(d3, 1, "fail")
    res = ora.build(ora.read_log([_log(d3 / "e.jsonl", ["success"])]), d3, policy="mme")
    assert res["ORIG_ATTEMPTS"] == "FAIL" and res["counts"]["status_mismatch"] == 1
    # 缺 trace → FAIL；只有 error 行 → unresolved（不判 FAIL）
    d4 = tmp_path / "miss"
    d4.mkdir()
    res = ora.build(ora.read_log([_log(d4 / "e.jsonl", ["success"])]), d4, policy="mme")
    assert res["counts"]["missing_trace"] == 1 and res["ORIG_ATTEMPTS"] == "FAIL"
    d5 = tmp_path / "unres"
    _trace(d5, 1, "error")
    res = ora.build(ora.read_log([_log(d5 / "e.jsonl", ["error"])]), d5, policy="mme")
    assert res["ORIG_ATTEMPTS"] == "PASS" and res["identities"][0]["unresolved"] is True
    # CLI 写 orig-attempts.json 与判定行
    out = tmp_path / "orig-attempts.json"
    rc = ora.main(["--policy", "mme", "--episode-log", str(log), "--rec-root", str(tmp_path), "--out", str(out)])
    assert rc == 0 and json.loads(out.read_text())["schema"] == "orig-attempts/1"


# ══════════════════════════════════════════════════════════════════════ 透明性对账与完整性判定


def _transport_fixture(root: Path, *, seal: bool = True, pid: int = 4242, with_trace: bool = True):
    """一条客户端连接（2 发 2 收）与代理同一连接的逐条记录、封口标记、清单与 trace。"""
    msgs = [("send", b"a"), ("recv", b"bb"), ("send", b"ccc"), ("recv", b"dddd")]
    cl, px, idx = [], [], {"send": 0, "recv": 0}
    for d, m in msgs:
        i = idx[d]
        idx[d] += 1
        sha = hashlib.sha256(m).hexdigest()
        cl.append({"pid": 1, "conn": 0, "dir": d, "idx": i, "type": "binary", "len": len(m), "sha256": sha,
                   "episode": f"{KEY}.a1"})
        px.append({"kind": "msg", "conn": 0, "dir": "c2s" if d == "send" else "s2c", "idx": i, "type": "binary",
                   "len": len(m), "sha256": sha})
    (root / "proxy").mkdir(parents=True, exist_ok=True)
    (root / "client-transport-1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in cl))
    (root / "proxy" / f"proxy-{pid}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in px))
    if seal:
        (root / "proxy" / f"proxy-{pid}.done").write_text("{}\n")
    if with_trace:
        _trace(root, 1, "success")
    man = root / "manifest.jsonl"
    man.write_text(json.dumps({"task": TASK, "source_episode": SRC, "seed": SEED, "shard": 0}) + "\n"
                   + json.dumps({"task": "Other", "source_episode": 1, "seed": 9, "shard": 1}) + "\n")
    return man


def test_transparency_check_coverage_and_seal(tmp_path):
    tcx = load_script("eval-official/orig_observer/transparency_check.py", fresh=True)
    man = _transport_fixture(tmp_path)
    keys = tcx.manifest_keys(man, 0)
    rep = tcx.check(tmp_path, keys)
    assert rep["OBSERVER_TRANSPARENT"] == "PASS" and rep["mismatch"] == 0 and rep["conns"] == 1
    assert "missing_conn=0 missing_trace=0 unsealed=0" in tcx.verdict_line(rep)
    # 清单里多一个没有连接与 trace 的身份 → FAIL
    rep = tcx.check(tmp_path, tcx.manifest_keys(man, None))
    assert rep["OBSERVER_TRANSPARENT"] == "FAIL" and rep["missing_conn"] == ["Other_xhard0_9"]
    # 未封口 → FAIL
    (tmp_path / "proxy" / "proxy-4242.done").unlink()
    rep = tcx.check(tmp_path, keys)
    assert rep["OBSERVER_TRANSPARENT"] == "FAIL" and rep["unsealed"] == ["proxy-4242.jsonl"]


@pytest.mark.parametrize("case,expect_report", [
    ("pass", "ok"), ("transparent_fail", "ok"), ("crashed", "crashed"), ("missing", "missing"), ("seal_timeout", "ok"),
    ("force_killed", "ok")])
def test_observer_status_cases(tmp_path, case, expect_report):
    ost = load_script("eval-official/orig_observer/observer_status.py", fresh=True)
    _trace(tmp_path, 1, "success")
    log = _log(tmp_path / "episodes.jsonl", ["success"])
    before = log.read_bytes()
    rep = tmp_path / "transparency.json"
    good = {"OBSERVER_TRANSPARENT": "PASS", "conns": 1, "mismatch": 0}
    kw = {"sealed": "yes", "proxy_force_killed": 0, "checker_rc": 0}
    if case == "transparent_fail":
        rep.write_text(json.dumps({"OBSERVER_TRANSPARENT": "FAIL", "conns": 1, "mismatch": 3}))
    elif case == "crashed":
        kw["checker_rc"] = 2
        rep.write_text(json.dumps(good))
    elif case != "missing":
        rep.write_text(json.dumps(good))
    if case == "seal_timeout":
        kw["sealed"] = "timeout"
    if case == "force_killed":
        kw.update(sealed="no", proxy_force_killed=1)
    st = ost.evaluate(tmp_path, policy="mme", report=str(rep), episode_logs=[str(log)], **kw)
    assert st["report"] == expect_report
    assert st["OBSERVER_COMPLETE"] == ("PASS" if case == "pass" else "FAIL")
    assert log.read_bytes() == before  # 成绩（逐局日志）不变
    line = ost.verdict_line(st)
    assert line.startswith(f"OBSERVER_COMPLETE={st['OBSERVER_COMPLETE']} episodes=1 conns=")
    assert line.endswith(f"report={expect_report}")
    assert (tmp_path / "orig-attempts.json").is_file()


# ══════════════════════════════════════════════════════════════════════ 启动器（bash）


def _bash(script: str, env: dict | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e, timeout=timeout)


FAKE_PROXY = textwrap.dedent("""
    import json, os, signal, sys, time
    log_dir, mode, src = sys.argv[1], sys.argv[2], sys.argv[3]
    pid = os.getpid()
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f"proxy-{pid}.jsonl"), "w") as fh:
        fh.write(open(src).read())
    def term(*_):
        if mode == "ignore":
            return
        with open(os.path.join(log_dir, f"proxy-{pid}.done"), "w") as fh:
            fh.write("{}\\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, term)
    print("PROXY_READY", flush=True)
    while True:
        time.sleep(0.1)
""")


@pytest.mark.slow
@pytest.mark.parametrize("mode,checker,expect", [
    ("seal", "real", "PASS"), ("ignore", "real", "FAIL"), ("seal", "crash", "FAIL")])
def test_mme_finalize_shell_seal_and_exit_code(tmp_path, mode, checker, expect):
    rec = tmp_path / "rec"
    rec.mkdir()
    man = _transport_fixture(rec, seal=False)
    src = rec / "proxy" / "proxy-4242.jsonl"
    tpl = tmp_path / "proxy-template.jsonl"
    src.rename(tpl)
    fake = tmp_path / "fake_proxy.py"
    fake.write_text(FAKE_PROXY)
    py = sys.executable
    if checker == "crash":
        crash = tmp_path / "crashpy"
        crash.write_text("#!/usr/bin/env bash\nexit 2\n")
        crash.chmod(0o755)
        py = str(crash)
    eplog = _log(tmp_path / "episodes.jsonl", ["success"])
    script = f"""
        source {OBS}/orig_observer_lib.sh
        RC=3
        {sys.executable} {fake} {rec}/proxy {mode} {tpl} > {tmp_path}/proxy.log 2>&1 &
        PROXY_PID=$!
        for _ in $(seq 1 100); do grep -q PROXY_READY {tmp_path}/proxy.log 2>/dev/null && break; sleep 0.1; done
        orig_stop_proxy
        echo "PID_AFTER=[$PROXY_PID]"
        orig_wait_seal {rec}/proxy "$PROXY_STOPPED_PID"
        orig_finalize_mme {py} {OBS} {rec} {man} 0 {eplog}
        echo "EXIT_CODE=$RC"
    """
    r = _bash(script, {"PROXY_STOP_TIMEOUT": "2", "SEAL_TIMEOUT": "2"})
    out = r.stdout
    assert "EXIT_CODE=3" in out, out + r.stderr  # 评估退出码不被观测器改动
    assert "PID_AFTER=[]" in out
    line = [x for x in out.splitlines() if x.startswith("OBSERVER_COMPLETE=")]
    assert line and line[-1].startswith(f"OBSERVER_COMPLETE={expect}"), out + r.stderr
    st = json.loads((rec / "observer-status.json").read_text())
    assert st["OBSERVER_COMPLETE"] == expect
    if mode == "ignore":
        assert "proxy_force_killed" in out and st["proxy_force_killed"] == 1 and st["sealed"] == "no"
        assert "TRANSPARENCY_SKIPPED" in out and st["report"] == "missing"
    if checker == "crash":
        assert st["report"] == "crashed"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.slow
@pytest.mark.parametrize("launcher,repo_var", [("run_orig_smvla.sh", "SMVLA_ORIG_REPO"),
                                               ("run_orig_mme.sh", "MME_ORIG_REPO")])
def test_launcher_blocks_on_commit_mismatch_or_dirty(tmp_path, launcher, repo_var):
    repo = tmp_path / "orig"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("x\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "init")
    head = _git(repo, "rev-parse", "HEAD")
    r = _bash(f"bash {OBS}/{launcher}", {repo_var: str(repo)})
    assert "RUN_BLOCKED reason=orig_commit_mismatch" in r.stdout and "EXIT_CODE=1" in r.stdout and r.returncode == 1
    assert "ORIG_BRANCH_PIN=FAIL" in r.stdout
    # 生产路径不认自测覆盖变量
    r = _bash(f"bash {OBS}/{launcher}", {repo_var: str(repo), "ORIG_PIN_SELFTEST_EXPECT": head})
    assert "RUN_BLOCKED reason=orig_commit_mismatch" in r.stdout
    selftest = {repo_var: str(repo), "ORIG_OBSERVER_SELFTEST": "1", "ORIG_PIN_SELFTEST_EXPECT": head}
    (repo / "untracked.txt").write_text("dirty\n")
    r = _bash(f"bash {OBS}/{launcher}", selftest)
    assert "RUN_BLOCKED reason=orig_worktree_dirty" in r.stdout and r.returncode == 1
    (repo / "untracked.txt").unlink()
    if launcher == "run_orig_smvla.sh":
        r = _bash(f"bash {OBS}/{launcher}", selftest)
        assert "ORIG_BRANCH_PIN=PASS" in r.stdout and "ORIG_SELFTEST_GUARD=PASS" in r.stdout and r.returncode == 0
    else:  # 无子模块 → 子模块提交不符
        r = _bash(f"bash {OBS}/{launcher}", selftest)
        assert "RUN_BLOCKED reason=orig_submodule_mismatch" in r.stdout


@pytest.mark.slow
def test_budget_reserve_and_pending_count(tmp_path):
    calls = tmp_path / "calls.txt"
    stub = tmp_path / "ledger_stub.py"
    stub.write_text(textwrap.dedent(f"""
        import sys
        with open({str(calls)!r}, "a") as fh:
            fh.write(" ".join(sys.argv[1:]) + "\\n")
        n = sum(1 for _ in open({str(calls)!r}))
        sys.exit(0 if n <= 3 else 1)
    """))
    man = tmp_path / "m.jsonl"
    man.write_text("".join(json.dumps({"task": "T", "source_episode": i, "seed": i, "shard": i % 2}) + "\n"
                           for i in range(6)))
    eplog = tmp_path / "e.jsonl"
    eplog.write_text(json.dumps({"task": "T", "source_episode": 0, "status": "success"}) + "\n"
                     + json.dumps({"task": "T", "source_episode": 2, "status": "error"}) + "\n")
    env = {"BUDGET_LEDGER_CMD": f"{sys.executable} {stub}", "BUDGET_LEDGER_ARGS": "--ledger L"}
    r = _bash(f"source {OBS}/orig_observer_lib.sh; orig_pending_count {man} 0 {eplog}; "
              f"orig_budget_reserve 2 6 && echo OK1; orig_budget_reserve 2 6 || echo BLOCKED", env)
    lines = r.stdout.splitlines()
    assert lines[0] == "2"  # shard 0 = {0,2,4}，0 已终态，2 仅 error → 待跑 2、4
    assert "BUDGET_RESERVED episodes=2 resets_per_episode=6 total_resets=12" in r.stdout and "OK1" in r.stdout
    assert "RUN_BLOCKED reason=budget reserved=1/2 resets_per_episode=6" in r.stdout and "BLOCKED" in r.stdout
    assert calls.read_text().splitlines()[0] == "reserve --resets 6 --ledger L"
    # 账本脚本缺失（S8 未合入时）同样阻断
    r = _bash(f"source {OBS}/orig_observer_lib.sh; BUDGET_PY=/bin/false; orig_budget_reserve 1 2 || echo BLOCKED",
              {"BUDGET_LEDGER_CMD": ""})
    assert "RUN_BLOCKED" in r.stdout and "BLOCKED" in r.stdout


def test_restored_files_present_and_renamed():
    names = sorted(p.name for p in OBS.iterdir() if p.is_file())
    for n in ("_obs_common.py", "smvla_wrap.py", "mme_client_wrap.py", "mme_proxy.py", "transparency_check.py",
              "official_rerun_shard.sh", "run_orig_smvla.sh", "run_orig_mme.sh", "step_arrays.py",
              "orig_results_adapter.py", "orig_episode.py", "observer_status.py", "orig_observer_lib.sh"):
        assert n in names
    for old in ("_v75_obs_common.py", "run_official_smvla.sh", "run_official_mme.sh"):
        assert old not in names
    for p in OBS.glob("*.py"):
        assert "import _v75_obs_common" not in p.read_text(encoding="utf-8")


ECHO_SERVER = textwrap.dedent("""
    import sys
    from websockets.sync.server import serve
    def handler(ws):
        for msg in ws:
            ws.send(msg)
    with serve(handler, "127.0.0.1", int(sys.argv[1]), compression=None, max_size=None) as srv:
        print("ECHO_READY", flush=True)
        srv.serve_forever()
""")


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.slow
def test_real_proxy_seals_log_after_sigterm(tmp_path):
    """真实 mme_proxy.py（回环）：转发原样、SIGTERM 后记账收完才写 proxy-<pid>.done。"""
    from websockets.sync.client import connect

    up, lp = _free_port(), _free_port()
    echo = tmp_path / "echo.py"
    echo.write_text(ECHO_SERVER)
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    srv = subprocess.Popen([sys.executable, str(echo), str(up)], stdout=subprocess.PIPE, text=True, env=env)
    log_dir = tmp_path / "rec" / "proxy"
    prx = None
    try:
        assert srv.stdout.readline().strip() == "ECHO_READY"
        prx = subprocess.Popen([sys.executable, str(OBS / "mme_proxy.py"), "--listen", str(lp), "--upstream", str(up),
                                "--log-dir", str(log_dir)], stdout=subprocess.PIPE, text=True, env=env)
        assert prx.stdout.readline().startswith("PROXY_READY")
        with connect(f"ws://127.0.0.1:{lp}", compression=None, max_size=None) as ws:
            for m in (b"\x01\x02", b"payload-2"):
                ws.send(m)
                assert ws.recv() == m
        time.sleep(0.3)
        prx.send_signal(signal.SIGTERM)
        assert prx.wait(timeout=60) == 0
        done = log_dir / f"proxy-{prx.pid}.done"
        assert done.is_file() and json.loads(done.read_text())["sealed"] is True
        recs = [json.loads(x) for x in (log_dir / f"proxy-{prx.pid}.jsonl").read_text().splitlines()]
        msgs = [r for r in recs if r.get("kind") == "msg"]
        assert [(r["dir"], r["len"]) for r in msgs] == [("c2s", 2), ("s2c", 2), ("c2s", 9), ("s2c", 9)]
    finally:
        for p in (prx, srv):
            if p is not None and p.poll() is None:
                p.kill()
                p.wait()
