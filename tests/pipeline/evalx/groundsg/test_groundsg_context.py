"""GroundSG 官方定义摘取、变体隔离、互斥断言、整席上下文（1003 评估计划 1.3，子任务 S3）。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

import groundsg_fakes as F

OFFICIAL_ENV = {"IMAGE_MAX_TOKEN_NUM": "256", "VIDEO_MAX_TOKEN_NUM": "64", "FPS_MAX_FRAMES": "10"}
QWEN_ENV = {"USE_HF": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
OTHER_PREDICTORS = ("GeminiSubgoalPredictor", "MemERSubgoalPredictor", "NullSubgoalPredictor")


@pytest.fixture
def clean_env(monkeypatch):
    """被测代码直接写 os.environ；先经 monkeypatch 登记这些键，用例结束后恢复原值。"""
    for k in (*OFFICIAL_ENV, *QWEN_ENV):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_extract_defs_takes_only_named_source(tmp_path):
    od = F.official_defs()
    src = tmp_path / "m.py"
    src.write_text("import does_not_exist_anywhere\nX = 3\nY: int = 4\nos.environ['S3_PROBE'] = '1'\n"
                   "def f(a):\n    return a + X\n@dataclasses.dataclass\nclass C:\n    v: int = 1\n", encoding="utf-8")
    ns = od.extract_defs(src, ["X", "f", "C"])
    assert ns["f"](1) == 4 and ns["C"]().v == 1 and "Y" not in ns
    assert "S3_PROBE" not in os.environ  # 模块级副作用与 import 行不执行
    assert ns["__source_sha256__"] == hashlib.sha256(src.read_bytes()).hexdigest()
    with pytest.raises(KeyError):
        od.extract_defs(src, ["X", "missing_name"])


def test_official_sources_hashes_recorded(clean_env):
    F.print_official_sha()
    od = F.official_defs()
    defs = od.load_groundsg(F.QWENVL, with_env_runner=True, env_runner_extra={"BenchmarkEnvBuilder": object},
                            ws_module=od.ws_shim(lambda h, p: None))
    want = F.official_sha256()
    assert defs["sha256"] == want
    for k, v in OFFICIAL_ENV.items():
        assert os.environ[k] == v


def test_oracle_variant_never_loads_qwen(tmp_path, clean_env):
    side = F.NewSide(F.ORACLE, 60, tmp_path, F.World())
    defs = side.ctx["defs"]
    assert defs["qwen"] is None and "subgoal_prediction/qwenvl/api.py" not in defs["sha256"]
    pred_names = set(defs["predictor"])
    assert "OracleSubgoalPredictor" in pred_names and "QwenVLSubgoalPredictor" not in pred_names
    assert "Qwen3VLModel" not in pred_names and not any(n in pred_names for n in OTHER_PREDICTORS)
    assert type(side.ctx["predictor"]).__name__ == "OracleSubgoalPredictor"
    assert side.swift.engines == [] and "swift" not in sys.modules and "google.generativeai" not in sys.modules
    for k in QWEN_ENV:
        assert k not in os.environ
    args = side.ctx["args"]
    assert (args.use_oracle, args.use_qwenvl, args.use_gemini, args.use_memer) == (True, False, False, False)
    assert args.subgoal_type == "grounded_subgoal" and args.max_steps == 60 and args.obs_horizon == 16


def test_qwenvl_variant_loads_only_qwen_classes(tmp_path, clean_env):
    side = F.NewSide(F.QWENVL, 60, tmp_path, F.World())
    pred_names = set(side.ctx["defs"]["predictor"])
    assert "QwenVLSubgoalPredictor" in pred_names and "OracleSubgoalPredictor" not in pred_names
    assert not any(n in pred_names for n in OTHER_PREDICTORS)
    assert type(side.ctx["predictor"]).__name__ == "QwenVLSubgoalPredictor"
    # 引擎参数取官方原文：底座、adapter、flash_attention_2，构造一次、不读权重
    assert side.swift.engines == [{"model_id_or_path": "Qwen/Qwen3-VL-4B-Instruct", "adapters": [F.ADAPTER],
                                   "attn_impl": "flash_attention_2"}]
    for k, v in {**OFFICIAL_ENV, **QWEN_ENV}.items():
        assert os.environ[k] == v
    res = side.run(F.identity())
    assert res["status"] == "success"
    assert {json.dumps(r["config"], sort_keys=True) for r in side.swift.requests} == {
        json.dumps({"max_tokens": 128, "temperature": 0}, sort_keys=True)}


def test_variants_are_mutually_exclusive(tmp_path, clean_env):
    od = F.official_defs()
    defs = od.load_groundsg(F.ORACLE, with_env_runner=False, ws_module=od.ws_shim(lambda h, p: None))
    Args = defs["Args"]
    for kw in ({"use_oracle": True, "use_qwenvl": True}, {"use_oracle": False, "use_qwenvl": False},
               {"use_oracle": True, "use_gemini": True}, {"use_qwenvl": True, "use_memer": True}):
        args = Args(subgoal_type="grounded_subgoal", **kw)
        with pytest.raises(AssertionError):
            od.build_predictor(defs, args, tmp_path)
    with pytest.raises(ValueError):
        od.make_args(defs, variant=F.QWENVL, host="h", port=1, max_steps=10, adapter_path=None)
    mc = F.groundsg_client()
    for bad in (None, "ground-sg-gemini"):
        with pytest.raises(ValueError):
            mc.make_policy_context(dict(F.seat_info(F.ORACLE, 60, tmp_path), groundsg_variant=bad))


def test_run_episode_rejects_mismatched_context(tmp_path, clean_env):
    side = F.NewSide(F.ORACLE, 60, tmp_path, F.World())
    ec = F.env_client()
    for conn in ({"policy_context": {}, "groundsg_variant": F.ORACLE, "max_steps": 60},
                 {"policy_context": side.ctx, "groundsg_variant": F.QWENVL, "max_steps": 60},
                 {"policy_context": side.ctx, "groundsg_variant": F.ORACLE, "max_steps": 1300}):
        with pytest.raises((RuntimeError, ValueError)):
            side.mc.run_episode(object(), F.identity(), conn, ec.NullRecorder())


class _HybridBuilder:
    """真实 robomme_hard builder（hard-verify）只做身份解析；环境换成假环境（按解析出的 source_episode）。"""

    def __init__(self, task, dataset, max_steps, world):
        from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

        self.task, self.world = task, world
        self.real = BenchmarkEnvBuilder(env_id=task, dataset=dataset, action_space="joint_angle", max_steps=max_steps)

    def resolve_identity(self, ep):
        return self.real.resolve_identity(ep)

    def make_env_for_episode(self, ep, max_steps=None):
        return self.world.new_env(self.task, int(self.real.resolve_identity(ep)["source_episode"]))


def test_policy_context_built_once_per_seat(tmp_path, clean_env):
    """SeatRunner 两局：make_policy_context 只调一次（Qwen 引擎只构造一次），每局同一上下文，close 调一次。"""
    import types

    ec, mc = F.env_client(), F.groundsg_client()
    world = F.World(default=F.Plan(success_at=12))
    server, swift = F.FakeServer(), F.FakeSwift()
    calls = {"make": 0, "close": 0, "ctx": []}

    def make(seat_info):
        calls["make"] += 1
        return mc.make_policy_context(seat_info, client_factory=lambda h, p, ep: F.FakeClient(server),
                                      qwen_extra=swift.names)

    def run_episode(session, identity, conn_info, recorder):
        calls["ctx"].append(id(conn_info["policy_context"]))
        return mc.run_episode(session, identity, conn_info, recorder)

    def close(ctx):
        calls["close"] += 1
        mc.close_policy_context(ctx)

    mod = types.SimpleNamespace(make_policy_context=make, run_episode=run_episode, close_policy_context=close)
    args = ec.build_parser().parse_args([
        "run", "--policy", "groundsg", "--identities", "unused.json", "--dataset", "hard-verify", "--max-steps", "1300",
        "--groundsg-variant", F.QWENVL, "--qwenvl-groundsg-adapter", F.ADAPTER, "--trace-root", str(tmp_path / "trace"),
        "--cond", "N", "--seat", "00", "--port", "18120", "--out", str(tmp_path / "out"), "--first-extra-s", "0",
        "--ledger", str(tmp_path / "ledger.jsonl"), "--reset-budget", "10", "--infra-retry-budget", "0"])
    runner = ec.SeatRunner(args, policy_mod=mod,
                           builder_factory=lambda task, dataset, ms: _HybridBuilder(task, dataset, ms, world))
    rows = []
    for ep in (0, 1):
        ident = runner.builder_for("PickXtimes").resolve_identity(ep)
        rows.append({"task": "PickXtimes", "tier": ident["tier"], "seed": ident["seed"], "candidate": None,
                     "builder_episode": ep, "source_episode": ident["source_episode"], "spec_sha256": None,
                     "key": f"PickXtimes_xhard0_{ident['seed']}"})
    assert runner.run_identities(rows) == 0
    runner.close()
    assert calls["make"] == 1 and calls["close"] == 1 and len(set(calls["ctx"])) == 1 and len(calls["ctx"]) == 2
    assert len(swift.engines) == 1
    got = [json.loads(x) for x in (tmp_path / "out" / "results.jsonl").read_text().splitlines()]
    assert [(g["status"], g["exec_steps"], g["policy_variant"], g["side"], g["dataset"]) for g in got] == [
        ("success", 12, F.QWENVL, "new", "hard-verify")] * 2
    for g, r in zip(got, rows):
        tdir = tmp_path / "trace" / f"{r['key']}.a1"
        assert g["trace_path"] == str(tdir / "trace.jsonl") and (tdir / "trace.jsonl").is_file()
        assert not (tdir / "qwen-tmp").exists()
        assert [w.ep for w in world.envs] == [r["source_episode"] for r in rows]
