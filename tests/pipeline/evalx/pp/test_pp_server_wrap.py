"""PonderPounce 服务外壳 ``pp_server_wrap.py``（S5）的等价性与子目标语义（日常门禁，CPU）。

外壳子类化 ``ponderpounce.eval.robomme_server.PonderPounceRoboMMEServer``（子模块 ``723df357``，文件 sha256 钉死）。
本测试用**父类真实方法**（``on_episode_start``／``on_observation``／``_fire_s2``／``_visible_cognition``／``_fire_s1``／
``_dispense``／``_hold`` 原文）驱动原类与外壳各跑一局，只把两处重模型换成 CPU 桩：

- System 2：替换模块全局 ``SoftS2SessionContext`` 为脚本化桩（按触发序号给 cognition 张量与子目标文本），
  父类 ``_fire_s2`` 的计时、``ready_at_ns``、``cognitions`` 截断逻辑照常运行；
- System 1：``_s1`` 换成确定性桩（``noise_spec``、``null_cognition``、``predict_action``），父类照常用本局
  ``noise_rng`` 抽噪声。

逐步比较两者的动作（dtype／shape／字节）、随机数发生器状态、``cursor``、chunk 内容、触发计数与节拍；除外壳新增
的 ``subgoal`` 与 ``_sgeval_audit`` 键外必须一致，打印 ``PP_SERVER_ACTION_EQ=PASS``。第三阶段另核：``SGEVAL_AUDIT=0``
时回包没有审计键、其余与开启时逐项相同；开启时审计键里的 System 2 生成块逐次对上桩的真实 ``fire`` 结果（不多一次、
不少一次），打印 ``PP_AUDIT_OBS_EQ=PASS``。外壳回传的子目标与测试按节拍算式独立推出的期望
逐步比对（首个子目标可见前为 ``None``、``ready_at_ns`` 之前仍回旧子目标、chunk 用尽后不变）。

父类依赖 vla-eval、torch、transformers，主检出 ``.venv`` 没有 vla-eval，故等价部分在子进程里用主检出 client-env
的解释器（``artifacts/sg-evaluation/venvs/client-env``，含 vla-eval 0.7.0 与 torch，CPU）跑本文件的 ``--child`` 分支，
PonderPounce 源码只读引用主检出 ``third_party/PonderPounce``（可用 ``SGEVAL_PP_PYTHON``／``SGEVAL_THIRD_PARTY`` 覆盖）。
解释器或源码缺失时测试失败，不跳过。子进程沿用本进程的 ``PYTHONPATH``（资源守卫的 sitecustomize 随之生效）。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
WRAP = REPO / "scripts" / "eval-official" / "pp_server_wrap.py"
PP_GITLINK = "723df35762bb641e1d520e4fa9359b98644adc21"
PARENT_REL = "ponderpounce/eval/robomme_server.py"
PARENT_SHA256 = "0664c0abc1598c68f75a8f2eaf2889062a34e39d4e1d75269512907a8f1cb135"
CLIENT_ENV_PY = "artifacts/sg-evaluation/venvs/client-env/bin/python"

# 节拍（毫秒）与 System 2 桩的子目标脚本；dt = 1000/20 = 50 ms
DT_MS = 50
CHUNK = 5
N_STEPS = 200
SCHEDULES = [
    # 默认节拍：Ponder／Pounce 各 1000 ms，计算延迟 400 ms
    {"name": "p1000_s1000_d400", "s2_ms": 1000, "s1_ms": 1000, "delay_ms": 400,
     "subgoals": ["", "", "pick up the cube at [612, 247]", "", "put it at [10, 990]", "", "", "press at [500, 500]"]},
    # 节拍不等、延迟长于周期：同一时刻有多条未可见 cognition，最新可见的可能是空子目标
    {"name": "p500_s1000_d1300", "s2_ms": 500, "s1_ms": 1000, "delay_ms": 1300,
     "subgoals": ["", "open the drawer", "", "", "", "grab at [100, 900]", "", "", "", "", "", "lift"]},
]


# ── 子进程：在有 vla-eval／torch 的解释器里驱动父类真实方法 ─────────────────────────────


def _child_main(mode: str) -> None:  # pragma: no cover - 在子进程里运行
    import asyncio
    import importlib.util
    import inspect
    import re
    import types

    import numpy as np
    import torch

    import ponderpounce.eval.robomme_server as rs

    spec = importlib.util.spec_from_file_location("pp_server_wrap", os.environ["SGEVAL_PP_WRAP"])
    wrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrap)
    assert wrap.PonderPounceRoboMMEServer is rs.PonderPounceRoboMMEServer
    ns = rs.NS_PER_MS

    class StubS2Context:
        """``SoftS2SessionContext`` 的桩：第 n 次 ``fire`` 给 ``subgoals[n % L]`` 与确定性 cognition。"""

        subgoals: list = []

        def __init__(self, *, session, system2, device, dtype, max_new_tokens):
            self.n = 0

        def fire(self, pils):
            img = float(np.asarray(pils[0], dtype=np.float32).mean()) / 255.0
            text = self.subgoals[self.n % len(self.subgoals)]
            cog = torch.full((2, 4), float(self.n), dtype=torch.float32) + img
            self.n += 1
            return rs.S2ContextResult(subgoal_tokens=None, subgoal_text=text, cognition=cog, kind="stub",
                                      gate_score=None, n_input_frames=1)

    class StubS1:
        """``LocalSystem1`` 的桩：动作块只由输入与父类抽出的噪声决定。"""

        action_chunk_size, action_dim = CHUNK, 8
        noise_spec = (CHUNK, 8)
        null_cognition = torch.zeros(2, 4)

        def predict_action(self, **kw):
            out = kw["noise"][0] * 0.05 + kw["cognition"].mean() * 0.1 + kw["images"].mean() * 0.01
            out = out + kw["age_ms"][0] * 1e-4
            if kw.get("proprio") is not None:
                out = out + kw["proprio"][0].sum() * 1e-3
            return out.unsqueeze(0)

    def s1_transform(pil):
        return torch.from_numpy(np.asarray(pil, dtype=np.float32) / 255.0).permute(2, 0, 1)

    def build(cls, sch):
        srv = cls.__new__(cls)
        super(rs.PonderPounceRoboMMEServer, srv).__init__()
        srv._device, srv._dtype = torch.device("cpu"), torch.float32
        srv._dt_ns = int(round(1e9 / (1000.0 / DT_MS)))
        srv._s2_period_ns, srv._s1_period_ns = sch["s2_ms"] * ns, sch["s1_ms"] * ns
        srv._wait_first_cognition = True
        srv._camera_keys = ("agentview", "wrist")
        srv._seed = 0
        srv._episodes, srv._episode_counts = {}, {}
        srv._s2_delay_ns = int(sch["delay_ms"] * ns)
        srv._model, srv._norm_stats = None, None
        srv._s1 = StubS1()
        srv._s2 = types.SimpleNamespace(num_cognition_tokens=2)
        srv._s2_processor, srv._s2_max_new_tokens, srv._subgoal_grounded = None, 40, False
        srv._s1_transform = s1_transform
        srv._adapter = rs.ObsAdapter(camera_keys=srv._camera_keys, proprio_dim=8, max_demo_frames=0,
                                     norm_stats=None, demo_fps=0.0, env_fps=1000.0 / DT_MS)
        srv._s1_tokenizer, srv._s1_max_token_len, srv._s1_num_camera_slots = None, 0, 0
        return srv

    # 父类 __init__ 设的属性必须全部由桩设好（上游加字段时这里先报）
    init_src = inspect.getsource(rs.PonderPounceRoboMMEServer.__init__)
    init_attrs = sorted(set(re.findall(r"self\.(_\w+)\s*(?::[^=\n]+)?=", init_src)))

    class Ctx:
        def __init__(self, sid):
            self.session_id = sid
            self.sent = []

        async def send_action(self, a):
            self.sent.append(a)

    def obs_at(t):
        rng = np.random.default_rng([7, t])
        o = {"images": {"agentview": rng.integers(0, 256, (8, 8, 3), dtype=np.uint8),
                        "wrist": rng.integers(0, 256, (8, 8, 3), dtype=np.uint8)},
             "task_description": "pick up the cube", "states": rng.normal(size=8).astype(np.float32)}
        if t == 0:
            o["video_history"] = [rng.integers(0, 256, (8, 8, 3), dtype=np.uint8) for _ in range(3)]
            o["episode_restart"] = True
        return o

    def arr_rec(a):
        a = np.ascontiguousarray(np.asarray(a))
        return [a.dtype.str, list(a.shape), hashlib.sha256(a.tobytes()).hexdigest()]

    async def run(cls, sch):
        StubS2Context.subgoals = sch["subgoals"]
        srv = build(cls, sch)
        missing = [a for a in init_attrs if not hasattr(srv, a)]
        sid = "T|0|0"
        ctx = Ctx(sid)
        await srv.on_episode_start({"task": {"name": "T", "env_id": "T", "episode_idx": 0},
                                    "recording": {"sid": sid, "eid": sid, "eval_id": "", "db_path": ""}}, ctx)
        steps = []
        for t in range(N_STEPS):
            await srv.on_observation(obs_at(t), ctx)
            ep = srv._episodes[sid]
            a = ctx.sent[-1]
            steps.append({
                "keys": sorted(a), "actions": arr_rec(a["actions"]), "subgoal": a.get("subgoal", "<absent>"),
                "audit": a.get("_sgeval_audit", "<absent>"),
                "tick": ep.tick, "n_s1": ep.n_s1_fires, "n_s2": ep.n_s2_fires, "s1_started": ep.s1_started,
                "s1_next": ep.s1_next_fire_ns, "s2_next": ep.s2_next_fire_ns, "n_cogs": len(ep.cognitions),
                "cursor": None if ep.chunk is None else ep.chunk.cursor,
                "chunk": None if ep.chunk is None else arr_rec(ep.chunk.actions.numpy()),
                "rng": hashlib.sha256(ep.noise_rng.get_state().numpy().tobytes()).hexdigest(),
                "active_subgoal": ep.active_subgoal})
        await srv.on_episode_end({}, ctx)
        return steps, missing

    def compare(a_steps, b_steps):
        bad = 0
        for x, y in zip(a_steps, b_steps):
            xs = {k: v for k, v in x.items() if k not in ("subgoal", "keys", "audit")}
            ys = {k: v for k, v in y.items() if k not in ("subgoal", "keys", "audit")}
            keys_ok = sorted(set(y["keys"]) - {"subgoal", "_sgeval_audit"}) == x["keys"] and "subgoal" in y["keys"]
            bad += int(xs != ys or not keys_ok)
        return bad + abs(len(a_steps) - len(b_steps))

    rs.SoftS2SessionContext = StubS2Context
    out = {"parent_file": rs.__file__, "init_attrs": init_attrs, "schedules": []}
    for sch in SCHEDULES:
        base_steps, miss = asyncio.run(run(rs.PonderPounceRoboMMEServer, sch))
        wrap_steps, _ = asyncio.run(run(wrap.SubgoalReportingServer, sch))
        rec = {"name": sch["name"], "mismatch": compare(base_steps, wrap_steps), "missing_attrs": miss,
               "base_has_subgoal_key": any("subgoal" in s["keys"] for s in base_steps),
               "subgoals": [s["subgoal"] for s in wrap_steps], "cursor": [s["cursor"] for s in wrap_steps],
               "n_s1": [s["n_s1"] for s in wrap_steps], "n_s2": [s["n_s2"] for s in wrap_steps],
               "s1_started": [s["s1_started"] for s in wrap_steps], "rng_final": wrap_steps[-1]["rng"]}
        # 观察开关对照：SGEVAL_AUDIT=0 时外壳不加审计键，其余（动作、随机数、游标、计数、子目标）与开启时逐项相同
        prev = os.environ.get("SGEVAL_AUDIT")
        os.environ["SGEVAL_AUDIT"] = "0"
        try:
            off_steps, _ = asyncio.run(run(wrap.SubgoalReportingServer, sch))
        finally:
            if prev is None:
                os.environ.pop("SGEVAL_AUDIT", None)
            else:
                os.environ["SGEVAL_AUDIT"] = prev
        strip = lambda st: [{k: v for k, v in x.items() if k not in ("audit", "keys")} for x in st]  # noqa: E731
        rec["audit_off_has_key"] = any("_sgeval_audit" in x["keys"] for x in off_steps)
        rec["audit_on_all_keyed"] = all("_sgeval_audit" in x["keys"] for x in wrap_steps)
        rec["audit_on_off_mismatch"] = sum(int(a_ != b_) for a_, b_ in zip(strip(off_steps), strip(wrap_steps))) \
            + abs(len(off_steps) - len(wrap_steps))
        fires = [f for x in wrap_steps for f in x["audit"]["pp_generation"]["fires"]]
        rec["audit_fire_subgoals"] = [f["subgoal_text"] for f in fires]
        rec["audit_fire_index"] = [f["fire_index"] for f in fires]
        rec["audit_kinds"] = sorted({f["kind"] for f in fires})
        if mode == "mutant":  # 比较器自检：多抽一次随机数的「坏外壳」必须被查出
            class RngMutant(wrap.SubgoalReportingServer):
                def _fire_s1(self, ep, obs, now):
                    torch.randn(1, generator=ep.noise_rng)
                    super()._fire_s1(ep, obs, now)

            class CursorMutant(wrap.SubgoalReportingServer):
                def _dispense(self, ep, obs):
                    out_ = super()._dispense(ep, obs)
                    if ep.chunk is not None and ep.chunk.cursor < CHUNK:
                        ep.chunk.cursor += 1
                    return out_

            rec["mutant_rng"] = compare(base_steps, asyncio.run(run(RngMutant, sch))[0])
            rec["mutant_cursor"] = compare(base_steps, asyncio.run(run(CursorMutant, sch))[0])
        out["schedules"].append(rec)
    print("CHILD_RESULT " + json.dumps(out), flush=True)


# ── pytest 一侧 ─────────────────────────────────────────────────────────────


def _main_checkout() -> Path:
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                         capture_output=True, text=True, timeout=30)
    return Path(out.stdout.strip()).parent if out.returncode == 0 and out.stdout.strip() else REPO


def _pp_root() -> Path:
    tp = os.environ.get("SGEVAL_THIRD_PARTY")
    root = Path(tp) / "PonderPounce" if tp else _main_checkout() / "third_party" / "PonderPounce"
    assert (root / PARENT_REL).is_file(), f"PonderPounce 源码不在场（设 SGEVAL_THIRD_PARTY）：{root}"
    return root


def _pp_python() -> str:
    py = os.environ.get("SGEVAL_PP_PYTHON") or str(_main_checkout() / CLIENT_ENV_PY)
    assert Path(py).exists(), f"带 vla-eval／torch 的解释器不在场（设 SGEVAL_PP_PYTHON）：{py}"
    return py


def _child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(_pp_root()), env.get("PYTHONPATH", "")) if p)
    env["SGEVAL_PP_WRAP"] = str(WRAP)
    env["CUDA_VISIBLE_DEVICES"] = ""
    return env


_CACHE: dict = {}


def _child(mode: str) -> dict:
    if mode not in _CACHE:
        out = subprocess.run([_pp_python(), str(Path(__file__).resolve()), "--child", mode], cwd=REPO,
                             env=_child_env(), capture_output=True, text=True, timeout=240)
        lines = [ln for ln in out.stdout.splitlines() if ln.startswith("CHILD_RESULT ")]
        assert out.returncode == 0 and lines, f"子进程失败 rc={out.returncode}\n{out.stdout[-3000:]}\n{out.stderr[-3000:]}"
        _CACHE[mode] = json.loads(lines[-1][len("CHILD_RESULT "):])
    return _CACHE[mode]


def _expected_subgoals(sch: dict, n_steps: int) -> tuple[list, list]:
    """按父类节拍算式独立推出每步应回的子目标（不读被测代码）。返回 ``(逐步期望, S1 触发步号)``。

    Ponder 第 j 次在 ``dt + j*P2`` 触发、``+ delay`` 后可见；Pounce 在首条可见后的第一个控制步起每 ``P1`` 触发；
    触发时取「已可见且非空」的最新子目标（没有则沿用上次，局初为 None）；两次触发之间回同一个值，未起步时 None。"""
    dt, p2, p1, delay = DT_MS, sch["s2_ms"], sch["s1_ms"], sch["delay_ms"]
    subs = sch["subgoals"]
    fire_t = lambda j: dt + j * p2  # noqa: E731
    expected, fires = [], []
    s1_next = None
    current = None
    for k in range(1, n_steps + 1):
        now = k * dt
        if s1_next is None and fire_t(0) + delay <= now:
            s1_next = now
        if s1_next is not None and now >= s1_next:
            vis = [j for j in range(0, (now - dt) // p2 + 1) if fire_t(j) + delay <= now and subs[j % len(subs)]]
            if vis:
                current = subs[max(vis) % len(subs)]
            fires.append(k)
            s1_next += p1
        expected.append(current if fires else None)
    return expected, fires


def test_parent_class_is_pinned():
    src = (_pp_root() / PARENT_REL).read_bytes()
    out = subprocess.run(["git", "ls-tree", "HEAD", "third_party/PonderPounce"], cwd=REPO, capture_output=True,
                         text=True, timeout=30)
    assert PP_GITLINK in out.stdout, out.stdout
    assert hashlib.sha256(src).hexdigest() == PARENT_SHA256
    text = src.decode()
    for frag in ("def _fire_s1(self, ep: Episode, obs: Observation, now: int) -> None:",
                 "def _dispense(self, ep: Episode, obs: Observation) -> Action:",
                 "def _visible_cognition(ep: Episode, now: int) -> Cognition | None:",
                 "ep.chunk = Chunk(actions=chunk, raw_state=raw_state)", "await ctx.send_action(self._dispense(ep, obs))"):
        assert frag in text, frag


def test_wrapper_actions_rng_cursor_counts_identical_to_parent():
    res = _child("eq")
    assert Path(res["parent_file"]).resolve() == (_pp_root() / PARENT_REL).resolve()
    assert "_s1" in res["init_attrs"] and "_adapter" in res["init_attrs"]
    total = 0
    for rec in res["schedules"]:
        assert rec["missing_attrs"] == [], rec["missing_attrs"]
        assert rec["base_has_subgoal_key"] is False
        assert rec["mismatch"] == 0, rec["name"]
        assert rec["n_s1"][-1] >= 5 and rec["n_s2"][-1] >= 9  # 非空跑：两套节拍都触发了多次
        total += len(rec["subgoals"])
    print(f"PP_SERVER_ACTION_EQ=PASS schedules={len(res['schedules'])} steps={total} mismatch=0 "
          f"parent_sha256={PARENT_SHA256[:12]}")


def test_wrapper_subgoal_semantics_match_schedule():
    res = _child("eq")
    by_name = {r["name"]: r for r in res["schedules"]}
    for sch in SCHEDULES:
        rec = by_name[sch["name"]]
        got = rec["subgoals"]
        want, fires = _expected_subgoals(sch, N_STEPS)
        assert got == want, (sch["name"], [(i + 1, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w][:5])
        # S1 触发步与父类计数一致（期望推导本身没错位）
        n_s1 = rec["n_s1"]
        assert [i + 1 for i in range(N_STEPS) if n_s1[i] != (n_s1[i - 1] if i else 0)] == fires
        # 首个子目标前为 None：起步前（hold）与「首条可见 cognition 子目标为空」的触发都回 None
        first_fire = fires[0]
        assert all(g is None for g in got[:first_fire])
        assert got[first_fire - 1] is None and rec["s1_started"][first_fire - 1] is True
        # chunk 用尽（cursor == CHUNK）后子目标不变：等于该 chunk 触发那一步的值
        exhausted = [i for i, c in enumerate(rec["cursor"]) if c == CHUNK]
        assert exhausted
        for i in exhausted:
            k = max(f for f in fires if f <= i + 1)
            assert got[i] == got[k - 1]
        # ready_at_ns 之前回旧子目标：新子目标已由 Ponder 产出、但还未可见时，回的仍是更早的子目标
        subs = sch["subgoals"]
        stale = 0
        for i, g in enumerate(got):
            now = (i + 1) * DT_MS
            produced = [j for j in range(0, (now - DT_MS) // sch["s2_ms"] + 1) if subs[j % len(subs)]]
            if produced and g is not None and subs[max(produced) % len(subs)] != g:
                stale += 1
        assert stale > 0, sch["name"]
    # 第二套节拍专门覆盖「触发时最新可见的 cognition 子目标为空，仍沿用更早的非空子目标」
    sch_b = SCHEDULES[1]
    _, fires_b = _expected_subgoals(sch_b, N_STEPS)
    newest_visible_empty = 0
    for k in fires_b:
        now = k * DT_MS
        vis = [j for j in range(0, (now - DT_MS) // sch_b["s2_ms"] + 1) if DT_MS + j * sch_b["s2_ms"] + sch_b["delay_ms"] <= now]
        if vis and not sch_b["subgoals"][max(vis) % len(sch_b["subgoals"])] and by_name[sch_b["name"]]["subgoals"][k - 1]:
            newest_visible_empty += 1
    assert newest_visible_empty > 0


def test_comparator_detects_rng_and_cursor_mutants():
    res = _child("mutant")
    for rec in res["schedules"]:
        assert rec["mismatch"] == 0
        assert rec["mutant_rng"] > 0 and rec["mutant_cursor"] > 0, rec["name"]


def test_entrypoint_accepts_same_args_as_original_server():
    """按绝对路径、cwd 在第三方目录启动：jsonargparse 识别与原服务相同的 ``--args.*``（只看 --help，不加载权重）。"""
    root = _pp_root()
    out = subprocess.run([_pp_python(), str(WRAP), "--help"], cwd=root, env=_child_env(), capture_output=True,
                         text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-3000:]
    for flag in ("--args.checkpoint_path", "--args.seed", "--args.s1_period_ms", "--port"):
        assert flag in out.stdout, flag
    assert "SubgoalReportingServer" in out.stdout


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "--child":
    _child_main(sys.argv[2])


def test_audit_switch_and_generation_blocks_observe_only():
    """第三阶段（接口冻结说明五节）：SGEVAL_AUDIT=0 时没有审计键、其余逐项与开启时相同；开启时每次回包都带审计键，
    且审计里的 System 2 生成块与桩的真实 fire 一一对应（第 j 次 fire 的子目标 = 脚本第 j % L 条，序号连续、总数等于
    父类 Ponder 计数）——外壳不多推理、不少记。"""
    res = _child("eq")
    for sch in SCHEDULES:
        rec = next(r for r in res["schedules"] if r["name"] == sch["name"])
        assert rec["audit_off_has_key"] is False and rec["audit_on_all_keyed"] is True
        assert rec["audit_on_off_mismatch"] == 0, sch["name"]
        n_s2 = rec["n_s2"][-1]
        subs = sch["subgoals"]
        assert rec["audit_fire_index"] == list(range(n_s2))
        assert rec["audit_fire_subgoals"] == [subs[j % len(subs)] for j in range(n_s2)]
        assert rec["audit_kinds"] == ["stub"]
    print(f"PP_AUDIT_OBS_EQ=PASS schedules={len(SCHEDULES)} audit_on_off_mismatch=0")
