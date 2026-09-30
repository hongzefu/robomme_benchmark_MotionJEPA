"""``scripts/eval-official/mme_client.py`` 的纯 CPU 测试（合成观测，不起仿真、不起真 server）。

覆盖：与子模块 ``examples/robomme`` 源码逐 AST 相同（pack_buffer、EpisodeState、pack_state）；消息序列
reset → add_buffer(全部 pre_traj) → infer → …；horizon 16；最后不足一个 horizon；server 回不足 16 个动作；
obs=None／env.step 异常／非正常终态的 error 语义；环境不报终态直到上限（timeout 1301）；timeout 先于终态判断；
真 websocket 往返 + 透明中继 + ``transport_check``。
"""
from __future__ import annotations

import ast
import importlib.util
import json
import socket
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
EO = REPO / "scripts" / "eval-official"
SUB = REPO / "third_party" / "mme-vla" / "examples" / "robomme"


def _load(name: str, alias: str):
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, EO / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load("mme_client", "mme_client")


# ── 与子模块源码逐 AST 相同 ────────────────────────────────────────────────


def _defs(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out[node.name] = ast.dump(_strip_doc(node))
    return out


def _strip_doc(node):
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str):
            n.body = n.body[1:] or [ast.Pass()]
    return node


@pytest.mark.skipif(not SUB.exists(), reason="子模块未检出")
def test_照抄部分与子模块逐AST相同():
    mine = _defs(EO / "mme_client.py")
    utils = _defs(SUB / "utils.py")
    runner = _defs(SUB / "env_runner.py")
    assert mine["pack_buffer"] == utils["pack_buffer"]
    assert mine["EpisodeState"] == utils["EpisodeState"]
    assert mine["pack_state"] == runner["pack_state"]


# ── 假 client / 假 env ────────────────────────────────────────────────────


class FakeClient:
    def __init__(self, n_actions=50, dim=8):
        self.calls = []
        self.n_actions = n_actions
        self.dim = dim
        self.k = 0

    def reset(self):
        self.calls.append(("reset",))
        return {"reset_finished": True, "reset_time_ms": 0.1}

    def add_buffer(self, buf):
        self.calls.append(("add_buffer", buf))
        return {"add_buffer_finished": True}

    def infer(self, obs):
        self.calls.append(("infer", obs))
        self.k += 1
        a = np.full((self.n_actions, self.dim), float(self.k), dtype=np.float32)
        a[:, 0] = np.arange(self.n_actions) + 1000 * self.k
        return {"actions": a, "infer_time_ms": 1.0}


def _frame(v):
    return np.full((4, 4, 3), v % 256, dtype=np.uint8)


class FakeEnv:
    """reset 给 demo 帧 + 初始帧；step 返回第 n 帧；可配置第几步报终态／异常／obs None。"""

    def __init__(self, demo=3, end_at=None, end_status="success", raise_at=None, none_at=None, status="ongoing"):
        self.demo, self.end_at, self.end_status = demo, end_at, end_status
        self.raise_at, self.none_at, self.status = raise_at, none_at, status
        self.n = 0
        self.actions = []

    def obs(self, vals):
        return {"front_rgb_list": [_frame(v) for v in vals], "wrist_rgb_list": [_frame(v + 100) for v in vals],
                "joint_state_list": [np.full(7, v, dtype=np.float64) for v in vals],
                "gripper_state_list": [np.array([v, -v], dtype=np.float64) for v in vals],
                "eef_state_list": [np.zeros(6) for _ in vals]}

    def reset(self):
        return self.obs(list(range(self.demo + 1))), {"task_goal": ["pick the cube"], "status": "ongoing"}

    def step(self, action):
        self.n += 1
        self.actions.append(action)
        if self.raise_at == self.n:
            raise RuntimeError("svulkan2 boom")
        if self.none_at == self.n:
            return None, 0.0, True, True, {"status": "error"}
        done = self.end_at == self.n
        return (self.obs([1000 + self.n]), 0.0, done, False,
                {"status": self.end_status if done else self.status})


def _run(env, client=None, max_steps=1300):
    client = client or FakeClient()
    res = M.evaluate_one(lambda: client, env.step, lambda: M.pre_traj_from_reset(*env.reset()), max_steps=max_steps)
    return res, client


