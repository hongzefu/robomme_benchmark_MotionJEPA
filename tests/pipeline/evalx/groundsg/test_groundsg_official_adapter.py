"""GroundSG 新侧适配与官方循环的逐项一致（1003 评估计划 1.3，子任务 S3；判定行 OFFICIAL_ADAPTER）。

两侧都跑官方 ``EpisodeEvaluator.eval_each_episode`` 原文：新侧经 ``mmesg_client.SessionRunner`` 委托到真实
``EnvSession``，原侧经 ``official_hard_runner`` 用官方 ``EnvRunner`` 原文 + 官方 builder 替身。两侧给同一组假环境
（下一帧由所执行动作决定）、各自一个同实现的假服务（动作块由本局请求指纹决定）、各自一份 swift 替身——任何
一个请求、动作或子目标不同都会向后传播。比较三类：请求（轨迹 request 行、假服务收到的指纹、Qwen 请求）、
执行（环境收到的动作字节、轨迹 step 行）、终态（status／步数／error 与轨迹 end 行）。

另有手写期望（不调用被测代码推出）：消息顺序、首批帧数与 exec_start_idx、提示词与 Oracle 子目标、执行动作 = 各
动作块前 16 行；``count > max_steps`` 才 timeout（max_steps=1300 时执行 1301 步、原侧帧数 3 + 1301）；``--strict-cap``
下第 max_steps+1 步不进环境；官方 ``unknown`` 记 error 且不中止后续局。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import groundsg_fakes as F

SCENARIOS = {
    "success": (F.Plan(success_at=37), 60),
    "fail": (F.Plan(fail_at=20), 60),
    "timeout": (F.Plan(), 40),
    "unknown": (F.Plan(unknown_at=10), 60),
    "env_raise": (F.Plan(raise_at=5), 60),
}


def run_pair(variant: str, plan: F.Plan, max_steps: int, tmp: Path, ident: dict | None = None):
    ident = ident or F.identity()
    wn, wo = F.World(default=plan), F.World(default=plan)
    new, orig = F.NewSide(variant, max_steps, tmp / "new", wn), F.OrigSide(variant, max_steps, tmp / "orig", wo)
    rn, ro = new.run(ident), orig.run(ident)
    return (new, wn, rn), (orig, wo, ro)


def test_official_adapter_matches_official_loop(tmp_path):
    F.print_official_sha()
    total = {"payload": 0, "exec": 0, "terminal": 0}
    seen = {}
    for variant in F.VARIANTS:
        for name, (plan, max_steps) in SCENARIOS.items():
            n, o = run_pair(variant, plan, max_steps, tmp_path / variant / name)
            d = F.diffs(n, o)
            assert d["n_req"] > 0 and d["n_exec"] > 0, (variant, name, d)
            for k in total:
                total[k] += d[k]
            seen[(variant, name)] = (n[2]["status"], n[2]["steps"], n[2]["error"])
            assert d["payload"] == d["exec"] == d["terminal"] == 0, (variant, name, d)
    # 终态手写：每种情形两变体相同
    for variant in F.VARIANTS:
        assert seen[(variant, "success")][:2] == ("success", 37)
        assert seen[(variant, "fail")][:2] == ("fail", 20)
        assert seen[(variant, "timeout")][:2] == ("timeout", 41)  # count > 40 才 timeout：执行 41 步
        assert seen[(variant, "unknown")] == ("error", 10, "success_flag=unknown")
        st, steps, err = seen[(variant, "env_raise")]
        assert st == "error" and steps == 5 and err.startswith("AttributeError"), seen[(variant, "env_raise")]
    print(f"OFFICIAL_ADAPTER=PASS variants={len(F.VARIANTS)} payload_diff={total['payload']} "
          f"exec_diff={total['exec']} terminal_diff={total['terminal']}")


def test_comparison_is_not_trivial(tmp_path):
    """换一局（source_episode 不同）后两侧请求与动作必须不同：等式非平凡。"""
    (new, wn, rn), _ = run_pair(F.ORACLE, F.Plan(success_at=37), 60, tmp_path / "a")
    (new2, wn2, rn2), _ = run_pair(F.ORACLE, F.Plan(success_at=37), 60, tmp_path / "b",
                                   ident=F.identity(source_episode=7, builder_episode=1, seed=510700))
    assert [x[1] for x in new.server.log] != [x[1] for x in new2.server.log]
    assert wn.envs[0].actions[0].tobytes() != wn2.envs[0].actions[0].tobytes()


def test_oracle_messages_hand_expected(tmp_path):
    """手写期望：消息顺序、首批 reset 帧、提示词、Oracle 子目标、执行动作 = 每块前 16 行。"""
    (new, wn, rn), _ = run_pair(F.ORACLE, F.Plan(success_at=37), 60, tmp_path)
    kinds = [k for k, _, _ in new.server.log]
    assert kinds == ["reset", "add_buffer", "infer", "add_buffer", "infer", "add_buffer", "infer"]
    bufs = [m for k, _, m in new.server.log if k == "add_buffer"]
    assert (bufs[0]["n_frames"], bufs[0]["exec_start_idx"]) == (F.N_RESET_FRAMES, F.N_RESET_FRAMES - 1)
    assert [(b["n_frames"], b["exec_start_idx"]) for b in bufs[1:]] == [(16, 0), (16, 0)]
    infers = [m for k, _, m in new.server.log if k == "infer"]
    goal = F.goal_of("PickXtimes", 3)
    # 决策发生在第 0、16、32 步之后：Oracle 取当时 info 的 grounded_subgoal_online
    assert [m["prompt"] for m in infers] == [goal] * 3
    assert [m["grounded_subgoal"] for m in infers] == [F.subgoal_at(0), F.subgoal_at(16), F.subgoal_at(32)]
    assert [m["simple_subgoal"] for m in infers] == [m["grounded_subgoal"] for m in infers]
    want = np.concatenate([c[:F.EXEC_HORIZON] for c in new.server.chunks])[:37]
    got = np.stack(wn.envs[0].actions)
    assert got.shape == (37, 8) and got.tobytes() == want.tobytes()
    assert rn["decisions"] == 3 and rn["side"] == "new" and rn["demo_frames"] == F.N_RESET_FRAMES - 1


def test_mme_loop_times_out_only_after_count_exceeds_1300(tmp_path):
    """官方 ``count > max_steps``：max_steps=1300 时两侧都真实执行 1301 步再记 timeout；原侧外围帧含第 1301 步。"""
    (new, wn, rn), (orig, wo, ro) = run_pair(F.ORACLE, F.Plan(), 1300, tmp_path)
    assert (rn["status"], rn["steps"], rn["_session_steps"]) == ("timeout", 1301, 1301)
    assert (ro["status"], ro["exec_steps"]) == ("timeout", 1301)
    assert len(wn.envs[0].actions) == len(wo.envs[0].actions) == 1301
    assert ro["video_frames"] == {"front": F.N_RESET_FRAMES + 1301, "wrist": F.N_RESET_FRAMES + 1301}
    fj = json.loads(Path(ro["frames_dir"], "frames.json").read_text())
    assert (fj["demo_frames"], fj["init_frames"], fj["exec_steps"], fj["missing_steps"]) == (2, 1, 1301, [])
    assert Path(ro["frames_dir"], "front.rgb24").stat().st_size == (F.N_RESET_FRAMES + 1301) * F.H * F.W * 3
    d = F.diffs((new, wn, rn), (orig, wo, ro))
    assert d["payload"] == d["exec"] == d["terminal"] == 0, d


def test_strict_cap_stops_before_env_and_reports_timeout(tmp_path):
    """``--strict-cap``（V9 约定）：第 max_steps+1 次 step 不进环境，适配入口收住 StepCapReached、记 timeout。"""
    world = F.World(default=F.Plan())
    side = F.NewSide(F.ORACLE, 30, tmp_path, world, strict_cap=True)
    res = side.run(F.identity())
    assert res["status"] == "timeout" and res["exception"] == "StepCapReached"
    assert res["_session_steps"] == 30 and res["_cap_hit"] is True and len(world.envs[0].actions) == 30
    end = F.read_trace(res["trace_path"])[-1]
    assert end["kind"] == "end" and end["status"] == "timeout" and end["exec_steps"] == 30


@pytest.mark.parametrize("variant", F.VARIANTS)
def test_unknown_is_error_and_does_not_stop_seat(tmp_path, variant):
    """官方 ``unknown`` → status=error、error=success_flag=unknown、非基础设施；同一上下文的下一局照常跑。
    Qwen 临时目录与官方叠字视频局末都不留，Qwen 日志归档到轨迹目录。"""
    world = F.World(plans={3: F.Plan(unknown_at=10), 7: F.Plan(success_at=20)})
    side = F.NewSide(variant, 60, tmp_path, world)
    r1 = side.run(F.identity())
    r2 = side.run(F.identity(source_episode=7, builder_episode=1, seed=510700))
    assert (r1["status"], r1["error"], r1["infra"], r1["steps"]) == ("error", "success_flag=unknown", False, 10)
    assert (r2["status"], r2["steps"]) == ("success", 20)
    for r in (r1, r2):
        tdir = Path(r["trace_path"]).parent
        assert not (tdir / "qwen-tmp").exists() and not (tdir / "official-video").exists()
        logs = sorted(p.name for p in tdir.glob("*_QwenVL_log.jsonl"))
        if variant == F.QWENVL:
            tag = tdir.name
            assert logs == [f"ep{tag}_QwenVL_log.jsonl"] and r["qwen_log"] == str(tdir / logs[0])
            assert all(json.loads(x)["messages"] for x in (tdir / logs[0]).read_text().splitlines())
        else:
            assert logs == [] and r["qwen_log"] is None
    # 原侧：同一分片两行，unknown 不中止
    orig_world = F.World(plans={3: F.Plan(unknown_at=10), 7: F.Plan(success_at=20)})
    orig = F.OrigSide(variant, 60, tmp_path / "orig", orig_world)
    rows = [F.identity(), F.identity(source_episode=7, builder_episode=1, seed=510700)]
    summary = orig.ohr.run_shard(orig.ctx, rows, out=tmp_path / "orig")
    assert summary == {"episodes": 2, "errors": 1, "aborted": False, "success": 1, "fail": 0, "timeout": 0}
    got = [json.loads(x) for x in (tmp_path / "orig" / "results.jsonl").read_text().splitlines()]
    assert [(g["status"], g["error"]) for g in got] == [("error", "success_flag=unknown"), ("success", None)]
    assert all(g["side"] == "orig" and g["policy"] == "mmesg" and g["policy_variant"] == variant
               and g["dataset"] == "test-hard0" for g in got)


def test_trace_location_fallbacks(tmp_path):
    """轨迹位置：trace_dir → recorder.out_dir → 不写（此时临时区用后即删）。"""
    ec = F.env_client()
    world = F.World(default=F.Plan(success_at=5))
    side = F.NewSide(F.ORACLE, 60, tmp_path, world)
    ident = F.identity()

    class Rec(ec.NullRecorder):
        out_dir = tmp_path / "recdir"

    for rec, conn_extra, want in ((Rec(), {"trace_dir": None}, tmp_path / "recdir" / "trace.jsonl"),
                                  (ec.NullRecorder(), {"trace_dir": None}, None)):
        sess = ec.EnvSession(ident["task"], 0, max_steps=60, builder=F.NewSideBuilder(ident["task"], world, {0: 3}),
                             dataset=F.DATASET)
        sess.build()
        conn = {"max_steps": 60, "dataset": F.DATASET, "mme_variant": F.ORACLE, "episode_tag": "x.a1",
                "policy_context": side.ctx, **conn_extra}
        res = side.mc.run_episode(sess, ident, conn, rec)
        sess.close()
        assert res["status"] == "success"
        assert res["trace_path"] == (None if want is None else str(want))
        if want is not None:
            assert F.read_trace(want)[0]["kind"] == "header"
