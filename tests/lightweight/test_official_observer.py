"""旧官方录制器（official_observer）的无仿真夹具：透明代理逐字节转发、帧类型与顺序、>16 MiB 大消息、对账工具。"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
OBS = ROOT / "scripts/eval-official/official_observer"

websockets = pytest.importorskip("websockets")
msgpack_numpy = pytest.importorskip("openpi_client.msgpack_numpy")
from websockets.asyncio.server import serve  # noqa: E402
import websockets.sync.client as wsc  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _sha(m):
    return hashlib.sha256(m.encode() if isinstance(m, str) else m).hexdigest()


class ToyServer:
    """仿官方 server：连上先发 metadata 帧；二进制消息回 msgpack 应答，文本消息回文本；可主动推一帧 >16 MiB。"""

    def __init__(self, port):
        self.port = port
        self.received: list[tuple[str, str]] = []
        self.sent: list[tuple[str, str]] = []
        self._ready = threading.Event()
        self._loop = None
        self._stop = None
        self._t = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)
        self._t.start()
        assert self._ready.wait(10)

    async def _send(self, ws, m):
        await ws.send(m)
        self.sent.append(("text" if isinstance(m, str) else "binary", _sha(m)))

    async def _handler(self, ws):
        packer = msgpack_numpy.Packer()
        await self._send(ws, packer.pack({"meta": "toy", "n": np.int64(3)}))
        async for m in ws:
            self.received.append(("text" if isinstance(m, str) else "binary", _sha(m)))
            if isinstance(m, str):
                await self._send(ws, "echo:" + m)
                continue
            obj = msgpack_numpy.unpackb(m)
            if obj.get("die"):  # 模拟 server 侧保活超时断开
                await ws.close(code=1011, reason="keepalive ping timeout")
                return
            if obj.get("big"):
                await self._send(ws, packer.pack({"actions": np.ones((17 * 1024 * 1024 // 4,), np.float32)}))
            elif obj.get("reset"):
                await self._send(ws, packer.pack({"reset_finished": True}))
            else:
                await self._send(ws, packer.pack({"actions": np.arange(16 * 8, dtype=np.float32).reshape(16, 8)}))

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        async with serve(self._handler, "127.0.0.1", self.port, compression=None, max_size=None):
            self._ready.set()
            await self._stop.wait()

    def close(self):
        self._loop.call_soon_threadsafe(self._stop.set)
        self._t.join(10)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    up, lp = _free_port(), _free_port()
    srv = ToyServer(up)
    rec_root = tmp_path / "rec"
    rec_root.mkdir()
    env = dict(os.environ, PYTHONPATH=str(ROOT / "third_party/mme-vla/packages/openpi-client/src"))
    proxy = subprocess.Popen([sys.executable, str(OBS / "mme_proxy.py"), "--listen", str(lp), "--upstream", str(up),
                              "--log-dir", str(rec_root / "proxy")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env=env)
    line = proxy.stdout.readline()
    assert line.startswith("PROXY_READY"), line
    # 客户端钩子：与 mme_client_wrap 同一实现，测完还原
    monkeypatch.setenv("REC_ROOT", str(rec_root))
    wrap = _load("v75_mme_client_wrap_t", OBS / "mme_client_wrap.py")
    wrap._state["root"] = rec_root
    orig = (wsc.ClientConnection.send, wsc.ClientConnection.recv)
    wrap._patch_ws(wsc)
    yield srv, lp, rec_root, proxy, wrap
    wsc.ClientConnection.send, wsc.ClientConnection.recv = orig
    if proxy.poll() is None:
        proxy.terminate()
        proxy.wait(60)
    srv.close()


def _stop_proxy(proxy):
    proxy.terminate()
    out, _ = proxy.communicate(timeout=120)
    assert "PROXY_STOPPED" in out


def _connect(lp):
    return wsc.connect(f"ws://127.0.0.1:{lp}", compression=None, max_size=None, ping_timeout=600,
                       open_timeout=60, close_timeout=60)


def test_proxy_byte_transparency_and_checker(rig):
    srv, lp, rec_root, proxy, wrap = rig
    packer = msgpack_numpy.Packer()
    client_sent, client_recv = [], []
    for episode in range(2):  # 每局新连接，与官方客户端一致
        ws = _connect(lp)
        client_recv.append(_sha(ws.recv()))  # metadata 帧
        msgs = [packer.pack({"reset": True}),
                packer.pack({"images": np.random.default_rng(episode).integers(0, 256, (5, 1, 8, 8, 3), dtype=np.uint8),
                             "state": np.zeros((5, 8), np.float32), "add_buffer": True, "exec_start_idx": 4}),
                "plain-text-frame",
                packer.pack({"observation/state": np.ones(8, np.float32), "prompt": "pick"}),
                packer.pack({"big": True, "pad": np.zeros(17 * 1024 * 1024, np.uint8).reshape(-1, 1024, 1024, 1)})]
        for m in msgs:
            ws.send(m)
            client_sent.append(_sha(m))
            r = ws.recv()
            client_recv.append(_sha(r))
            if isinstance(m, str):
                assert isinstance(r, str) and r == "echo:" + m  # 文本帧仍是文本帧
            else:
                assert isinstance(r, bytes)
        ws.close()
    time.sleep(0.5)
    _stop_proxy(proxy)
    # 两端逐字节一致：server 收到的 == 客户端发出的；客户端收到的 == server 发出的（顺序相同）
    assert [s for _, s in srv.received] == client_sent
    assert [s for _, s in srv.sent] == client_recv
    ck = _load("v75_transparency_t", OBS / "transparency_check.py")
    rep = ck.check(rec_root)
    assert rep["OBSERVER_TRANSPARENT"] == "PASS", rep
    assert rep["messages"] == len(client_sent) + len(client_recv) and rep["mismatch"] == 0 and rep["conns"] == 2
    assert ck.verdict_line(rep).startswith("OBSERVER_TRANSPARENT=PASS messages=22 mismatch=0")
    # 代理按连接写的数组目录：动作、状态原样可读回，图像只记 sha
    conns = sorted((rec_root / "proxy").glob("conn-*"))
    assert len(conns) == 2
    z = np.load(conns[0] / "arrays.npz")
    acts = [k for k in z.files if k.startswith("s2c.actions")]
    assert np.array_equal(z[acts[0]], np.arange(128, dtype=np.float32).reshape(16, 8))
    evs = [json.loads(l) for l in (conns[0] / "events.jsonl").read_text().splitlines()]
    img_ev = [e for e in evs if e.get("kind") == "msg" and "images" in e.get("fields", {})][0]
    assert len(img_ev["fields"]["images"]["frame_sha256"]) == 5
    assert json.loads((conns[0] / "summary.json").read_text())["RECORDER_VERIFY"] == "PASS"
    # 篡改代理日志一条 → 对账 FAIL
    plog = next((rec_root / "proxy").glob("proxy-*.jsonl"))
    lines = plog.read_text().splitlines()
    for i, l in enumerate(lines):
        r = json.loads(l)
        if r.get("kind") == "msg" and r["dir"] == "c2s":
            r["sha256"] = "0" * 64
            lines[i] = json.dumps(r)
            break
    plog.write_text("\n".join(lines) + "\n")
    rep2 = ck.check(rec_root)
    assert rep2["OBSERVER_TRANSPARENT"] == "FAIL" and rep2["mismatch"] >= 1


def test_proxy_forwards_server_error_text_and_close(tmp_path, rig):
    srv, lp, rec_root, proxy, wrap = rig
    ws = _connect(lp)
    ws.recv()
    ws.send("x")
    assert ws.recv() == "echo:x"
    ws.close()
    time.sleep(0.3)
    _stop_proxy(proxy)
    ck = _load("v75_transparency_t2", OBS / "transparency_check.py")
    rep = ck.check(rec_root)
    assert rep["OBSERVER_TRANSPARENT"] == "PASS" and rep["messages"] == 3


def test_checker_detects_missing_and_reordered(tmp_path):
    ck = _load("v75_transparency_t3", OBS / "transparency_check.py")
    root = tmp_path
    (root / "proxy").mkdir()
    c = [{"pid": 1, "conn": 0, "dir": "recv", "idx": 0, "type": "binary", "len": 3, "sha256": "a"},
         {"pid": 1, "conn": 0, "dir": "send", "idx": 0, "type": "binary", "len": 3, "sha256": "b"},
         {"pid": 1, "conn": 0, "dir": "send", "idx": 1, "type": "text", "len": 3, "sha256": "c"}]
    p = [{"kind": "msg", "conn": 0, "dir": "s2c", "idx": 0, "type": "binary", "len": 3, "sha256": "a"},
         {"kind": "msg", "conn": 0, "dir": "c2s", "idx": 0, "type": "text", "len": 3, "sha256": "c"},
         {"kind": "msg", "conn": 0, "dir": "c2s", "idx": 1, "type": "binary", "len": 3, "sha256": "b"}]
    (root / "client-transport-1.jsonl").write_text("".join(json.dumps(x) + "\n" for x in c))
    (root / "proxy/proxy-9.jsonl").write_text("".join(json.dumps(x) + "\n" for x in p))
    rep = ck.check(root)
    assert rep["OBSERVER_TRANSPARENT"] == "FAIL" and rep["mismatch"] == 2  # 顺序互换 → 两条不符
    (root / "proxy/proxy-9.jsonl").write_text("".join(json.dumps(x) + "\n" for x in [p[0], p[2]]))
    rep = ck.check(root)
    assert rep["OBSERVER_TRANSPARENT"] == "FAIL"  # 缺一条


def test_post_import_hooks_preserve_order(tmp_path, monkeypatch):
    common = _load("v75_obs_common_t", OBS / "_v75_obs_common.py")
    pkg = tmp_path / "hookpkg_v75"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod_a.py").write_text("ORDER = []\nclass K:\n    def f(self, x):\n        return x + 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    seen = []

    def hook(m):
        seen.append(m.__name__)
        orig = m.K.f
        m.K.f = lambda self, x: orig(self, x)

    h = common.PostImportHooks({"hookpkg_v75.mod_a": hook})
    h.install()
    try:
        assert "hookpkg_v75.mod_a" not in sys.modules  # 装钩子不提前导入
        import hookpkg_v75.mod_a as ma

        assert seen == ["hookpkg_v75.mod_a"] and ma.K().f(1) == 2
    finally:
        if h in sys.meta_path:
            sys.meta_path.remove(h)


def test_smvla_wrap_patches_live_run_group(tmp_path, monkeypatch):
    """回归：run_group 补丁必须打在活模块命名空间上（runpy.run_module 返回的是副本，补丁无效）。"""
    pkg = tmp_path / "fake_smvla_pkg_v75"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "eval_success.py").write_text(
        "import sys\nCALLS = []\n"
        "def run_group(args, pool, batched, buffer_factory, normalize_state, task, specs, **kw):\n"
        "    CALLS.append((task, specs[0]['episode']))\n    return [True]\n"
        "def main():\n"
        "    run_group(None, None, None, None, None, 'PickXtimes', [{'task': 'PickXtimes', 'episode': 3}], details=[])\n"
        "if __name__ == '__main__':\n    raise SystemExit('不应以 __main__ 执行')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    rec_root = tmp_path / "rec"
    monkeypatch.setenv("REC_ROOT", str(rec_root))
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    wrap = _load("v75_smvla_wrap_t", OBS / "smvla_wrap.py")
    wrap._state["root"] = rec_root
    rec_root.mkdir()
    wrap.run_observed("fake_smvla_pkg_v75.eval_success", [], {("PickXtimes", 3): 510300})
    mod = sys.modules["fake_smvla_pkg_v75.eval_success"]
    assert mod.CALLS == [("PickXtimes", 3)]
    idx = [json.loads(l) for l in (rec_root / "recorder-index.jsonl").read_text().splitlines()]
    assert idx[0]["episode"] == "PickXtimes_3_510300" and idx[0]["RECORDER_VERIFY"] == "PASS"


def test_proxy_propagates_upstream_close_code_and_reason(rig):
    srv, lp, rec_root, proxy, wrap = rig
    ws = _connect(lp)
    ws.recv()
    ws.send(msgpack_numpy.Packer().pack({"die": True}))
    with pytest.raises(websockets.ConnectionClosedError):
        ws.recv()
    assert ws.close_code == 1011 and ws.close_reason == "keepalive ping timeout"


def test_proxy_rejects_handshake_when_upstream_down(tmp_path):
    lp, dead = _free_port(), _free_port()
    proxy = subprocess.Popen([sys.executable, str(OBS / "mme_proxy.py"), "--listen", str(lp), "--upstream", str(dead),
                              "--log-dir", str(tmp_path / "proxy")], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
    try:
        assert proxy.stdout.readline().startswith("PROXY_READY")
        with pytest.raises(websockets.InvalidStatus) as ei:
            _connect(lp)
        assert ei.value.response.status_code == 503
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{lp}/healthz", timeout=10) as r:  # 照官方 server 的健康检查
            assert r.status == 200
    finally:
        proxy.terminate()
        proxy.wait(60)


def test_proxy_keepalive_settings_mirror_history():
    """两跳的保活参数照抄历史两端：面向客户端 = server 默认 20/20；面向上游 = 官方客户端 20/600。"""
    src = (OBS / "mme_proxy.py").read_text()
    assert "ping_timeout=600, open_timeout=60, close_timeout=60" in src
    assert "ping_interval=None" not in src
    import inspect
    from openpi_client import websocket_client_policy as wcp

    assert "ping_timeout=600, open_timeout=60, close_timeout=60" in inspect.getsource(wcp.WebsocketClientPolicy._wait_for_server)


def test_smvla_pool_hooks_record_in_main_thread(tmp_path, monkeypatch):
    """InProcSimPool 钩子：在主线程从返回 dict 录制；exec_action = float64 各行 [:8]，按 consumed 截取。"""
    import types

    rec_root = tmp_path / "rec"
    rec_root.mkdir()
    monkeypatch.setenv("REC_ROOT", str(rec_root))
    wrap = _load("v75_smvla_wrap_t2", OBS / "smvla_wrap.py")
    wrap._state["root"] = rec_root
    threads = []
    img = np.zeros((4, 4, 3), np.uint8)

    class FakePool:
        num_envs = 1

        def reset(self, specs):
            threads.append(threading.get_ident())
            return [{"ok": True, "episode": 3, "instruction": "go", "frames": [{"front": img, "wrist": img + 1}] * 2,
                     "states": [np.zeros(8, np.float32)] * 2, "max_steps": 1300}]

        def step(self, action_chunks, active):
            return [{"frames": [{"front": img + 2, "wrist": img + 3}] * 3, "states": [np.ones(8, np.float32)] * 3,
                     "consumed": 3, "done": True, "success": True, "status": "success", "error_message": None}]

    mod = types.SimpleNamespace(InProcSimPool=FakePool)
    wrap._patch_pool(mod)
    rec = wrap.R.EpisodeRecorder(rec_root / "ep", {}, free_gib_fn=lambda p: 4000.0)
    wrap._state.update(rec=rec, step=0, decision=0)
    pool = FakePool()
    pool.reset([{"task": "PickXtimes", "episode": 3}])
    chunk = np.arange(16 * 9, dtype=np.float32).reshape(16, 9)
    out = pool.step([chunk], [0])
    assert out[0]["consumed"] == 3
    wrap._state["rec"] = None
    res = rec.close({})
    assert res["RECORDER_VERIFY"] == "PASS" and res["frames"] == 10
    z = np.load(rec_root / "ep/arrays.npz")
    assert np.array_equal(z["exec_action__00000"], chunk[:3, :8].astype(np.float64))
    assert np.array_equal(z["action_chunk__00000"], chunk)