def test_消息序列_reset_addbuffer全部pretraj_infer():
    env = FakeEnv(demo=3, end_at=20)
    res, c = _run(env)
    assert [k[0] for k in c.calls[:3]] == ["reset", "add_buffer", "infer"]
    buf = c.calls[1][1]
    assert buf["images"].shape == (4, 1, 4, 4, 3) and buf["images"].dtype == np.uint8
    assert buf["state"].shape == (4, 8) and buf["state"].dtype == np.float32
    assert buf["exec_start_idx"] == 3 and buf["add_buffer"] is True
    inf = c.calls[2][1]
    assert set(inf) == {"observation/image", "observation/wrist_image", "observation/state", "prompt"}
    assert np.array_equal(inf["observation/image"], _frame(3)) and inf["prompt"] == "pick the cube"
    assert inf["observation/state"].dtype == np.float32 and inf["observation/state"][7] == 3
    # 第二次决策：16 帧、exec_start_idx=0、infer 用第 16 步的帧
    buf2 = c.calls[3][1]
    assert c.calls[3][0] == "add_buffer" and buf2["images"].shape[0] == 16 and buf2["exec_start_idx"] == 0
    assert np.array_equal(c.calls[4][1]["observation/image"], _frame(1016))
    assert res["status"] == "success" and res["steps"] == 20 and res["error"] is None
    # 执行动作 = 模型动作前 16 行，原样
    assert env.actions[0][0] == 1000 and env.actions[15][0] == 1015 and env.actions[16][0] == 2000


def test_环境不报终态直到上限_timeout_1301():
    env = FakeEnv(demo=0, end_at=None)
    res, c = _run(env)
    assert res["status"] == "timeout" and res["steps"] == 1301 and env.n == 1301
    assert sum(1 for k in c.calls if k[0] == "infer") == 82
    assert res["decisions"] == 82


def test_timeout先于终态判断():
    env = FakeEnv(demo=0, end_at=1301, end_status="success")
    res, _ = _run(env)
    assert res["status"] == "timeout" and res["steps"] == 1301
    env = FakeEnv(demo=0, end_at=1300, end_status="fail")
    res, _ = _run(env)
    assert res["status"] == "fail" and res["steps"] == 1300


def test_最后不足一个horizon与server回不足16个():
    env = FakeEnv(demo=1, end_at=37)
    res, c = _run(env)
    assert res["steps"] == 37 and sum(1 for k in c.calls if k[0] == "infer") == 3
    env = FakeEnv(demo=1, end_at=25)
    res, c = _run(env, FakeClient(n_actions=10))
    assert res["steps"] == 25 and sum(1 for k in c.calls if k[0] == "infer") == 3
    assert c.calls[3][1]["images"].shape[0] == 10


def test_env_step异常_照旧官方落成AttributeError():
    env = FakeEnv(demo=0, raise_at=5)
    res, _ = _run(env)
    assert res["status"] == "error" and res["steps"] == 5
    assert res["error"] == "AttributeError: 'NoneType' object has no attribute 'copy'"
    assert res["infra"] is True and res["infra_reason"] == "svulkan2"
    assert "svulkan2" in res["env_exception"]


def test_obs_None_照旧官方落成TypeError且步数不加():
    env = FakeEnv(demo=0, none_at=7)
    res, _ = _run(env)
    assert res["status"] == "error" and res["steps"] == 6
    assert res["error"].startswith("TypeError: 'NoneType' object is not subscriptable")


def test_非正常终态记error():
    env = FakeEnv(demo=0, end_at=3, end_status="ongoing")
    res, _ = _run(env)
    assert res["status"] == "error" and res["error"] == "success_flag=ongoing" and res["steps"] == 3
    assert res["infra"] is False


def test_连接失败记error且标基础设施():
    def boom():
        raise ConnectionRefusedError("ConnectionRefused")

    env = FakeEnv()
    res = M.evaluate_one(boom, env.step, lambda: M.pre_traj_from_reset(*env.reset()))
    assert res["status"] == "error" and res["steps"] == 0 and res["infra"] is True


