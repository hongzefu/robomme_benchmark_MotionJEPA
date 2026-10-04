"""PonderPounce 协议对拍（slow）：真实 vla-eval 0.7.0 源码 vs 新侧 ``pp_client``，本地回环 websocket 假服务。

期望序列的独立来源：按路径加载 vla-eval 源码（``SGEVAL_VLA_EVAL_ROOT``，缺省为主检出 client-env 的
site-packages），用它的 ``SyncEpisodeRunner`` + ``RoboMMEBenchmark``（环境构建换成确定性假 builder）+
``Connection`` 跑一局，假服务逐帧记下收到的协议帧；再用同一假服务跑新侧 ``pp_client.run_episode``（同样用真实
``Connection``）与原侧 ``pp_official_runner.run_shard``，三份帧序列逐帧比对（帧类型、顺序、观测键、dtype/shape、
字节、sid、局号、seq）。vla-eval 源码缺失时测试失败，不跳过。依赖本机 artifacts，故标 slow、不进日常门禁。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import types
from pathlib import Path

import numpy as np
import pytest

from pp_fakes import REPO, FakeEnv, FakeSession, action_for, compare_frames
from tests._support.loaders import load_script

pytestmark = pytest.mark.slow

CLIENT_ENV_SITE = "artifacts/sg-evaluation/venvs/client-env/lib/python3.11/site-packages"
TASK, SRC, SEED = "VideoUnmask", 5, 98765
XH = {"task": TASK, "tier": "xhard0", "seed": SEED, "source_episode": SRC, "builder_episode": 0,
      "key": f"{TASK}_xhard0_{SEED}", "candidate": None, "spec_sha256": None}
SID = f"{TASK}|{SRC}|{SEED}"
READ_FILES = ("runners/sync_runner.py", "connection.py", "benchmarks/robomme/benchmark.py", "protocol/messages.py",
              "model_servers/serve.py")


def _vla_eval_root() -> Path:
    """``SGEVAL_VLA_EVAL_ROOT``；缺省取主检出（worktree 内按 git 公共目录回到主检出）的 client-env site-packages。"""
    env = os.environ.get("SGEVAL_VLA_EVAL_ROOT")
    if env:
        return Path(env)
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                         capture_output=True, text=True, timeout=30)
    main = Path(out.stdout.strip()).parent if out.returncode == 0 and out.stdout.strip() else REPO
    return main / CLIENT_ENV_SITE


@pytest.fixture(scope="module")
def vla(tmp_path_factory):
    root = _vla_eval_root()
    pkg = root / "vla_eval"
    if not (pkg / "runners" / "sync_runner.py").is_file():
        pytest.fail(f"vla-eval 源码不在场（设 SGEVAL_VLA_EVAL_ROOT）：{root}")
    for rel in READ_FILES:
        print(f"VLA_EVAL_SOURCE {pkg / rel} sha256={hashlib.sha256((pkg / rel).read_bytes()).hexdigest()}")
    link_dir = tmp_path_factory.mktemp("vla_eval_link")
    (link_dir / "vla_eval").symlink_to(pkg, target_is_directory=True)
    sys.path.insert(0, str(link_dir))
    from vla_eval._version import __version__
    from vla_eval.benchmarks.robomme.benchmark import RoboMMEBenchmark
    from vla_eval.connection import Connection
    from vla_eval.protocol.messages import Message, MessageType, pack_message, unpack_message
    from vla_eval.recording import NullEpisodeRecorder
    from vla_eval.runners.sync_runner import SyncEpisodeRunner

    assert __version__.startswith("0.7.0"), __version__
    RoboMMEBenchmark.configure_render("gpu")
    return types.SimpleNamespace(RoboMMEBenchmark=RoboMMEBenchmark, Connection=Connection, Message=Message,
                                 MessageType=MessageType, pack=pack_message, unpack=unpack_message,
                                 NullEpisodeRecorder=NullEpisodeRecorder, SyncEpisodeRunner=SyncEpisodeRunner)


class LoopbackServer:
    """回环 websocket 假服务：逐帧记录 ``(type, payload, seq)``；HELLO 回 HELLO，OBSERVATION 回 ACTION（seq 回显），
    EPISODE_START／EPISODE_END 不回复（与 vla-eval serve.py 成功路径一致）。每条连接各记一份。"""

    def __init__(self, vla):
        self.vla = vla
        self.conns: list[list[tuple]] = []
        self.port = None
        self._ready = threading.Event()
        self._loop = None
        self._stop = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(30)

    def _run(self):
        import websockets.asyncio.server as wss

        async def handler(ws):
            log: list[tuple] = []
            self.conns.append(log)
            n = 0
            async for raw in ws:
                m = self.vla.unpack(raw)
                log.append((m.type.value, m.payload, m.seq))
                if m.type == self.vla.MessageType.HELLO:
                    await ws.send(self.vla.pack(self.vla.Message(type=self.vla.MessageType.HELLO,
                                                                 payload={"model_server": "fake"}, seq=m.seq)))
                elif m.type == self.vla.MessageType.OBSERVATION:
                    await ws.send(self.vla.pack(self.vla.Message(type=self.vla.MessageType.ACTION,
                                                                 payload={"actions": action_for(n)}, seq=m.seq)))
                    n += 1

        async def main():
            self._stop = asyncio.Event()
            async with wss.serve(handler, "127.0.0.1", 0, compression=None, max_size=None, ping_interval=None) as srv:
                self.port = srv.sockets[0].getsockname()[1]
                self._ready.set()
                await self._stop.wait()

        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(main())

    def close(self):
        self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(10)


def _fake_robomme_modules(monkeypatch, env_kwargs: dict, built: list):
    """把 ``robomme.robomme_env``／``robomme.env_record_wrapper`` 换成假模块：RoboMMEBenchmark.reset 原样运行，
    环境由假 builder 按 ``(env_id, episode_idx)`` 构建。"""
    reg = types.ModuleType("robomme.robomme_env")

    class FakeBuilder:
        def __init__(self, env_id, dataset, action_space, gui_render, max_steps):
            built.append({"env_id": env_id, "dataset": dataset, "action_space": action_space,
                          "gui_render": gui_render, "max_steps": max_steps})
            self.env_id = env_id

        def make_env_for_episode(self, idx):
            return FakeEnv(self.env_id, idx, **env_kwargs)

    wrap = types.ModuleType("robomme.env_record_wrapper")
    wrap.BenchmarkEnvBuilder = FakeBuilder
    monkeypatch.setitem(sys.modules, "robomme.robomme_env", reg)
    monkeypatch.setitem(sys.modules, "robomme.env_record_wrapper", wrap)


def _reference_run(vla, port: int, max_steps: int) -> None:
    """独立来源：真实 SyncEpisodeRunner + RoboMMEBenchmark + Connection；记录器为测试内手写的固定 sid 子类。"""
    import anyio

    class Rec(vla.NullEpisodeRecorder):
        is_active = property(lambda self: True)
        sid = property(lambda self: SID)
        eid = property(lambda self: SID)
        eval_id = property(lambda self: "")
        db_path = property(lambda self: "")

    async def go():
        conn = vla.Connection(f"ws://127.0.0.1:{port}", timeout=300.0)
        await conn.connect(benchmark="vla_eval.benchmarks.robomme.benchmark:RoboMMEBenchmark")
        bench = vla.RoboMMEBenchmark(tasks=[TASK], action_space="joint_angle", max_steps=max_steps)
        try:
            await vla.SyncEpisodeRunner().run_episode(bench, {"name": TASK, "env_id": TASK, "episode_idx": SRC},
                                                      conn, max_steps=max_steps, recorder=Rec())
        finally:
            bench.cleanup()
            await conn.close()

    anyio.run(go)


def _strip(log):
    return [(t, p) for t, p, _ in log]


@pytest.mark.parametrize("env_kwargs,max_steps,n_actions", [({"demo": 4, "done_at": 7}, 1300, 7),
                                                             ({"demo": 3}, 1300, 1300)])
def test_new_and_orig_frames_identical_to_vla_eval_sync_runner(vla, monkeypatch, tmp_path, env_kwargs, max_steps,
                                                               n_actions):
    pp = load_script("eval-official/pp_client.py")
    orig = load_script("eval-official/pp_official_runner.py")
    built: list = []
    _fake_robomme_modules(monkeypatch, env_kwargs, built)
    srv = LoopbackServer(vla)
    try:
        _reference_run(vla, srv.port, max_steps)
        env = FakeEnv(TASK, SRC, **env_kwargs)
        res = pp.run_episode(FakeSession(env), XH, {"host": "127.0.0.1", "port": srv.port, "max_steps": max_steps,
                                                    "dataset": "test-hard0",
                                                    "trace_path": str(tmp_path / "new" / "trace.jsonl")},
                             None, connection_factory=lambda url, timeout: vla.Connection(url, timeout=timeout))
        import anyio

        summary = anyio.run(lambda: orig.run_shard(
            [XH], out_dir=tmp_path / "orig", url=f"ws://127.0.0.1:{srv.port}",
            bench_cls=orig.make_tracing_bench_class(vla.RoboMMEBenchmark), runner=vla.SyncEpisodeRunner(),
            conn_factory=lambda url, timeout: vla.Connection(url, timeout=timeout),
            recorder_cls=orig.make_fixed_sid_recorder_class(vla.NullEpisodeRecorder), max_steps=max_steps))
    finally:
        srv.close()
    assert len(srv.conns) == 3
    ref, new, org = srv.conns
    # seq 也逐帧相同（每局新连接、单局分片）
    assert [s for *_, s in ref] == [s for *_, s in new] == [s for *_, s in org]
    fd_new, od_new, notes_new = compare_frames(_strip(new), _strip(ref))
    fd_org, od_org, notes_org = compare_frames(_strip(org), _strip(ref))
    assert (fd_new, od_new) == (0, 0), notes_new
    assert (fd_org, od_org) == (0, 0), notes_org
    kinds = [t for t, *_ in ref]
    assert kinds.count("observation") == n_actions and kinds[1] == "episode_start" and kinds[-1] == "episode_end"
    assert ref[1][1]["recording"]["sid"] == SID and ref[1][1]["task"]["episode_idx"] == SRC
    first = ref[2][1]
    assert set(first) == {"images", "task_description", "states", "video_history", "wrist_video_history",
                          "episode_restart"}
    assert first["states"].dtype == np.float32 and first["states"].shape == (8,)
    assert first["images"]["agentview"].dtype == np.uint8 and first["images"]["agentview"].shape == (8, 8, 3)
    assert len(first["video_history"]) == env_kwargs["demo"]
    assert all(b == {"env_id": TASK, "dataset": "test", "action_space": "joint_angle", "gui_render": False,
                     "max_steps": max_steps} for b in built) and len(built) == 2
    # 结局与步数：新侧、原侧一致
    rows = [json.loads(x) for x in (tmp_path / "orig" / "results.jsonl").read_text().splitlines()]
    assert summary["episodes"] == 1 and rows[0]["status"] == res["status"]
    assert rows[0]["exec_steps"] == res["steps"] == n_actions
    # 两侧轨迹的请求哈希、动作、画面逐行相同
    tw = load_script("eval-official/trace_writer.py")
    tn = tw.read_trace(tmp_path / "new" / "trace.jsonl")
    to = tw.read_trace(rows[0]["trace_path"])
    pick = lambda rs: [(r["kind"], r.get("sha256"), r.get("front_sha256"), (r.get("action") or {}).get("sha256"),  # noqa: E731
                        (r.get("actions") or {}).get("sha256")) for r in rs if r["kind"] in ("request", "response", "step")]
    assert pick(tn) == pick(to)
    assert [r for r in tn if r["kind"] == "demo"] == [r for r in to if r["kind"] == "demo"]
    print(f"PP_PROTOCOL=PASS frames_diff={fd_new + fd_org} order_diff={od_new + od_org} source=vla_eval_sync_runner "
          f"frames={len(ref)} actions={n_actions}")
