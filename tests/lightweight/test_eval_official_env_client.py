"""``scripts/eval-official/env_client.py`` 的纯 CPU 测试（假 builder／假 env／假策略模块，不起仿真）。

覆盖：EnvSession 把 action 原样交给 env.step 并记录交出去的数组、reset 阶段只入队后切 run、env.step 异常原样
上抛并留事件、进度回调；身份不符即运行阻塞（退出码 3、写 run_blocked 记录）；结果记录合同字段；
identities 模式续跑跳过、基础设施失败重试；队列模式 done 终态与 ``QUEUE_CLAIM=PASS``；乱序可复现；金丝雀解析。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
EO = REPO / "scripts" / "eval-official"


def _load(name, alias):
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, EO / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


EC = _load("env_client", "env_client")
Q = _load("claim_queue", "claim_queue")


class Rec:
    def __init__(self, *a, **k):
        self.phases, self.frames, self.arrays, self.events = [], [], [], []
        self.closed = None

    def set_phase(self, p):
        self.phases.append(p)

    def add_frames(self, stream, frames, *, tag=""):
        self.frames.append((stream, tag, np.asarray(frames).shape, self.phases[-1] if self.phases else None))
        return []

    def add_array(self, name, arr, *, step=None):
        self.arrays.append((name, step, np.array(arr)))

    def add_event(self, e):
        self.events.append(e)

    def close(self, summary):
        self.closed = summary
        return {"RECORDER_VERIFY": "PASS", "frames": len(self.frames)}


def _obs(vals):
    f = lambda v: np.full((4, 4, 3), v % 256, dtype=np.uint8)  # noqa: E731
    return {"front_rgb_list": [f(v) for v in vals], "wrist_rgb_list": [f(v + 1) for v in vals],
            "joint_state_list": [np.full(7, v, np.float64) for v in vals],
            "gripper_state_list": [np.array([v, v], np.float64) for v in vals],
            "eef_state_list": [np.zeros(6) for _ in vals]}


class Env:
    def __init__(self, raise_at=None):
        self.got, self.n, self.raise_at, self.closed = [], 0, raise_at, False

    def reset(self):
        return _obs([0, 1, 2]), {"task_goal": ["goal"], "status": "ongoing"}

    def step(self, action):
        self.got.append(action)
        self.n += 1
        if self.raise_at == self.n:
            raise RuntimeError("boom")
        return _obs([10 + self.n]), 0.0, self.n >= 5, False, {"status": "success" if self.n >= 5 else "ongoing"}

    def close(self):
        self.closed = True


class Builder:
    def __init__(self, task, seed_of=None, envs=None):
        self.task = task
        self.seed_of = seed_of or {}
        self.envs = envs if envs is not None else []

    def resolve_identity(self, i):
        seed, se = self.seed_of.get(i, (500000 + i, 3 + 4 * i))
        return {"episode": i, "tier": "xhard0", "seed": seed, "source_episode": se}

    def make_env_for_episode(self, i, max_steps=None):
        assert max_steps == 1300
        e = Env()
        self.envs.append(e)
        return e


def test_EnvSession_动作原样_记录_阶段():
    rec = Rec()
    b = Builder("PickXtimes")
    s = EC.EnvSession("PickXtimes", 0, recorder=rec, builder=b)
    hits = []
    s.progress_cb, s.progress_every = hits.append, 2
    obs, info = s.reset()
    assert len(obs["front_rgb_list"]) == 3 and info["task_goal"] == ["goal"]
    assert rec.phases[:2] == ["reset", "reset"] and rec.phases[-1] == "run"
    assert rec.frames[0] == ("front", "reset", (3, 4, 4, 3), "reset")
    ev = [e for e in rec.events if e["kind"] == "env_reset"][0]
    assert ev["demo_frames"] == 2 and len(ev["front"]) == 3 and ev["task_goal"] == "goal"
    a = np.arange(8, dtype=np.float32)
    s.step(a)
    assert b.envs[0].got[0] is a  # 原样交出，不复制不转换
    name, step, arr = [x for x in rec.arrays if x[0] == "exec_action"][0]
    assert step == 0 and arr.dtype == np.float32 and np.array_equal(arr, a)
    a[0] = 99  # 记录的是交出时的拷贝
    assert arr[0] == 0
    s.step([0.0] * 8)
    assert hits == [2]
    s.close()
    assert b.envs[0].closed and s.timing["step_n"] == 2 and "env_build_s" in s.timing


def test_EnvSession_step异常原样上抛():
    rec = Rec()
    b = Builder("X")

    def mk(i, max_steps=None):
        e = Env(raise_at=1)
        b.envs.append(e)
        return e

    b.make_env_for_episode = mk
    s = EC.EnvSession("X", 0, recorder=rec, builder=b)
    s.reset()
    with pytest.raises(RuntimeError):
        s.step(np.zeros(8))
    assert any(e["kind"] == "env_step_exception" for e in rec.events)


class Policy:
    """假策略模块：跑到环境报终态。"""

    def __init__(self, infra_first=0):
        self.calls = []
        self.infra_left = infra_first

    def run_episode(self, session, identity, conn_info, recorder):
        self.calls.append((identity["task"], identity["seed"], conn_info["port"]))
        if self.infra_left:
            self.infra_left -= 1
            return {"status": "error", "steps": 0, "error": "ConnectionClosed", "infra": True, "timing": {}}
        session.reset()
        n = 0
        while True:
            _, _, term, trunc, info = session.step(np.zeros(8, np.float32))
            n += 1
            if term or trunc:
                return {"status": info["status"], "steps": n, "error": None, "infra": False, "timing": {"x": 1}}


def _args(tmp_path, **kw):
    d = dict(policy="mme", identities=None, queue=None, cond="E1", seat="card1", host="127.0.0.1", port=18010,
             out=str(tmp_path / "out"), order="forward", shuffle_seed=20260930, canary=None, only=None, limit=0,
             max_steps=1300, episode_wall_s=0.0, first_extra_s=0.0, infra_retries=2, no_record=False,
             reap_threshold_s=1200.0, poll_s=30.0,
             never_degrade=False, baseline=False)
    d.update(kw)
    return argparse.Namespace(**d)


def _idents():
    return [{"task": "PickXtimes", "source_episode": 3 + 4 * i, "seed": 500000 + i, "builder_episode": i}
            for i in range(3)]


def _runner(tmp_path, pol, builders=None, **kw):
    builders = builders if builders is not None else {}
    return EC.SeatRunner(_args(tmp_path, **kw), policy_mod=pol, recorder_factory=lambda d, m: Rec(),
                         builder_factory=lambda t: builders.setdefault(t, Builder(t)),
                         proc_info={"gpu_name": "G", "gpu_uuid": "U", "git_commit": "abc", "git_dirty": False,
                                    "init_timing": {"import_torch_s": 1.0}})


def test_结果记录合同字段与续跑(tmp_path):
    pol = Policy()
    r = _runner(tmp_path, pol)
    r.run_identities(_idents())
    rows = [json.loads(l) for l in (tmp_path / "out" / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    need = {"task", "source_episode", "seed", "identity", "policy", "cond", "status", "task_success", "steps", "error",
            "seat", "host", "gpu_name", "gpu_uuid", "git_commit", "rec_dir", "timing", "attempt"}
    assert need <= set(rows[0])
    assert rows[0]["identity"] == {"tier": "xhard0", "seed": 500000, "source_episode": 3}
    assert rows[0]["status"] == "success" and rows[0]["task_success"] and rows[0]["steps"] == 5
    assert rows[0]["timing"]["process_init"] == {"import_torch_s": 1.0} and "process_init" not in rows[1]["timing"]
    assert rows[0]["recorder_verify"] == "PASS"
    prog = json.loads((tmp_path / "out" / "progress.json").read_text())
    assert prog["episodes_done"] == 3
    pol2 = Policy()
    _runner(tmp_path, pol2).run_identities(_idents())
    assert pol2.calls == []  # 全部续跑跳过


def test_基础设施失败重试(tmp_path):
    pol = Policy(infra_first=1)
    _runner(tmp_path, pol).run_identities(_idents()[:1])
    rows = [json.loads(l) for l in (tmp_path / "out" / "results.jsonl").read_text().splitlines()]
    assert [r["status"] for r in rows] == ["error", "success"] and [r["attempt"] for r in rows] == [1, 2]
    assert rows[1]["rec_dir"].endswith(".a2")


def test_身份不符_运行阻塞(tmp_path):
    builders = {"PickXtimes": Builder("PickXtimes", seed_of={1: (999, 7)})}
    r = _runner(tmp_path, Policy(), builders=builders)
    with pytest.raises(SystemExit) as ei:
        r.run_identities(_idents())
    assert ei.value.code == EC.EXIT_BLOCKED
    rows = [json.loads(l) for l in (tmp_path / "out" / "results.jsonl").read_text().splitlines()]
    assert rows[-1]["run_blocked"] is True and rows[-1]["error"].startswith("IDENTITY_MISMATCH")


def test_队列模式_终态与check(tmp_path):
    q = Q.ClaimQueue(tmp_path / "q" / "mme")
    q.init(_idents(), order="forward")
    pol = Policy(infra_first=1)
    _runner(tmp_path, pol, queue=str(tmp_path / "q")).run_queue(q)
    st = q.check()
    assert st["dup"] == 0 and st["missing"] == 0 and st["requeued"] == 1 and st["retries_used"] == 1
    assert len(pol.calls) == 4
    done = json.loads((q.done / "PickXtimes_500000.json").read_text())
    assert done["status"] == "success" and done["attempt"] == 2


def test_乱序可复现与金丝雀解析():
    rows = _idents() * 1
    a = EC.order_identities(rows, "shuffle", 20260930)
    b = EC.order_identities(list(reversed(rows)), "shuffle", 20260930)
    assert [EC.key_of(x) for x in a] == [EC.key_of(x) for x in b]
    assert EC.order_identities(rows, "reverse", 0)[0]["seed"] == 500002
    c = EC.parse_canary("PickXtimes:3:510300")
    assert c == {"task": "PickXtimes", "source_episode": 3, "seed": 510300, "builder_episode": 0}
    assert EC.check_identity({"tier": "xhard0", "seed": 510300, "source_episode": 3}, c) is None
    assert "tier" in EC.check_identity({"tier": "xhard1", "seed": 510300, "source_episode": 3}, c)


def test_队列模式_死席位认领被回收_活席位等待而不提前退出(tmp_path):
    import os
    import time as _t

    q = Q.ClaimQueue(tmp_path / "q" / "mme")
    q.init(_idents(), order="forward")
    dead = q.claim_next("deadSeat")  # 死席位占住一个身份，mtime 很旧
    old = _t.time() - 5000
    os.utime(q.claims / f"{dead.key}.claim", (old, old))
    pol = Policy()
    r = _runner(tmp_path, pol, queue=str(tmp_path / "q"), reap_threshold_s=1200.0, poll_s=0.01)
    r.run_queue(q)
    st = q.check()
    assert st["missing"] == 0 and st["dup"] == 0 and st["requeued"] == 1 and len(pol.calls) == 3


def test_录制器故障记基础设施(tmp_path):
    class BadRec(Rec):
        def add_frames(self, *a, **k):
            raise OSError(28, "No space left on device")

    b = Builder("PickXtimes")
    s = EC.EnvSession("PickXtimes", 0, recorder=BadRec(), builder=b)
    with pytest.raises(EC.RecorderError):
        s.reset()
    MC = _load("mme_client", "mme_client")
    env = Env()
    s2 = EC.EnvSession("PickXtimes", 0, recorder=Rec(), builder=b)
    s2.build()
    s2.reset()
    s2._rec = EC._GuardedRecorder(BadRec())
    res = MC.evaluate_one(lambda: _FakeClient(), s2.step, lambda: MC.pre_traj_from_reset(*env.reset()))
    assert res["status"] == "error" and res["infra"] is True and "RecorderError" in res["error"]


class _FakeClient:
    def reset(self):
        return {"reset_finished": True}

    def add_buffer(self, b):
        return {"add_buffer_finished": True}

    def infer(self, o):
        return {"actions": np.zeros((16, 8), np.float32)}
