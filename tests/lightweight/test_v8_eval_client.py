"""``scripts/eval-official/env_client.py`` V8 模式的纯 CPU 测试（假 env／假 builder／假策略连接，不起仿真）。

覆盖（1001-v8-post-evaluation-gl-plan.md 第一部分 §1 第 4 条、§3，第二部分 §4；契约 C2）：
- 1600 截断：第 1599／1600 步成功记 success；第 1600 步未成功 → 第 1601 次 step 不进入环境、记 timeout；exec_steps≤1600；
- 经真实 ``SeatRunner.run_one`` 调用链：真 smvla_client 拿到 max_steps=1600、reset_retries=0、hard_bound=102，
  旧模式 84；真 mme_client 只靠 conn_info 拿 1600；
- reset 额度：跨两个 SeatRunner 实例（模拟进程重启）不刷新，耗尽退出码 5，提升写 budget_raise；
- infra 重试只一次、额度从账本计；accept／late；悬空尝试恢复；身份不符 RUN_BLOCKED；旧 xhard0 模式回归。
末尾 ``test_zz_判定行`` 汇总打印 ``V8_STEP_CAP_CONTRACT=...``。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
EO = REPO / "scripts" / "eval-official"

pytestmark = pytest.mark.lightweight


def _load(name, alias):
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, EO / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


EC = _load("env_client", "env_client")
SM = _load("smvla_client", "smvla_client_v8test")
MC = _load("mme_client", "mme_client_v8test")

CAP = 1600
FACTS: dict = {}  # 供末尾判定行汇总


# ── 假环境、假 builder、假录制器 ─────────────────────────────────────────────


def _obs(vals):
    f = lambda v: np.full((2, 2, 3), v % 256, dtype=np.uint8)  # noqa: E731
    return {"front_rgb_list": [f(v) for v in vals], "wrist_rgb_list": [f(v + 1) for v in vals],
            "joint_state_list": [np.full(7, v % 7, np.float64) for v in vals],
            "gripper_state_list": [np.array([0.01, 0.01], np.float64) for v in vals],
            "eef_state_list": [np.zeros(6) for _ in vals]}


class Env:
    """success_at=n：第 n 次 step 报 success（terminated）；None 表示永不终止。reset 返回 3 帧（2 帧演示）。"""

    def __init__(self, success_at=None, reset_raises=None):
        self.n, self.success_at, self.resets, self.reset_raises = 0, success_at, 0, reset_raises

    def reset(self):
        self.resets += 1
        if self.reset_raises:
            raise RuntimeError(self.reset_raises)
        return _obs([0, 1, 2]), {"task_goal": ["goal"], "status": "ongoing"}

    def step(self, action):
        self.n += 1
        ok = self.success_at is not None and self.n == self.success_at
        return _obs([10 + self.n]), 0.0, ok, False, {"status": "success" if ok else "ongoing"}

    def close(self):
        pass


SPEC = {k: hashlib.sha256(k.encode()).hexdigest() for k in ("a", "b", "c", "d")}


def _ident(i, task="SwingXtimes", tier="xhard5", cand=None, spec=None):
    seed = 26_000_000 + i
    return {"task": task, "tier": tier, "seed": seed, "candidate": i if cand is None else cand, "builder_episode": 12 + i,
            "source_episode": None, "spec_sha256": spec or SPEC["abcd"[i % 4]], "effective_max_steps": CAP,
            "key": f"{task}_{tier}_{seed}"}


class Builder:
    """resolve_identity 按身份表返回；make_env_for_episode 记 max_steps 并按 env_factory 建环境。"""

    def __init__(self, task, ms, idents, env_factory, log):
        self.task, self.ms, self.log = task, ms, log
        self.by_ep = {r["builder_episode"]: r for r in idents if r["task"] == task}
        self.env_factory = env_factory
        self.overrides: dict = {}

    def resolve_identity(self, ep):
        r = self.by_ep[ep]
        out = {"episode": ep, "tier": r["tier"], "candidate": r["candidate"], "seed": r["seed"],
               "spec_sha256": r["spec_sha256"], "source_run": None}
        out.update(self.overrides.get(ep, {}))
        return out

    def make_env_for_episode(self, ep, max_steps=None):
        self.log.append(("make_env", self.task, ep, max_steps, self.ms))
        return self.env_factory(ep)


class Rec:
    def set_phase(self, p):
        pass

    def add_frames(self, stream, frames, *, tag=""):
        return []

    def add_array(self, name, arr, *, step=None):
        pass

    def add_event(self, e):
        pass

    def close(self, summary):
        return {"RECORDER_VERIFY": "PASS"}


# ── 假策略 ───────────────────────────────────────────────────────────────────


class StepPolicy:
    """MME 式最简策略（无 max_steps 关键字）：reset 后逐步 step 到环境终态；step 异常记 error（与客户端一样吞掉）。"""

    def __init__(self, infra_always=False):
        self.calls = []
        self.infra_always = infra_always

    def run_episode(self, session, identity, conn_info, recorder):
        self.calls.append(dict(conn_info))
        if self.infra_always:
            return {"status": "error", "steps": 0, "error": "ConnectionClosed", "infra": True, "timing": {}}
        try:
            session.reset()
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "steps": 0, "error": f"{type(e).__name__}: {e}", "infra": False}
        n = 0
        while True:
            try:
                _, _, term, trunc, info = session.step(np.zeros(8, np.float32))
            except Exception as e:  # noqa: BLE001
                return {"status": "error", "steps": n, "error": f"{type(e).__name__}: {e}", "infra": False}
            n += 1
            if term or trunc:
                return {"status": info["status"], "steps": n, "error": None, "infra": False}


class FakeConn:
    """smvla 协议的假连接（与 test_eval_official_smvla_client.FakeConn 同式）：动作恒为 0。"""

    def __init__(self, *a, **k):
        self.metadata = {"policy": "smvla", "fake": True}
        self.n = 0

    def call(self, msg):
        raw = repr(sorted(msg)).encode() + str(self.n).encode()
        self.n += 1
        kind = next(iter(msg))
        if kind == "reset":
            rep = {"reset_finished": True}
        elif kind == "observe":
            frs = msg["observe"]["frames"]
            rep = {"n": len(frs), "frame_sha": [{k: SM.frame_sha(v) for k, v in sorted(f.items())} for f in frs]}
        else:
            p = msg["infer"]
            a = np.zeros((32, 8), np.float32)
            rep = {"actions": a[:16], "actions_full": a, "subtask": "s", "infer_ms": 1.0,
                   "recv_state_sha": SM.array_sha(np.asarray(p["state"])),
                   "recv_instruction_sha": SM.sha256_bytes(p["instruction"].encode())}
        rep["req_sha"] = hashlib.sha256(raw).hexdigest()
        return rep, raw, b"r" + raw

    def close(self):
        pass


class FakeMMEClient:
    def reset(self):
        return {"reset_finished": True}

    def add_buffer(self, b):
        return {"add_buffer_finished": True}

    def infer(self, o):
        return {"actions": np.zeros((16, 8), np.float32)}


# ── 工具 ─────────────────────────────────────────────────────────────────────


def _args(tmp_path, **kw):
    d = dict(policy="mme", identities=None, queue=None, cond="V8", seat="s00", host="127.0.0.1", port=18010,
             out=str(tmp_path / "out"), order="forward", shuffle_seed=20260930, canary=None, only=None, limit=0,
             max_steps=1300, episode_wall_s=0.0, first_extra_s=0.0, infra_retries=2, no_record=False,
             reap_threshold_s=1200.0, poll_s=30.0, never_degrade=True, baseline=False,
             v8=True, ledger=str(tmp_path / "mme.ledger.jsonl"), reset_budget=100, infra_retry_budget=10,
             rec_root=str(tmp_path / "rec"), budget_raise_reason=None)
    d.update(kw)
    return argparse.Namespace(**d)


def _runner(tmp_path, pol, idents, env_factory=None, log=None, builders=None, **kw):
    log = log if log is not None else []
    builders = builders if builders is not None else {}
    env_factory = env_factory or (lambda ep: Env())

    def bf(task, ms=None):
        return builders.setdefault((task, ms), Builder(task, ms, idents, env_factory, log))

    return EC.SeatRunner(_args(tmp_path, **kw), policy_mod=pol, recorder_factory=lambda d, m: Rec(),
                         builder_factory=bf, proc_info={"gpu_name": "G", "gpu_uuid": "U", "git_commit": "abc",
                                                        "git_dirty": False, "init_timing": {}})


def _results(tmp_path):
    return [json.loads(l) for l in (tmp_path / "out" / "results.jsonl").read_text().splitlines()]


def _ledger(tmp_path, name="mme"):
    return [json.loads(l) for l in (tmp_path / f"{name}.ledger.jsonl").read_text().splitlines()]


def _cap_ok(rec):
    FACTS.setdefault("exec_max", 0)
    FACTS["exec_max"] = max(FACTS["exec_max"], rec["exec_steps"])
    FACTS["over"] = FACTS.get("over", 0) + int(rec["exec_steps"] > CAP)


# ── 1600 截断 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("success_at,status,exec_steps", [(1599, "success", 1599), (1600, "success", 1600),
                                                           (None, "timeout", 1600)])
def test_1600截断_第1599与1600步成功_未成功记timeout(tmp_path, success_at, status, exec_steps):
    ident = _ident(0)
    envs = []

    def ef(ep):
        envs.append(Env(success_at=success_at))
        return envs[-1]

    log = []
    pol = StepPolicy()
    r = _runner(tmp_path, pol, [ident], env_factory=ef, log=log)
    rec = r.run_one(ident, attempt=1)
    assert rec["status"] == status and rec["task_success"] == (status == "success")
    assert rec["exec_steps"] == exec_steps and envs[0].n == exec_steps  # 第 1601 次未进入环境
    assert rec["cap_hit"] == (success_at is None) and rec["infra"] is False
    assert rec["effective_max_steps"] == CAP and pol.calls[0]["max_steps"] == CAP
    assert log[0][3] == CAP and log[0][4] == CAP  # make_env 与 builder 都按 1600
    if success_at is None:
        assert rec["client_status"] == "error" and "StepCapReached" in rec["client_error"]
        assert rec["error"].startswith("STEP_CAP")
    assert rec["reset_calls"] == 2 and rec["demo_frames"] == 2 and rec["rec_dir"].endswith(f"{ident['key']}.a1")
    acc = [x for x in _ledger(tmp_path) if x["kind"] == "accept"]
    assert len(acc) == 1 and acc[0]["accepted_attempt_id"] == rec["attempt_id"] and acc[0]["status"] == status
    _cap_ok(rec)


def test_EnvSession_step_cap_直接():
    s = EC.EnvSession("X", 0, max_steps=3, builder=Builder("X", 3, [dict(_ident(0), task="X", builder_episode=0)],
                                                           lambda ep: Env(), []), step_cap=3)
    s.reset()
    for _ in range(3):
        s.step(np.zeros(8))
    env = s.env
    with pytest.raises(EC.StepCapReached):
        s.step(np.zeros(8))
    assert s.cap_hit and s.steps == 3 and env.n == 3
    legacy = EC.EnvSession("X", 0, max_steps=3, builder=Builder("X", 3, [dict(_ident(0), task="X", builder_episode=0)],
                                                                lambda ep: Env(), []))
    legacy.reset()
    for _ in range(5):  # 旧模式不截断
        legacy.step(np.zeros(8))
    assert legacy.steps == 5 and not legacy.cap_hit and legacy.reset_calls == 2


# ── 真实调用链：smvla 102 块 / 旧 84 块；mme 只靠 conn_info ──────────────────


def test_smvla_真实run_one调用链_V8为102块_1600截断(tmp_path, monkeypatch):
    monkeypatch.setattr(SM, "WSPolicyConn", FakeConn)
    seen = {}
    orig = SM.reset_session

    def spy(session, task, retries=SM.RESET_RETRIES):
        seen["retries"] = retries
        return orig(session, task, retries=retries)

    monkeypatch.setattr(SM, "reset_session", spy)
    ident = _ident(1)
    envs = []

    def ef(ep):
        envs.append(Env())
        return envs[-1]

    r = _runner(tmp_path, SM, [ident], env_factory=ef, policy="smvla", ledger=str(tmp_path / "smvla.ledger.jsonl"))
    assert r.policy_kwargs(CAP) == {"max_steps": CAP, "reset_retries": 0}
    rec = r.run_one(ident, attempt=1)
    assert seen["retries"] == 0
    assert rec["hard_bound"] == SM.hard_bound(CAP) == 102
    assert rec["status"] == "timeout" and rec["cap_hit"] and rec["exec_steps"] == CAP and envs[0].n == CAP
    assert rec["chunks"] == 101 and rec["client_steps"] == CAP and rec["infra"] is False
    FACTS["smvla_v8"] = rec["hard_bound"]
    _cap_ok(rec)


def test_smvla_旧模式仍84块_不截断(tmp_path, monkeypatch):
    monkeypatch.setattr(SM, "WSPolicyConn", FakeConn)
    ident = {"task": "PickXtimes", "source_episode": 3, "seed": 510300, "builder_episode": 0}
    envs = []

    class LegacyBuilder:
        def resolve_identity(self, i):
            return {"episode": i, "tier": "xhard0", "seed": 510300, "source_episode": 3}

        def make_env_for_episode(self, i, max_steps=None):
            assert max_steps == 1300
            envs.append(Env())
            return envs[-1]

    args = _args(tmp_path, policy="smvla")
    for k in ("v8", "ledger", "reset_budget", "infra_retry_budget", "rec_root", "budget_raise_reason"):
        delattr(args, k)  # 旧调用方的 Namespace 没有这些字段
    r = EC.SeatRunner(args, policy_mod=SM, recorder_factory=lambda d, m: Rec(), builder_factory=lambda t: LegacyBuilder(),
                      proc_info={})
    assert r.policy_kwargs(1300) == {} and not r.v8
    rec = r.run_one(ident, attempt=1)
    assert rec["hard_bound"] == 84 and rec["status"] == "timeout" and rec["steps"] == 84 * 16 == envs[0].n
    assert "v8" not in rec and "exec_steps" not in rec and rec["identity"]["tier"] == "xhard0"
    assert rec["rec_dir"].endswith("rec/PickXtimes_510300")
    FACTS["smvla_legacy"] = rec["hard_bound"]


def test_mme_真实run_one调用链_只靠conn_info(tmp_path, monkeypatch):
    monkeypatch.setattr(MC, "make_recording_client", lambda *a, **k: FakeMMEClient())
    ident = _ident(2)
    envs = []

    def ef(ep):
        envs.append(Env())
        return envs[-1]

    r = _runner(tmp_path, MC, [ident], env_factory=ef)
    assert r.policy_kwargs(CAP) == {}  # mme 的 run_episode 无 max_steps 关键字
    rec = r.run_one(ident, attempt=1)
    assert rec["status"] == "timeout" and rec["cap_hit"] and rec["exec_steps"] == CAP and envs[0].n == CAP
    assert rec["chunks"] is None and rec["hard_bound"] is None and rec["infra"] is False
    _cap_ok(rec)


# ── reset 额度 ───────────────────────────────────────────────────────────────


def test_reset额度跨重启不刷新_耗尽退出码5_提升(tmp_path, capsys):
    a, b = _ident(0), _ident(1)
    pol = StepPolicy()
    ef = lambda ep: Env(success_at=3)  # noqa: E731
    r1 = _runner(tmp_path, pol, [a, b], env_factory=ef, reset_budget=3)
    r1.run_identities([a])  # build + reset = 2 次
    assert r1.ledger.reset_claims == 2
    r2 = _runner(tmp_path, pol, [a, b], env_factory=ef, reset_budget=3)  # 模拟进程重启
    assert r2.ledger.reset_claims == 2 and r2.ledger.reset_left() == 1
    with pytest.raises(SystemExit) as ei:
        r2.run_identities([a, b])  # a 已 accept 跳过；b 的 build 领到第 3 次，reset 被拒
    assert ei.value.code == EC.EXIT_BUDGET == 5
    out = capsys.readouterr().out
    assert "RESET_BUDGET_EXHAUSTED" in out
    last = _results(tmp_path)[-1]
    assert last["key"] == b["key"] and last["status"] == "error" and last["budget_exhausted"] is True
    assert last["infra"] is False and last["reset_calls"] == 1
    r3 = _runner(tmp_path, pol, [a, b], env_factory=ef, reset_budget=3)
    with pytest.raises(SystemExit) as ei:
        r3.run_identities([b])  # 再重启也不刷新：开局前即停，不开新尝试
    assert ei.value.code == 5
    assert sum(x["kind"] == "attempt_start" for x in _ledger(tmp_path)) == 2
    r4 = _runner(tmp_path, pol, [a, b], env_factory=ef, reset_budget=30, budget_raise_reason="smoke_resets_gt2")
    out = capsys.readouterr().out
    assert "RESET_BUDGET_RAISE from=3 to=30 reason=smoke_resets_gt2" in out
    r4.run_identities([a, b])
    led = _ledger(tmp_path)
    raise_rows = [x for x in led if x["kind"] == "budget_raise"]
    assert len(raise_rows) == 1 and raise_rows[0]["from"] == 3 and raise_rows[0]["to"] == 30
    assert sum(x["kind"] == "budget" for x in led) == 4
    rows = [x for x in _results(tmp_path) if x["key"] == b["key"]]
    assert [x["attempt_no"] for x in rows] == [1, 2] and rows[1]["status"] == "success"
    assert rows[1]["rec_dir"].endswith(f"{b['key']}.a2")
    assert r4.ledger.infra_retries_used() == 0  # 额度作废的尝试不占 infra 重试
    assert r4.ledger.reset_claims == 5


# ── infra 重试 ───────────────────────────────────────────────────────────────


def test_infra重试只一次_额度从账本计(tmp_path, capsys):
    a, b = _ident(0), _ident(1)
    pol = StepPolicy(infra_always=True)
    r = _runner(tmp_path, pol, [a, b], infra_retry_budget=1)
    r.run_identities([a, b])
    rows = _results(tmp_path)
    assert [(x["key"], x["attempt_no"]) for x in rows] == [(a["key"], 1), (a["key"], 2), (b["key"], 1)]
    assert "INFRA_RETRY_BUDGET_EXHAUSTED" in capsys.readouterr().out
    assert r.ledger.infra_retries_used() == 1
    r2 = _runner(tmp_path, pol, [a, b], infra_retry_budget=1)  # 重启不刷新
    r2.run_identities([a, b])
    assert len(_results(tmp_path)) == 3
    r3 = _runner(tmp_path, pol, [a, b], infra_retry_budget=5)  # 额度变大：b 可重试一次，a 已满 2 次
    r3.run_identities([a, b])
    rows = _results(tmp_path)
    assert [(x["key"], x["attempt_no"]) for x in rows][-1] == (b["key"], 2) and len(rows) == 4
    assert not [x for x in _ledger(tmp_path) if x["kind"] == "accept"]


def test_正常终态不重试(tmp_path):
    a = _ident(0)
    pol = StepPolicy()
    r = _runner(tmp_path, pol, [a], env_factory=lambda ep: Env(reset_raises="scene invalid"))
    r.run_identities([a])
    rows = _results(tmp_path)
    assert len(rows) == 1 and rows[0]["status"] == "error" and rows[0]["infra"] is False


# ── accept / late / 悬空恢复 ────────────────────────────────────────────────


def test_accept与late(tmp_path):
    a = _ident(0)
    pol = StepPolicy()
    r = _runner(tmp_path, pol, [a], env_factory=lambda ep: Env(success_at=2))
    r.run_identities([a])
    first = _results(tmp_path)[0]
    late = r.run_one(a, attempt=2)  # 同一身份再来一条终态
    assert late["late"] is True and first["late"] is False
    led = _ledger(tmp_path)
    acc = [x for x in led if x["kind"] == "accept"]
    assert len(acc) == 1 and acc[0]["accepted_attempt_id"] == first["attempt_id"]
    ends = [x for x in led if x["kind"] == "attempt_end"]
    assert [e["late"] for e in ends] == [False, True]
    n = len(pol.calls)
    _runner(tmp_path, pol, [a]).run_identities([a])  # resume：已 accept 跳过
    assert len(pol.calls) == n
    need = {"v8", "key", "tier", "candidate", "spec_sha256", "attempt_id", "attempt_no", "exec_steps", "client_steps",
            "chunks", "hard_bound", "effective_max_steps", "cap_hit", "demo_frames", "reset_calls", "rec_dir",
            "identity", "task_success"}
    assert need <= set(first)
    assert first["identity"] == {"tier": a["tier"], "seed": a["seed"], "candidate": a["candidate"],
                                 "spec_sha256": a["spec_sha256"], "builder_episode": a["builder_episode"]}
    for kind in ("budget", "attempt_start", "reset_claim", "attempt_end", "accept"):
        row = next(x for x in led if x["kind"] == kind)
        assert {"t", "kind", "seat", "policy"} <= set(row)
        if kind != "budget":
            assert {"key", "attempt_id", "attempt_no"} <= set(row)


def test_悬空尝试恢复(tmp_path):
    a, b = _ident(0), _ident(1)
    r = _runner(tmp_path, StepPolicy(), [a, b], env_factory=lambda ep: Env(success_at=2))
    rec = r.run_one(a, attempt=1)
    # 模拟：b 开了尝试后进程被杀（无结果行、无 attempt_end）；a 的 accept 行丢失（结果行已写）
    lp = tmp_path / "mme.ledger.jsonl"
    lines = [l for l in lp.read_text().splitlines() if json.loads(l)["kind"] not in ("attempt_end", "accept")]
    lines.append(json.dumps({"t": 0, "kind": "attempt_start", "key": b["key"], "attempt_id": "dead", "attempt_no": 1,
                             "retry": False, "seat": "s00", "policy": "mme"}))
    lp.write_text("\n".join(lines) + "\n")
    pol = StepPolicy()
    r2 = _runner(tmp_path, pol, [a, b], env_factory=lambda ep: Env(success_at=2))
    r2.run_identities([a, b])
    led = _ledger(tmp_path)
    acc = {x["key"]: x["accepted_attempt_id"] for x in led if x["kind"] == "accept"}
    assert acc[a["key"]] == rec["attempt_id"]  # 按结果行恢复 accept，不重跑
    assert len(pol.calls) == 1  # 只有 b 重试一次（悬空尝试记 infra，占 1 次 infra 重试）
    assert r2.ledger.infra_retries_used() == 1 and b["key"] in acc


# ── 身份核对 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("field,value", [("spec_sha256", "f" * 64), ("candidate", None), ("seed", 1), ("tier", "xhard4")])
def test_身份不符_RUN_BLOCKED(tmp_path, capsys, field, value):
    a = _ident(0)
    builders = {}
    r = _runner(tmp_path, StepPolicy(), [a], builders=builders)
    b = r.builder_for(a["task"], CAP)
    b.overrides[a["builder_episode"]] = {field: value}
    with pytest.raises(SystemExit) as ei:
        r.run_identities([a])
    assert ei.value.code == EC.EXIT_BLOCKED
    assert "RUN_BLOCKED reason=identity" in capsys.readouterr().out
    row = _results(tmp_path)[-1]
    assert row["run_blocked"] is True and row["error"].startswith("IDENTITY_MISMATCH") and field in row["error"]
    assert not [x for x in _ledger(tmp_path) if x["kind"] == "attempt_start"]  # 阻塞不占尝试


def test_有效上限不符_RUN_BLOCKED(tmp_path):
    a = dict(_ident(0), effective_max_steps=1300)
    with pytest.raises(SystemExit) as ei:
        _runner(tmp_path, StepPolicy(), [a]).run_one(a)
    assert ei.value.code == 3 and "effective_max_steps" in _results(tmp_path)[-1]["error"]


def test_builder缓存按上限区分(tmp_path):
    r = _runner(tmp_path, StepPolicy(), [_ident(0)])
    assert r.builder_for("SwingXtimes", 1600) is not r.builder_for("SwingXtimes", 1300)
    assert r.builder_for("SwingXtimes", 1600) is r.builder_for("SwingXtimes", 1600)


def test_身份清单与命令行(tmp_path, capsys):
    rows = [_ident(i) for i in range(3)]
    p = tmp_path / "shard-00.json"
    p.write_text(json.dumps(rows))
    args = EC.build_parser().parse_args(["run", "--policy", "smvla", "--identities", str(p), "--cond", "V8", "--seat",
                                         "s00", "--port", "1", "--out", str(tmp_path / "o"), "--v8", "--ledger",
                                         str(tmp_path / "l.jsonl"), "--reset-budget", "8", "--infra-retry-budget", "2",
                                         "--rec-root", str(tmp_path / "rec"), "--order", "shuffle"])
    assert args.v8 and args.reset_budget == 8 and EC.check_v8_args(args) is None
    got = EC.load_identities(args)
    assert sorted(EC.key_of(r) for r in got) == sorted(r["key"] for r in rows)
    legacy = EC.build_parser().parse_args(["run", "--policy", "mme", "--identities", str(p), "--cond", "E1", "--seat",
                                           "c", "--port", "1", "--out", "o"])
    assert legacy.v8 is False and legacy.ledger is None and legacy.rec_root is None and legacy.max_steps == 1300
    bad = EC.build_parser().parse_args(["run", "--policy", "mme", "--identities", str(p), "--cond", "V8", "--seat",
                                        "c", "--port", "1", "--out", "o", "--v8"])
    assert "--ledger" in EC.check_v8_args(bad)
    p.write_text(json.dumps(rows + [rows[0]]))
    with pytest.raises(SystemExit) as ei:
        EC.load_identities(args)
    assert ei.value.code == 3
    c = EC.parse_canary(json.dumps({k: v for k, v in rows[0].items() if k not in ("key", "source_episode")}), v8=True)
    assert c["key"] == rows[0]["key"] and c["source_episode"] is None
    with pytest.raises(ValueError):
        EC.parse_canary("PickXtimes:3:510300", v8=True)


def test_旧xhard0模式回归(tmp_path):
    """旧接口：key=<task>_<seed>、check_identity 只认 xhard0、shuffle 按 source_episode、不截断不领额度。"""
    old = {"task": "PickXtimes", "source_episode": 3, "seed": 510300, "builder_episode": 0}
    assert EC.key_of(old) == "PickXtimes_510300"
    assert EC.check_identity({"tier": "xhard0", "seed": 510300, "source_episode": 3}, old) is None
    assert "tier" in EC.check_identity({"tier": "xhard1", "seed": 510300, "source_episode": 3}, old)
    assert EC.parse_canary("PickXtimes:3:510300")["builder_episode"] == 0
    rows = [dict(old, seed=510300 + i, source_episode=3 + 4 * i, builder_episode=i) for i in range(4)]
    assert [EC.key_of(x) for x in EC.order_identities(rows, "shuffle", 1)] == \
        [EC.key_of(x) for x in EC.order_identities(rows[::-1], "shuffle", 1)]


def test_zz_判定行():
    """汇总以上用例的事实打印判定行（须在本文件其余用例之后运行）。"""
    assert FACTS.get("smvla_v8") == 102 and FACTS.get("smvla_legacy") == 84
    assert FACTS.get("over", 0) == 0 and FACTS.get("exec_max") == CAP
    print(f"V8_STEP_CAP_CONTRACT=PASS cap={CAP} over={FACTS['over']} smvla_blocks_v8={FACTS['smvla_v8']} "
          f"smvla_blocks_legacy={FACTS['smvla_legacy']}")
