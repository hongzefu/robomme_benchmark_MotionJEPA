"""C13 两个策略客户端（``mme_client``、``smvla_client``）的协议与动作转换，以及席位层「普通失败不重试、唯一接受、
必填身份」。

假 server 只记录收到的消息并按输入确定性地回动作；期望（帧序列、exec_start_idx、执行的动作行、步数）都由本文件
手写的假环境推出，不调用被测函数生成。
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import eval_fakes as F


# ---------------------------------------------------------------- MME：逐行照抄旧官方的循环语义


class _Session:
    """最小会话：reset 返回假环境 reset 观测；step 交给假环境。"""

    def __init__(self, plan, ep=2):
        self.env = F.FakeEnv("T", ep, plan)
        self.steps = 0

    def reset(self):
        return self.env.reset()

    def step(self, a):
        self.steps += 1
        return self.env.step(a)


def _mme_run(plan, *, max_steps=None, server=None, client_factory=None):
    mc = F.mme_client()
    server = server or F.FakePolicyServer()
    sess = _Session(plan)
    kw = {} if max_steps is None else {"max_steps": max_steps}
    res = mc.evaluate_one(client_factory or (lambda: F.FakeMMEClient(server)), sess.step,
                          lambda: mc.pre_traj_from_reset(*sess.reset()), **kw)
    return res, sess, server


def test_pack_state_is_joint7_plus_first_gripper_float32():
    mc = F.mme_client()
    s = mc.pack_state(np.arange(7, dtype=np.float64), np.array([0.25, 0.75]))
    assert s.dtype == np.float32 and s.tolist() == [0, 1, 2, 3, 4, 5, 6, 0.25]


def test_mme_first_inference_sends_all_reset_frames_then_only_new_frames():
    mc = F.mme_client()
    res, sess, server = _mme_run(F.Plan(success_at=20))
    assert res["status"] == "success" and res["steps"] == 20 and res["infra"] is False
    obs_msgs = [p for k, p in server.log if k == "observe"]
    infer_msgs = [p for k, p in server.log if k == "infer"]
    # 第一次决策：reset 的全部帧（演示 + 初始），exec_start_idx 指向初始帧
    reset_shas = [F.sha_bytes(F.frame(v)) for v in F.reset_values(2)]
    assert obs_msgs[0]["frames"] == reset_shas and obs_msgs[0]["exec_start_idx"] == F.N_RESET_FRAMES - 1
    assert obs_msgs[0]["shape"] == [F.N_RESET_FRAMES, 1, F.HW, F.HW, 3]
    assert infer_msgs[0]["prompt"] == "goal-T-2"  # 取 task_goal 的第一条
    assert infer_msgs[0]["image"] == reset_shas[-1]
    assert np.array_equal(infer_msgs[0]["state"], mc.pack_state(np.full(7, F.reset_values(2)[-1] / 10.0),
                                                                np.full(2, F.reset_values(2)[-1] / 100.0)))
    # 第二次决策：只带执行段新出现的帧，exec_start_idx 归零
    h = mc.OBS_HORIZON
    assert len(obs_msgs[1]["frames"]) == h and obs_msgs[1]["exec_start_idx"] == 0
    assert obs_msgs[1]["frames"][0] == F.sha_bytes(F.frame(100 + (2 * 3 + 1) % 100))
    # 每次推理回 CHUNK_ROWS 行，只执行前 OBS_HORIZON 行
    assert F.CHUNK_ROWS > h and res["decisions"] == 2
    executed = np.stack(sess.env.actions)
    assert executed.shape == (20, 8)
    assert np.array_equal(executed[:h], infer_msgs[0]["actions"][:h])
    assert np.array_equal(executed[h:], infer_msgs[1]["actions"][:20 - h])


def test_mme_timeout_counts_to_max_plus_one():
    """count > max_steps 即 timeout，步数记 max_steps+1（该判断先于终态判断）。"""
    res, sess, _ = _mme_run(F.Plan(), max_steps=5)
    assert res["status"] == "timeout" and res["steps"] == 6 and sess.env.n == 6


def test_mme_env_exception_becomes_error_without_infra():
    res, sess, _ = _mme_run(F.Plan(raise_at=3, raise_exc=lambda: RuntimeError("IK 失败")))
    assert res["status"] == "error" and res["infra"] is False
    assert res["env_exception"] == "RuntimeError: IK 失败" and res["steps"] == 3


@pytest.mark.parametrize("message", ["svulkan2 boom", "CUDA_ERROR_LAUNCH_FAILED", "out of memory"])
def test_mme_infra_marker_sets_infra(message):
    res, _, _ = _mme_run(F.Plan(raise_at=1, raise_exc=lambda: RuntimeError(message)))
    assert res["status"] == "error" and res["infra"] is True


def test_mme_unknown_terminal_status_is_error():
    class _Weird(F.FakeEnv):
        def step(self, a):
            obs, r, _, tr, _ = super().step(a)
            return obs, r, True, tr, {"status": "ongoing"}

    mc = F.mme_client()
    env = _Weird("T", 2, F.Plan())
    res = mc.evaluate_one(lambda: F.FakeMMEClient(F.FakePolicyServer()), env.step,
                          lambda: mc.pre_traj_from_reset(*env.reset()))
    assert res["status"] == "error" and res["error"] == "success_flag=ongoing"


def test_mme_connection_refused_is_infra():
    def factory():
        raise ConnectionRefusedError("拒绝连接")

    res, sess, _ = _mme_run(F.Plan(success_at=1), client_factory=factory)
    assert res["status"] == "error" and res["infra"] is True and sess.env.n == 0


# ---------------------------------------------------------------- SMVLA：SimEnvService 的打包语义


def test_step_chunk_converts_rows_to_float64_first8_and_stops_on_done():
    sm = F.smvla_client()
    sess = _Session(F.Plan(success_at=2))
    sess.reset()
    chunk = np.arange(40, dtype=np.float32).reshape(4, 10)
    out = sm.step_chunk(sess, chunk)
    assert out["consumed"] == 2 and out["done"] is True and out["success"] is True
    assert [a.dtype for a in sess.env.actions] == [np.float64] * 2
    assert [a.tolist() for a in sess.env.actions] == [list(range(0, 8)), list(range(10, 18))]
    assert len(out["frames"]) == 2 and out["states"][0].dtype == np.float32


def test_step_chunk_rejects_short_action():
    sm = F.smvla_client()
    sess = _Session(F.Plan())
    sess.reset()
    with pytest.raises(ValueError):
        sm.step_chunk(sess, np.zeros((2, 7)))
    assert sess.env.n == 0


def _smvla_run(plan, **kw):
    sm = F.smvla_client()
    server = F.FakePolicyServer(fail_on=kw.pop("fail_on", None))
    conn = F.FakeSmvlaConn(server, tamper=kw.pop("tamper", None))
    sess = _Session(plan)
    res = sm.run_episode(sess, {"task": "T", "source_episode": None, "seed": 1}, {}, None, conn=conn, **kw)
    return res, sess, server


def test_smvla_first_inference_and_messages():
    res, sess, server = _smvla_run(F.Plan(success_at=3))
    assert res["status"] == "success" and res["steps"] == 3 and res["decisions"] == 1
    assert server.kinds()[:3] == ["reset", "observe", "infer"]
    assert server.log[0][1] == "T/None/1"
    reset_shas = [F.sha_bytes(F.frame(v)) for v in F.reset_values(2)]
    assert server.log[1][1]["frames"] == reset_shas
    inf = server.log[2][1]
    assert inf["prompt"] == "goal-T-2" and inf["state"].dtype == np.float32
    v = F.reset_values(2)[-1]
    assert inf["state"].tolist() == pytest.approx([v / 10.0] * 7 + [v / 100.0])
    assert res["protocol"]["sha_mismatch"] == 0 and res["protocol"]["frames_sent"] == F.N_RESET_FRAMES + 3


def test_smvla_decision_budget_hand_computed():
    """max_steps=32、执行段 16：决策上限 32/16+2 = 4 次（手算），永不终止的环境走满 4×16 = 64 步后记 timeout。"""
    res, sess, _ = _smvla_run(F.Plan(), max_steps=32, execute_horizon=16)
    assert res["hard_bound"] == 4 and res["decisions"] == 4
    assert res["status"] == "timeout" and res["steps"] == 64 and sess.env.n == 64
    assert "hard_bound=4" in res["error"]


@pytest.mark.parametrize("fail_on,tamper,reason", [("server_error", None, "server_error"),
                                                    (None, "req_sha", "protocol"),
                                                    (None, "frame_sha", "protocol"),
                                                    ("infer_disconnect", None, "connection:ConnectionClosed")])
def test_smvla_server_side_failures_are_infra(fail_on, tamper, reason):
    res, sess, _ = _smvla_run(F.Plan(success_at=3), fail_on=fail_on, tamper=tamper)
    assert res["status"] == "error" and res["infra"] is True and res["infra_reason"] == reason
    assert sess.env.n == 0


def test_smvla_step_exception_without_marker_is_final_error():
    res, sess, _ = _smvla_run(F.Plan(raise_at=2, raise_exc=lambda: RuntimeError("IK 失败")))
    assert res["status"] == "error" and res["infra"] is False and res["error"].startswith("step_exc: ")


def test_smvla_reset_failure_with_vulkan_marker_is_infra_and_retries_count():
    class _Bad(_Session):
        def __init__(self):
            super().__init__(F.Plan())
            self.n_reset = 0
            self.closed = 0

        def reset(self):
            self.n_reset += 1
            raise RuntimeError("vk::DeviceLost")

        def close(self):
            self.closed += 1

    sm = F.smvla_client()
    sess = _Bad()
    res = sm.run_episode(sess, {"task": "T", "source_episode": 0, "seed": 1}, {}, None,
                         conn=F.FakeSmvlaConn(F.FakePolicyServer()), reset_retries=2)
    assert sess.n_reset == 3 and sess.closed == 3  # 2 次重试 = 共 3 次
    assert res["status"] == "error" and res["infra"] is True and res["infra_reason"] == "env_reset:vk::"


# ---------------------------------------------------------------- 席位层：普通失败不重试、必填身份


@pytest.mark.parametrize("plan", [F.Plan(fail_at=1), F.Plan(raise_at=1, raise_exc=lambda: RuntimeError("IK"))],
                         ids=["fail", "ordinary_error"])
@pytest.mark.parametrize("policy", ("mme", "smvla"))
def test_ordinary_failure_is_not_retried(tmp_path, monkeypatch, policy, plan):
    task, tier = F.v9_cells_sorted()[0]
    ident = F.packaged_identity(task, tier, 0)
    world = F.World({(task, ident["builder_episode"]): [plan]})
    runner = F.make_runner(tmp_path, policy, F.policy_module(policy, monkeypatch, F.FakePolicyServer()), world)
    assert F.run_rows(runner, [ident]) == 0
    assert len(world.envs) == 1
    ledger = F.read_jsonl(tmp_path / "s00" / policy / f"{policy}.ledger.jsonl")
    assert [x["kind"] for x in ledger].count("attempt_start") == 1
    assert [x["kind"] for x in ledger].count("accept") == 1


def _args_for_identities(tmp_path, rows):
    p = tmp_path / "shard-00.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return F.seat_args(tmp_path / "out", "mme", ledger=tmp_path / "l.jsonl", identities=str(p))


@pytest.mark.parametrize("mutate", ["drop_spec", "dup_key", "float_seed"])
def test_load_identities_blocks_on_bad_rows(tmp_path, capsys, mutate):
    ec = F.env_client()
    task, tier = F.v9_cells_sorted()[0]
    a, b = F.packaged_identity(task, tier, 0), F.packaged_identity(task, tier, 1)
    rows = [a, b]
    if mutate == "drop_spec":
        rows = [a, {k: v for k, v in b.items() if k != "spec_sha256"}]
    elif mutate == "dup_key":
        rows = [a, dict(a)]
    else:
        rows = [a, dict(b, seed=float(b["seed"]))]
    with pytest.raises(SystemExit) as ei:
        ec.load_identities(_args_for_identities(tmp_path, rows))
    assert ei.value.code == ec.EXIT_BLOCKED
    assert "RUN_BLOCKED reason=identities" in capsys.readouterr().out


def test_load_identities_accepts_clean_rows_and_only_filter(tmp_path):
    ec = F.env_client()
    task, tier = F.v9_cells_sorted()[0]
    a, b = F.packaged_identity(task, tier, 0), F.packaged_identity(task, tier, 1)
    args = _args_for_identities(tmp_path, [a, b])
    assert [r["key"] for r in ec.load_identities(args)] == [a["key"], b["key"]]
    args.only = b["key"]
    assert [r["key"] for r in ec.load_identities(args)] == [b["key"]]


_BASE = ["run", "--identities", "x.json", "--cond", "c", "--seat", "s", "--port", "1", "--out", "o"]
_LEDGER = ["--ledger", "l.jsonl", "--reset-budget", "10", "--infra-retry-budget", "1"]


@pytest.mark.parametrize("drop", ["--dataset", "--max-steps"])
def test_dataset_and_max_steps_have_no_default(drop):
    """--dataset 与 --max-steps 都必填、无默认值：缺任一即参数错误（argparse 退出 2）。"""
    ec = F.env_client()
    argv = _BASE + ["--policy", "mme", "--dataset", "test-hard0", "--max-steps", "1300"] + _LEDGER
    i = argv.index(drop)
    with pytest.raises(SystemExit) as ei:
        ec.build_parser().parse_args(argv[:i] + argv[i + 2:])
    assert ei.value.code == 2


@pytest.mark.parametrize("extra,why", [
    (["--policy", "mme", "--dataset", "test-hard", "--max-steps", "1600"], "必须给 --ledger"),
    (["--policy", "mmesg", "--dataset", "test-hard0", "--max-steps", "1300", *_LEDGER], "--mme-variant"),
    (["--policy", "mmesg", "--dataset", "test-hard0", "--max-steps", "1300", "--mme-variant", "ground-sg-qwenvl",
      *_LEDGER], "--qwenvl-groundsg-adapter"),
    (["--policy", "mme", "--dataset", "test-hard0", "--max-steps", "1300", "--mme-variant", "ground-sg-oracle",
      *_LEDGER], "只能与 --policy mmesg"),
    (["--policy", "mmesg", "--dataset", "test-hard0", "--max-steps", "1300", "--mme-variant", "ground-sg-oracle",
      "--qwenvl-groundsg-adapter", "a", *_LEDGER], "只能与 --mme-variant ground-sg-qwenvl"),
    (["--policy", "pp", "--dataset", "test-hard0", "--max-steps", "0", *_LEDGER], "--max-steps 必须是正整数"),
], ids=["no_ledger", "mmesg_no_variant", "qwenvl_no_adapter", "variant_on_mme", "adapter_on_oracle", "zero_steps"])
def test_run_args_blocked(capsys, extra, why):
    ec = F.env_client()
    args = ec.build_parser().parse_args(_BASE + extra)
    assert ec.cmd_run(args) == 3
    out = capsys.readouterr().out
    assert "RUN_BLOCKED reason=args" in out and why in out


def test_run_args_accept_all_four_policies():
    ec = F.env_client()
    for pol, extra in (("mme", []), ("smvla", []), ("pp", []),
                       ("mmesg", ["--mme-variant", "ground-sg-oracle"]),
                       ("mmesg", ["--mme-variant", "ground-sg-qwenvl", "--qwenvl-groundsg-adapter", "/x"])):
        args = ec.build_parser().parse_args(_BASE + ["--policy", pol, "--dataset", "test-hard0", "--max-steps",
                                                     "1300", *_LEDGER, *extra])
        assert ec.check_run_args(args, need_identities=True) is None, pol
        assert args.strict_cap is False