def test_reset顺序_先client_reset再env_reset():
    order = []
    c = FakeClient()
    orig = c.reset

    def creset():
        order.append("client.reset")
        return orig()

    c.reset = creset
    env = FakeEnv(demo=0, end_at=1)

    def env_reset():
        order.append("env.reset")
        return M.pre_traj_from_reset(*env.reset())

    M.evaluate_one(lambda: c, env.step, env_reset)
    assert order == ["client.reset", "env.reset"]


# ── 真 websocket：假 server + 中继 + transport_check ──────────────────────


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _fake_server(port, stop):
    import asyncio

    import websockets.asyncio.server as wss
    from openpi_client import msgpack_numpy

    async def handler(ws):
        packer = msgpack_numpy.Packer()
        await ws.send(packer.pack({"meta": 1}))
        k = 0
        async for msg in ws:
            obs = msgpack_numpy.unpackb(msg)
            if obs.get("reset"):
                await ws.send(packer.pack({"reset_finished": True, "reset_time_ms": 0.5}))
            elif obs.get("add_buffer"):
                await ws.send(packer.pack({"add_buffer_finished": True, "add_buffer_time_ms": 0.5}))
            else:
                k += 1
                a = np.random.default_rng(k).normal(size=(50, 8)).astype(np.float32)
                await ws.send(packer.pack({"actions": a, "state": obs["observation/state"], "infer_time_ms": 2.0}))

    async def main():
        async with wss.serve(handler, "127.0.0.1", port, compression=None, max_size=None):
            while not stop.is_set():
                await asyncio.sleep(0.05)

    asyncio.run(main())


class _Rec:
    def __init__(self):
        self.events, self.arrays = [], []

    def add_event(self, e):
        self.events.append(json.loads(json.dumps(e)))

    def add_array(self, name, arr, step=None):
        self.arrays.append((name, step, np.array(arr)))

    def add_frames(self, *a, **k):
        return []

    def set_phase(self, p):
        pass

    def close(self, s):
        return {}


def _wait_port(port, t=10):
    end = time.time() + t
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(port)


def test_真websocket往返_中继透明_transport_check(tmp_path):
    pytest.importorskip("openpi_client")
    pytest.importorskip("websockets")
    EC = _load("env_client", "env_client")
    sport, rport = _free_port(), _free_port()
    stop = threading.Event()
    threading.Thread(target=_fake_server, args=(sport, stop), daemon=True).start()
    _wait_port(sport)
    log = tmp_path / "relay.jsonl"
    import argparse
    threading.Thread(target=M.cmd_relay, args=(argparse.Namespace(listen=rport, upstream=sport, log=str(log)),),
                     daemon=True).start()
    _wait_port(rport)

    env = FakeEnv(demo=2, end_at=40)

    class _B:
        def make_env_for_episode(self, i, max_steps=None):
            return env

    rec = _Rec()
    sess = EC.EnvSession("PickXtimes", 0, recorder=rec, builder=_B())
    sess.build()
    res = M.run_episode(sess, {"task": "PickXtimes"}, {"host": "127.0.0.1", "port": rport}, rec)
    assert res["status"] == "success" and res["steps"] == 40
    assert res["timing"]["infer"]["n"] == 3 and res["timing"]["reset"]["n"] == 1
    time.sleep(0.3)
    relay = [json.loads(l) for l in log.read_text().splitlines()]
    out = M.transport_check(rec.events, relay)
    assert out["mismatch"] == 0 and out["frames"] == 3 + 16 + 16 + 3 * 2 and out["exec_actions"] == 40, out
    # 篡改一条中继记录 → 能测出
    bad = [dict(r) for r in relay]
    bad[2]["sha"] = "0" * 64
    assert M.transport_check(rec.events, bad)["mismatch"] >= 1
    # 执行动作与模型动作不符 → 能测出
    ev2 = [dict(e) for e in rec.events]
    for e in ev2:
        if e["kind"] == "env_step_action" and e["step"] == 5:
            e["sha"] = "f" * 64
    assert M.transport_check(ev2, relay)["mismatch"] >= 1
    # 模型动作原样记进 model_action，执行动作记进 exec_action
    names = [a[0] for a in rec.arrays]
    assert names.count("model_action") == 3 and names.count("exec_action") == 40
    stop.set()
