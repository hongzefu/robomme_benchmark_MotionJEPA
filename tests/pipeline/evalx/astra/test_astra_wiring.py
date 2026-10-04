"""S5 接线：新侧驱动把 Astra 的 ``runner.episode`` 接到真实 S1 builder 上（环境打桩、零外联）。

判定行：``ASTRA_WIRING=PASS api_calls=0 builder_dataset_ok=1``（由 ``test_astra_wiring_xhard0`` 通过时打印）。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from astra_fakes import (FakeEnv, FakeMonitor, FakeResponder, FakeVLA, NetCounter, astra_session, make_args,
                         make_deps, print_upstream_digests, recording_builder_cls, write_cases)

ALL_TASKS = ["BinFill", "StopCube", "PickXtimes", "SwingXtimes", "ButtonUnmask", "VideoUnmask", "VideoUnmaskSwap",
             "ButtonUnmaskSwap", "PickHighlight", "VideoRepick", "VideoPlaceButton", "VideoPlaceOrder", "MoveCube",
             "InsertPeg", "PatternLock", "RouteStick"]


def _trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_prepare_hard0_local_zero_is_official_episode_3():
    """第二档身份：16 任务各取官方 test episode 3，即 test-hard0 本地局号 0（手写期望，不读被测代码的表）。"""
    with astra_session() as (mod, astra):
        assert list(astra.core.TASKS) == ALL_TASKS
        doc = mod.prepare_cases(recording_builder_cls(), "test-hard0", ALL_TASKS, source_episodes=[3])
    assert doc["dataset"] == "test-hard0"
    assert len(doc["cases"]) == 16
    for case in doc["cases"]:
        assert case["episode"] == 0 and case["source_episode"] == 3 and case["tier"] == "xhard0"


def test_prepare_v9_connectivity_is_videounmask_xhard1_first():
    with astra_session() as (mod, _astra):
        cls = recording_builder_cls()
        doc = mod.prepare_cases(cls, "test-hard", ["VideoUnmask"], tier="xhard1", index=0)
        builder = cls("VideoUnmask", dataset="test-hard", action_space="joint_angle", gui_render=False, max_steps=1600)
    (case,) = doc["cases"]
    first_xhard1 = min(ep for ep in range(builder.get_episode_num()) if builder.resolve_identity(ep)["tier"] == "xhard1")
    assert case["task"] == "VideoUnmask" and case["tier"] == "xhard1" and case["episode"] == first_xhard1
    assert case["seed"] == builder.resolve_identity(first_xhard1)["seed"]


def test_astra_wiring_xhard0(tmp_path, monkeypatch):
    net = NetCounter().install(monkeypatch)
    with astra_session() as (mod, astra):
        print_upstream_digests(mod)
        tasks = ["VideoUnmask", "BinFill"]
        cls = recording_builder_cls(lambda b, ep: FakeEnv(terminal_step=40))
        doc = mod.prepare_cases(cls, "test-hard0", tasks, source_episodes=[3])
        cls.constructed.clear()
        cases = write_cases(tmp_path / "cases.json", doc)
        args = make_args(tmp_path, cases, max_steps=1300)
        checks, monitor, vla = [], FakeMonitor(), FakeVLA()
        responder = FakeResponder(astra.champ)
        deps = make_deps(astra, cls, monitor=monitor, vla=vla, responder=responder, check_calls=checks)
        out = mod.run_cases(args, deps)

    # ① validate_checkpoints 以启动参数调用一次
    assert checks == [(args.vla_checkpoint, args.monitor_adapter)]
    # builder：真实 S1 类，构造参数逐项手写期望
    assert cls.constructed == [
        {"env_id": t, "dataset": "test-hard0", "action_space": "joint_angle", "gui_render": False, "max_steps": 1300}
        for t in tasks]
    assert [c["episode"] for c in cls.make_calls] == [0, 0]
    assert all(c["args"] == () and c["kwargs"] == {} for c in cls.make_calls), "步数不得逐局覆盖"
    builder = cls("VideoUnmask", dataset="test-hard0", action_space="joint_angle", gui_render=False, max_steps=1300)
    assert builder.dataset == "test-hard0" and builder.max_steps_without_demonstration == 1302
    assert builder.resolve_identity(0)["source_episode"] == 3
    builder_dataset_ok = 1

    run = Path(args.output).parent
    assert run.parent.name == "group_0"
    results = out["results"]
    assert [r["status"] for r in results] == ["success", "success"]
    for task in tasks:
        ep = run / "results" / task / "ep000"
        for name in ("identity.json", "decisions.jsonl", "actions.npy", "result.json", "rollout.mp4", "trace.jsonl"):
            assert (ep / name).is_file(), name
        assert (ep / "monitor_inputs").is_dir()
        assert (ep / "rollout.mp4").stat().st_size > 0
        identity = json.loads((ep / "identity.json").read_text())
        assert identity["dataset"] == "test-hard0" and identity["episode"] == 0
        assert identity["seed_and_difficulty"][1] == "xhard0"
        result = json.loads((ep / "result.json").read_text())
        assert result["dataset"] == "test-hard0" and result["steps"] == 40 and result["planner_calls"] == 1
        assert np.load(ep / "actions.npy").shape == (40, 8)
        rows = _trace(ep / "trace.jsonl")
        assert rows[0]["kind"] == "header" and rows[0]["route"] == "astra-new" and rows[0]["max_steps"] == 1300
        assert rows[0]["identity"]["source_episode"] == 3 and rows[0]["identity"]["dataset"] == "test-hard0"
        assert rows[1]["kind"] == "demo" and rows[1]["frames"] == 3 and rows[1]["texts"] == ["pick up the cube"]
        steps = [r for r in rows if r["kind"] == "step"]
        assert [r["step"] for r in steps] == list(range(1, 41))
        assert all(r["subgoal"] for r in steps)
        names = [r["name"] for r in rows if r["kind"] == "request"]
        assert names.count("planner") == 1 and names.count("vla_infer") == 3 and names.count("monitor") == 2
        assert names[0] == "vla_reset"
        assert sum(1 for r in rows if r["kind"] == "response") == 3
        assert rows[-1]["kind"] == "end" and rows[-1]["status"] == "success" and rows[-1]["exec_steps"] == 40
    # planner_calls 为分片共用的一个目录，按请求 uuid 分子目录
    calls = sorted(p for p in (run / "planner_calls").iterdir())
    assert len(calls) == 2 and all((p / "request.json").is_file() and (p / "response.json").is_file() for p in calls)
    assert {json.loads((p / "request.json").read_text())["episode"] for p in calls} == {0}
    # ⑥ 正常结束写 PILOT_FINISHED.json
    finished = json.loads((run / "results" / "PILOT_FINISHED.json").read_text())
    assert finished["dataset"] == "test-hard0" and finished["tasks"] == tasks
    assert responder.calls == 2 and vla.resets == 2
    assert net.calls == 0
    print(f"ASTRA_WIRING=PASS api_calls={net.calls} builder_dataset_ok={builder_dataset_ok}")


def test_v9_connectivity_runs_exactly_1600_steps(tmp_path, monkeypatch):
    """V9 连通局：test-hard + 1600；环境永不结束时循环恰好执行 1600 步后记 timeout。"""
    net = NetCounter().install(monkeypatch)
    with astra_session() as (mod, astra):
        cls = recording_builder_cls(lambda b, ep: FakeEnv(terminal_step=None))
        doc = mod.prepare_cases(cls, "test-hard", ["VideoUnmask"], tier="xhard1", index=0)
        cls.constructed.clear()
        cases = write_cases(tmp_path / "cases.json", doc)
        args = make_args(tmp_path, cases, max_steps=1600)
        monkeypatch.setattr(astra.runner.imageio, "get_writer", lambda *a, **k: _NullWriter())
        deps = make_deps(astra, cls, monitor=FakeMonitor(), vla=FakeVLA(), responder=FakeResponder(astra.champ),
                         check_calls=[])
        out = mod.run_cases(args, deps)
    assert cls.constructed == [{"env_id": "VideoUnmask", "dataset": "test-hard", "action_space": "joint_angle",
                                "gui_render": False, "max_steps": 1600}]
    (result,) = out["results"]
    assert result["status"] == "timeout" and result["steps"] == 1600
    assert cls.make_calls[0]["episode"] == doc["cases"][0]["episode"]
    ep = Path(args.output) / "VideoUnmask" / f"ep{doc['cases'][0]['episode']:03d}"
    rows = _trace(ep / "trace.jsonl")
    assert rows[-1]["exec_steps"] == 1600 and rows[-1]["terminal_reason"] == "loop_exit"
    assert rows[0]["identity"]["tier"] == "xhard1"
    assert net.calls == 0


class _NullWriter:
    def append_data(self, frame):
        pass

    def close(self):
        pass


@pytest.mark.parametrize("dataset,max_steps", [("test-hard0", 1600), ("test-hard", 1300)])
def test_step_cap_pairing_blocks_before_any_side_effect(tmp_path, dataset, max_steps):
    with astra_session() as (mod, astra):
        cls = recording_builder_cls()
        doc = (mod.prepare_cases(cls, dataset, ["VideoUnmask"], source_episodes=[3]) if dataset == "test-hard0"
               else mod.prepare_cases(cls, dataset, ["VideoUnmask"], tier="xhard1", index=0))
        args = make_args(tmp_path, write_cases(tmp_path / "cases.json", doc), max_steps=max_steps)
        responder = FakeResponder(astra.champ)
        with pytest.raises(ValueError, match="step_cap_pairing"):
            mod.run_cases(args, make_deps(astra, cls, monitor=FakeMonitor(), vla=FakeVLA(), responder=responder,
                                          check_calls=[]))
    assert not Path(args.output).exists() and responder.calls == 0


def test_layout_requires_group_dir(tmp_path):
    with astra_session() as (mod, astra):
        cls = recording_builder_cls()
        doc = mod.prepare_cases(cls, "test-hard0", ["VideoUnmask"], source_episodes=[3])
        args = make_args(tmp_path, write_cases(tmp_path / "cases.json", doc), max_steps=1300, group="not_a_group")
        with pytest.raises(ValueError, match="reason=layout"):
            mod.run_cases(args, make_deps(astra, cls, check_calls=[]))
    assert not Path(args.output).exists()


@pytest.mark.parametrize("existing", ["output", "spool"])
def test_existing_output_or_spool_is_refused(tmp_path, existing):
    """② 两个目录都必须是新的（上游 main() 的 mkdir(exist_ok=False) 口径）。"""
    with astra_session() as (mod, astra):
        cls = recording_builder_cls()
        doc = mod.prepare_cases(cls, "test-hard0", ["VideoUnmask"], source_episodes=[3])
        args = make_args(tmp_path, write_cases(tmp_path / "cases.json", doc), max_steps=1300)
        Path(getattr(args, existing)).mkdir(parents=True)
        responder = FakeResponder(astra.champ)
        with pytest.raises(ValueError, match="existing evidence is preserved"):
            mod.run_cases(args, make_deps(astra, cls, monitor=FakeMonitor(), vla=FakeVLA(), responder=responder,
                                          check_calls=[]))
    assert responder.calls == 0


def test_real_validate_checkpoints_rejects_fake_dirs(tmp_path):
    """① 用上游真实 validate_checkpoints：假目录在任何目录创建与请求之前被拒。"""
    with astra_session() as (mod, astra):
        cls = recording_builder_cls()
        doc = mod.prepare_cases(cls, "test-hard0", ["VideoUnmask"], source_episodes=[3])
        args = make_args(tmp_path, write_cases(tmp_path / "cases.json", doc), max_steps=1300)
        responder = FakeResponder(astra.champ)
        with pytest.raises(ValueError, match="Missing checkpoint component"):
            mod.run_cases(args, make_deps(astra, cls, monitor=FakeMonitor(), vla=FakeVLA(), responder=responder))
    assert not Path(args.output).exists() and responder.calls == 0


def test_identity_mismatch_blocks_before_requests(tmp_path):
    with astra_session() as (mod, astra):
        cls = recording_builder_cls()
        doc = mod.prepare_cases(cls, "test-hard0", ["VideoUnmask"], source_episodes=[3])
        doc["cases"][0]["source_episode"] = 7
        args = make_args(tmp_path, write_cases(tmp_path / "cases.json", doc), max_steps=1300)
        responder = FakeResponder(astra.champ)
        with pytest.raises(ValueError, match="身份不符"):
            mod.run_cases(args, make_deps(astra, cls, monitor=FakeMonitor(), vla=FakeVLA(), responder=responder,
                                          check_calls=[]))
    assert responder.calls == 0


def test_env_sources_point_to_repo_src():
    with astra_session() as (mod, _astra):
        files = mod.assert_env_sources()
    src = str(mod.REPO_SRC.resolve())
    assert files["robomme_hard"].startswith(src) and files["robomme"].startswith(src)
