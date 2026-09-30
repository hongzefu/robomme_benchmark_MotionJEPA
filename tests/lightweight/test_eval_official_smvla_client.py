"""smvla_client / smvla_server 的轻量单测（不用 GPU、不建环境）。

- 假 EnvSession + 假策略连接：消息顺序、float64[:8] 转换、块中途终止、obs None、决策用尽超时 1344。
- 真 websocket（线程内假 server，用 openpi_client.msgpack_numpy）：协议往返与 sha 核对。
- to_full / state_norm：用 ast 从上游 run_group 取出原文，与 smvla_server.make_closures 逐字比对，
  并在同一输入上执行两份闭包逐位比较。
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import sys
import textwrap
import threading
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO / "scripts" / "eval-official"
UPSTREAM_EVAL = REPO / "third_party" / "SimpleMemVLA" / "robomme_sim" / "eval_success.py"
UPSTREAM_ENV = REPO / "third_party" / "SimpleMemVLA" / "robomme_sim" / "robomme_env.py"

pytestmark = pytest.mark.lightweight


def _load(name: str, path: Path):
    # 目录名带连字符且含 queue.py（遮蔽标准库），因此按文件路径加载，不把目录放进 sys.path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load("smvla_client_under_test", EVAL_DIR / "smvla_client.py")


# ------------------------------------------------------------------ 假环境与假连接
def _frame(v: int) -> np.ndarray:
    return np.full((4, 4, 3), v % 256, dtype=np.uint8)


def _obs(vals):
    return {
        "front_rgb_list": [_frame(v) for v in vals],
        "wrist_rgb_list": [_frame(v + 100) for v in vals],
        "joint_state_list": [np.arange(7, dtype=np.float64) + v for v in vals],
        "eef_state_list": [np.zeros(7) for _ in vals],
        "gripper_state_list": [np.array([0.04 + v, 0.04]) for v in vals],
    }


class FakeSession:
    """按脚本返回的 EnvSession：terminal_at=(第几步, status)；obs_none_at=第几步 obs 为 None。"""

    def __init__(self, n_demo=3, terminal_at=None, obs_none_at=None, raise_at=None, max_steps=1300):
        self.n_demo = n_demo
        self.terminal_at = terminal_at
        self.obs_none_at = obs_none_at
        self.raise_at = raise_at
        self.max_steps = max_steps
        self.actions = []
        self.resets = 0

    def reset(self):
        self.resets += 1
        return _obs(range(self.n_demo + 1)), {"task_goal": ["pick the cube"], "status": "ongoing"}

    def step(self, action):
        self.actions.append(action)
        n = len(self.actions)
        if self.raise_at is not None and n == self.raise_at:
            raise RuntimeError("boom")
        if self.obs_none_at is not None and n == self.obs_none_at:
            return None, 0.0, False, False, {"status": "error", "error_message": "sim broke"}
        status = "ongoing"
        term = False
        if self.terminal_at is not None and n == self.terminal_at[0]:
            status, term = self.terminal_at[1], True
        return _obs([1000 + n]), 0.0, term, False, {"status": status}


class FakeConn:
    """记录消息顺序的假策略连接；动作 float32 [32, 8]，值随决策编号变化。"""

    def __init__(self, action_dim=8, horizon=32):
        self.metadata = {"policy": "smvla", "fake": True}
        self.log = []
        self.n_infer = 0
        self.action_dim = action_dim
        self.horizon = horizon
        self.closed = False

    def call(self, msg):
        raw = repr(sorted(msg)).encode() + str(len(self.log)).encode()
        kind = next(iter(msg))
        self.log.append((kind, msg[kind]))
        req = hashlib.sha256(raw).hexdigest()
        if kind == "reset":
            rep = {"reset_finished": True}
        elif kind == "observe":
            frs = msg["observe"]["frames"]
            rep = {"n": len(frs), "frame_sha": [{k: C.frame_sha(v) for k, v in sorted(f.items())} for f in frs]}
        else:
            p = msg["infer"]
            a = (np.arange(self.horizon * self.action_dim, dtype=np.float32).reshape(self.horizon, self.action_dim)
                 / 7.0 + self.n_infer)
            self.n_infer += 1
            rep = {"actions": a[:16], "actions_full": a, "subtask": "s", "infer_ms": 1.0,
                   "recv_state_sha": C.array_sha(np.asarray(p["state"])),
                   "recv_instruction_sha": C.sha256_bytes(p["instruction"].encode())}
        rep["req_sha"] = req
        return rep, raw, b"r" + raw

    def close(self):
        self.closed = True


class ListRecorder:
    def __init__(self):
        self.events, self.arrays, self.frames, self.phases = [], [], {"front": 0, "wrist": 0}, []

    def set_phase(self, p):
        self.phases.append(p)

    def add_frames(self, stream, frames, *, tag=""):
        n = len(frames)
        i0 = self.frames[stream]
        self.frames[stream] += n
        return list(range(i0, i0 + n))

    def add_array(self, name, arr, *, step=None):
        self.arrays.append((name, step, np.array(arr, copy=True)))

    def add_event(self, ev):
        self.events.append(ev)


IDENT = {"task": "PickXtimes", "source_episode": 3, "seed": 510300, "builder_episode": 0}


def _run(session, conn=None, rec=None, **kw):
    conn = conn or FakeConn()
    rec = rec or ListRecorder()
    out = C.run_episode(session, IDENT, {"host": "x", "port": 0}, rec, conn=conn, **kw)
    return out, conn, rec


# ------------------------------------------------------------------ 纯函数层
def test_hard_bound_and_error_string():
    assert C.hard_bound(1300, 16) == 84
    assert C.timeout_error(84) == "策略循环 hard_bound=84 用尽，环境未报终态"


def test_encode_functions_match_upstream_source():
    """encode_frames / encode_states / _to_uint8_hwc / _to_f32 / _scalar 与上游 robomme_env.py 逐字相同。"""
    up = ast.parse(UPSTREAM_ENV.read_text())
    mine = ast.parse((EVAL_DIR / "smvla_client.py").read_text())

    def funcs(tree):
        return {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}

    fu, fm = funcs(up), funcs(mine)
    for name in ("_to_uint8_hwc", "_to_f32", "encode_frames", "encode_states", "_scalar"):
        assert fu[name] == fm[name], name


def test_step_chunk_float64_first8_and_stop_mid_chunk():
    s = FakeSession(terminal_at=(5, "success"))
    chunk = (np.arange(16 * 9, dtype=np.float32).reshape(16, 9) / 3.0)
    got = []
    res = C.step_chunk(s, chunk, on_exec=got.append)
    assert res["consumed"] == 5 and res["done"] and res["success"] and res["status"] == "success"
    assert len(s.actions) == 5 and len(res["frames"]) == 5
    for i, a in enumerate(s.actions):
        assert a.dtype == np.float64 and a.shape == (8,)
        np.testing.assert_array_equal(a, np.asarray(chunk[i], dtype=np.float64)[:8])
        assert got[i] is a or np.array_equal(got[i], a)


def test_step_chunk_obs_none():
    s = FakeSession(obs_none_at=3)
    res = C.step_chunk(s, np.zeros((16, 8), np.float32))
    assert res["consumed"] == 3 and res["done"] and res["status"] == "error"
    assert res["error_message"] == "sim broke" and len(res["frames"]) == 2


# ------------------------------------------------------------------ 整局语义
def test_message_sequence_success_mid_chunk():
    s = FakeSession(n_demo=3, terminal_at=(20, "success"))
    out, conn, rec = _run(s)
    kinds = [k for k, _ in conn.log]
    assert kinds == ["reset", "observe", "infer", "observe", "infer", "observe"]
    assert len(conn.log[1][1]["frames"]) == 4  # 3 演示帧 + 初始帧
    assert conn.log[0][1]["episode_key"] == "PickXtimes/3/510300"
    assert out["status"] == "success" and out["task_success"] and out["steps"] == 20
    assert out["error"] is None and out["decisions"] == 2
    # 第一次推理的状态 = 初始帧状态（7 关节 + 夹爪第 1 维，float32）
    st0 = conn.log[2][1]["state"]
    assert st0.dtype == np.float32
    np.testing.assert_array_equal(st0, np.array([3, 4, 5, 6, 7, 8, 9, 3.04], dtype=np.float32))
    assert conn.log[2][1]["instruction"] == "pick the cube"
    # 第二次推理状态 = 第 16 步返回的状态
    np.testing.assert_array_equal(conn.log[4][1]["state"][:7], np.arange(7, dtype=np.float32) + 1016)
    ex = [a for n, _, a in rec.arrays if n == "exec_action"]
    ma = [a for n, _, a in rec.arrays if n == "model_action"]
    assert len(ex) == 20 and len(ma) == 2 and ma[0].shape == (32, 8)
    assert [st for n, st, _ in rec.arrays if n == "exec_action"] == list(range(20))
    assert rec.phases == ["reset", "run"]
    assert rec.frames == {"front": 24, "wrist": 24}


def test_env_reported_timeout_1301():
    s = FakeSession(terminal_at=(1301, "timeout"))
    out, conn, _ = _run(s)
    assert out["status"] == "timeout" and out["steps"] == 1301 and out["error"] is None
    assert out["decisions"] == 82


def test_env_never_terminal_hard_bound_1344():
    s = FakeSession()
    out, conn, _ = _run(s)
    assert out["status"] == "timeout" and out["steps"] == 1344
    assert out["error"] == "策略循环 hard_bound=84 用尽，环境未报终态"
    assert conn.n_infer == 84 and len(s.actions) == 1344


def test_obs_none_error():
    s = FakeSession(obs_none_at=18)
    out, _, _ = _run(s)
    assert out["status"] == "error" and out["error"] == "sim broke" and out["steps"] == 18


def test_step_exception_like_pool():
    s = FakeSession(raise_at=20)
    out, _, _ = _run(s)
    assert out["status"] == "error" and out["error"] == "step_exc: boom" and out["steps"] == 16


def test_fail_status():
    out, _, _ = _run(FakeSession(terminal_at=(40, "fail")))
    assert out["status"] == "fail" and not out["task_success"] and out["steps"] == 40


def test_reset_failure_retries_then_error():
    class Bad(FakeSession):
        def reset(self):
            self.resets += 1
            raise RuntimeError("no scene")

    s = Bad()
    out, conn, _ = _run(s)
    assert s.resets == 3 and out["status"] == "error" and conn.log == []
    assert out["error"].startswith("reset 失败：{'ok': False, 'reason': 'reset_failed: RuntimeError: no scene'}")


def test_protocol_mismatch_is_error():
    class BadConn(FakeConn):
        def call(self, msg):
            rep, raw, rr = super().call(msg)
            if "observe" in msg:
                rep["frame_sha"] = [{"front": "x", "wrist": "y"}] * rep["n"]
            return rep, raw, rr

    out, _, _ = _run(FakeSession(terminal_at=(5, "success")), conn=BadConn())
    assert out["status"] == "error" and out["protocol"]["broken"] and "ProtocolError" in out["error"]


# ------------------------------------------------------------------ to_full / state_norm 与上游逐位相同
def test_closures_verbatim_vs_upstream_ast():
    up = ast.parse(UPSTREAM_EVAL.read_text())
    rg = next(n for n in up.body if isinstance(n, ast.FunctionDef) and n.name == "run_group")
    mine = ast.parse((EVAL_DIR / "smvla_server.py").read_text())
    mc = next(n for n in mine.body if isinstance(n, ast.FunctionDef) and n.name == "make_closures")
    up_stmts = [ast.dump(n) for n in rg.body[1:5]]
    # make_closures：docstring、import torch 之后四条语句
    my_stmts = [ast.dump(n) for n in mc.body if not (isinstance(n, ast.Expr) or isinstance(n, ast.Import))][:4]
    assert up_stmts == my_stmts


class _Norm:
    def normalize(self, t):
        import torch

        return (t - torch.tensor([0.5] * 8)) / torch.tensor([2.0] * 8)


class _Buf:
    image_keys = ["observation.images.front", "observation.images.wrist"]


class _Batched:
    device = "cpu"


def test_closures_bitwise_equal_on_same_input():
    import torch

    ns_up: dict = {"np": np, "torch": torch}
    up_src = UPSTREAM_EVAL.read_text()
    tree = ast.parse(up_src)
    rg = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_group")
    fn = ast.FunctionDef(name="_mk", args=ast.parse("def f(buffer_factory, normalize_state, batched): pass").body[0].args,
                         body=rg.body[1:5] + [ast.parse("return to_full, state_norm").body[0]],
                         decorator_list=[], returns=None)
    mod = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    exec(compile(mod, str(UPSTREAM_EVAL), "exec"), ns_up)
    up_full, up_norm = ns_up["_mk"](_Buf, _Norm(), _Batched())

    S = _load("smvla_server_under_test", EVAL_DIR / "smvla_server.py")
    my_full, my_norm = S.make_closures(_Buf, _Norm(), _Batched())

    rng = np.random.default_rng(0)
    fr = {"front": rng.integers(0, 256, (8, 8, 3)).astype(np.uint8),
          "wrist": rng.integers(0, 256, (8, 8, 3)).astype(np.uint8), "extra": np.ones((2, 2, 3), np.uint8)}
    a, b = up_full(fr), my_full(fr)
    assert list(a) == list(b) == ["observation.images.front", "observation.images.wrist", "extra"]
    for k in a:
        assert a[k].dtype == b[k].dtype and np.array_equal(a[k], b[k])
    st = rng.standard_normal(8).astype(np.float32)
    x, y = up_norm(st), my_norm(st)
    assert x.shape == y.shape == (1, 8) and x.dtype == y.dtype and torch.equal(x, y)
    assert ns_up["_mk"](_Buf, None, _Batched())[1](st) is None
    assert S.make_closures(_Buf, None, _Batched())[1](st) is None


# ------------------------------------------------------------------ 真 websocket 往返
def test_real_websocket_roundtrip():
    from openpi_client import msgpack_numpy
    import websockets.asyncio.server as _server

    seen = []
    ready = threading.Event()
    holder = {}

    async def handler(ws):
        packer = msgpack_numpy.Packer()
        await ws.send(packer.pack({"policy": "fake"}))
        n = 0
        async for raw in ws:
            msg = msgpack_numpy.unpackb(raw)
            kind = next(iter(msg))
            seen.append(kind)
            rep = {"req_sha": hashlib.sha256(raw).hexdigest()}
            if kind == "observe":
                frs = msg["observe"]["frames"]
                rep.update(n=len(frs), frame_sha=[{k: C.frame_sha(v) for k, v in sorted(f.items())} for f in frs])
            elif kind == "infer":
                p = msg["infer"]
                a = np.full((32, 8), 0.25 + n, dtype=np.float32)
                n += 1
                rep.update(actions=a[:16], actions_full=a, subtask="t", infer_ms=2.0,
                           recv_state_sha=C.array_sha(p["state"]),
                           recv_instruction_sha=C.sha256_bytes(p["instruction"].encode()))
            await ws.send(packer.pack(rep))

    def serve():
        async def main():
            async with _server.serve(handler, "127.0.0.1", 0, compression=None, max_size=None) as srv:
                holder["port"] = srv.sockets[0].getsockname()[1]
                holder["loop"] = asyncio.get_running_loop()
                holder["stop"] = asyncio.Event()
                ready.set()
                await holder["stop"].wait()

        asyncio.run(main())

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    assert ready.wait(10)
    try:
        s = FakeSession(terminal_at=(17, "success"))
        rec = ListRecorder()
        out = C.run_episode(s, IDENT, {"host": "127.0.0.1", "port": holder["port"]}, rec)
    finally:
        holder["loop"].call_soon_threadsafe(holder["stop"].set)
        t.join(5)
    assert out["status"] == "success" and out["steps"] == 17, out
    assert seen == ["reset", "observe", "infer", "observe", "infer", "observe"]
    assert out["protocol"]["sha_mismatch"] == 0 and out["protocol"]["frames_sent"] == 4 + 16 + 1
    assert all(len(e["send_sha256"]) == 64 for e in rec.events if e.get("kind") == "msg")
    np.testing.assert_array_equal(s.actions[0], np.full(8, 0.25, dtype=np.float64))
    np.testing.assert_array_equal(s.actions[16], np.full(8, 1.25, dtype=np.float64))


# ------------------------------------------------------------------ infra 标记（env_client 据此重试）
class _ErrConn(FakeConn):
    def __init__(self, err, on="infer"):
        super().__init__()
        self.err, self.on = err, on

    def call(self, msg):
        rep, raw, rr = super().call(msg)
        if self.on in msg:
            rep = {"error": self.err, "req_sha": rep["req_sha"]}
        return rep, raw, rr


def test_normal_outcomes_not_infra():
    for sess in (FakeSession(terminal_at=(20, "success")), FakeSession(terminal_at=(40, "fail")),
                 FakeSession(), FakeSession(obs_none_at=18), FakeSession(raise_at=20)):
        out, _, _ = _run(sess)
        assert out["infra"] is False and out["infra_reason"] is None, out


def test_server_error_oom_and_plain_are_infra():
    out, _, _ = _run(FakeSession(), conn=_ErrConn("torch.cuda.OutOfMemoryError: CUDA out of memory"))
    assert out["status"] == "error" and out["infra"] and out["infra_reason"] == "server_oom"
    out, _, _ = _run(FakeSession(), conn=_ErrConn("KeyError: 'x'"))
    assert out["status"] == "error" and out["infra"] and out["infra_reason"] == "server_error"


def test_protocol_mismatch_is_infra():
    class BadConn(FakeConn):
        def call(self, msg):
            rep, raw, rr = super().call(msg)
            rep["req_sha"] = "0" * 64
            return rep, raw, rr

    out, _, _ = _run(FakeSession(), conn=BadConn())
    assert out["infra"] and out["infra_reason"] == "protocol" and out["protocol"]["broken"]


def test_connection_refused_is_infra():
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # 端口无人监听
    out = C.run_episode(FakeSession(), IDENT, {"host": "127.0.0.1", "port": port}, ListRecorder())
    assert out["status"] == "error" and out["infra"] and out["infra_reason"].startswith("connection:"), out


def test_connection_closed_is_infra():
    class Closing(FakeConn):
        def call(self, msg):
            from websockets.exceptions import ConnectionClosedError

            if "infer" in msg:
                raise ConnectionClosedError(None, None)
            return super().call(msg)

    out, _, _ = _run(FakeSession(), conn=Closing())
    assert out["infra"] and out["infra_reason"] == "connection:ConnectionClosedError"


def test_reset_vulkan_is_infra_but_plain_reset_failure_not():
    class Vk(FakeSession):
        def reset(self):
            raise RuntimeError("svulkan2 failed to create device")

    class Bad(FakeSession):
        def reset(self):
            raise RuntimeError("no scene")

    out, _, _ = _run(Vk())
    assert out["status"] == "error" and out["infra"] and out["infra_reason"] == "env_reset:svulkan2"
    out, _, _ = _run(Bad())
    assert out["status"] == "error" and out["infra"] is False


# ------------------------------------------------------------------ server 预热后随机状态恢复（CPU 假模型）
def _fake_host(S, monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    class Buf:
        image_keys = ["observation.images.front", "observation.images.wrist"]

        def reset(self):
            pass

        def observe(self, fr):
            pass

        def _prepare_inputs(self, prompt):
            return {}

    class Batched:
        device = "cpu"

        def generate_batch(self, processed, states):
            torch.randn(4)  # 消耗随机数，模拟 DiT 采样
            return [(np.zeros((32, 8), np.float32), "s")]

    host = object.__new__(S.SMVLAPolicyHost)
    host.buffer_factory = Buf
    host.batched = Batched()
    host.to_full = lambda fr: fr
    host.state_norm = lambda s: None
    host.metadata = {}
    S.reseed()
    host.rng_ref = S.rng_digest()
    return host


def test_warmup_rng_restored_is_meaningful(monkeypatch):
    S = _load("smvla_server_rng_test", EVAL_DIR / "smvla_server.py")
    w = _fake_host(S, monkeypatch).warmup()
    assert w["rng_consumed_by_warmup"] and w["rng_restored"]
    host = _fake_host(S, monkeypatch)
    monkeypatch.setattr(S, "reseed", lambda: None)  # 每局重设失效时必须报 False
    w = host.warmup()
    assert w["rng_consumed_by_warmup"] and not w["rng_restored"]
