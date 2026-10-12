"""纯 CPU 的规划、端点绑定与运行失败留证测试，不创建仿真环境。"""

from types import SimpleNamespace
import json
from pathlib import Path
import subprocess
import numpy as np
import pytest
import torch

from robomme_xhard import swap_plan as sp
from robomme_xhard.collision import bin_collision as bc
from robomme_xhard.collision import SwapCollisionError, SceneGenerationError


def state(i, xy):
    p, q = bc.cube_actor_pose(xy, 0, 0.005)
    return bc.ObjectState(str(i), p, q, bc.cube_shape_specs(0.005))


def rectangle():
    return {i: state(i, xy) for i, xy in enumerate([(-.05, -.1), (-.05, .1), (.1, .1), (.1, -.1)])}


def generator(seed=7):
    return torch.Generator().manual_seed(seed)


def test_select_initiator_excludes_last_pair():
    assert sp.select_initiator([0, 0, 5, 7], {0, 1}, generator()) == 2


def test_select_initiator_fallback_when_pool_empty():
    assert sp.select_initiator([4, 1], {0, 1}, generator()) == 1


def test_select_initiator_tie_random_reproducible():
    def draws(seed):
        g = generator(seed)
        return [sp.select_initiator([0]*4, set(), g) for _ in range(20)]
    assert draws(4) == draws(4)
    assert draws(4) != draws(5)


def test_plan_usage_uniform_s11_n4():
    plan = sp.plan_swaps(rectangle(), [], 11, generator())
    assert max(plan.usage) - min(plan.usage) <= 1
    assert all(set(a[:2]).isdisjoint(b[:2]) for a, b in zip(plan.pairs, plan.pairs[1:]))


def test_plan_rectangle_pairs_short_edge():
    assert all(set(p[:2]) in ({0, 3}, {1, 2}) for p in sp.plan_swaps(rectangle(), [], 11, generator()).pairs)


def test_plan_prefix_across_tiers():
    plans = [sp.plan_swaps(rectangle(), [], s, generator()) for s in (4, 5, 7, 9, 11)]
    assert all(p.pairs == plans[-1].pairs[:len(p.pairs)] for p in plans)


def test_usage_counts_split():
    plan = sp.plan_swaps(rectangle(), [], 11, generator())
    assert sum(plan.initiator_usage) == sum(plan.partner_usage) == 11
    assert plan.usage == [a+b for a, b in zip(plan.initiator_usage, plan.partner_usage)]


def test_plan_n3_rotation():
    states = {0: state(0, (-.2, 0)), 1: state(1, (0, 0)), 2: state(2, (.2, 0))}
    plan = sp.plan_swaps(states, [], 9, generator())
    assert all(set(a[:2]) != set(b[:2]) for a, b in zip(plan.pairs, plan.pairs[1:]))


def test_plan_rejects_sweep_collision_raises_scene_error(monkeypatch):
    # 发起者选左端，另一交换对象在左弯道顶点，最近邻仍是右端。
    states = {0: state(0, (-.02, 0)), 1: state(1, (.02, 0)), 2: state(2, (0, .07))}
    monkeypatch.setattr(sp, "select_initiator", lambda *args: 0)
    with pytest.raises(SwapCollisionError) as exc:
        sp.plan_swaps(states, [], 1, generator())
    assert isinstance(exc.value, SceneGenerationError)
    assert exc.value.stage == "sweep"
    assert exc.value.rejection.object_b == "2"


def fake_read(actor, name=None):
    return bc.ObjectState(name or actor.name, actor.p.copy(), actor.q.copy(), actor.shapes)


def test_certify_prefills_all_pairs_and_schedule(monkeypatch):
    actors = list(rectangle().values())
    env = SimpleNamespace(seed=9, swap_times=11, refreshes=0)
    def refresh():
        env.refreshes += 1
    env._refresh_swap_schedule = refresh
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    before = torch.get_rng_state().clone()
    plan = sp.certify_swap_plan(env, actors, [], "bin_")
    assert torch.equal(before, torch.get_rng_state())
    for k, (a, b, _, _) in enumerate(plan.pairs, 1):
        assert getattr(env, f"swap_pair{k}_idx1") is actors[a]
        assert getattr(env, f"swap_pair{k}_idx2") is actors[b]
    assert env.refreshes == 1
    assert env._xhard_runtime_checks == [] and env._xhard_fatal is None
    assert len(env._xhard_swap_plan["pairs"]) == 11
    sp.certify_swap_plan(env, actors, [], "bin_")
    assert env._xhard_swap_plan == plan.as_dict()


def test_certify_rejects_initial_and_too_few(monkeypatch):
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    env = SimpleNamespace(seed=0, swap_times=1)
    with pytest.raises(SceneGenerationError):
        sp.certify_swap_plan(env, [], [], "bin_")
    with pytest.raises(SwapCollisionError) as exc:
        sp.certify_swap_plan(env, [state(0, (0, 0)), state(1, (0, 0))], [], "bin_")
    assert exc.value.stage == "initial"


class Parent:
    def step(self, action):
        self._before_control_step()
        for _ in range(3):
            self._before_simulation_step()
            self._after_simulation_step()
        self.elapsed_steps += 1
        return action
    def _before_control_step(self):
        pass
    def _before_simulation_step(self):
        self.before_called = True
    def _after_simulation_step(self):
        self.after_called = True


class Env(sp.SwapCollisionMixin, Parent):
    def _swap_actors(self):
        return self.actors


def runtime_env(monkeypatch, actors=None):
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    env = Env()
    env.actors = actors or list(rectangle().values())
    for actor in env.actors:
        actor.pose = SimpleNamespace(q=actor.q)
    env.elapsed_steps = 11
    env.swap_pair1_idx1, env.swap_pair1_idx2 = env.actors[0], env.actors[1]
    env.swap_schedule = [(env.actors[0], env.actors[1], 10, 20)]
    env._xhard_swap_plan = {}
    env._xhard_runtime_checks = []
    env._xhard_fatal = None
    env.before_called = False
    env.after_called = False
    return env


def cache_endpoints(env):
    a, b, start, end = env.swap_schedule[0]
    env._two_lane_swaps = {(id(a), id(b), start, end): dict(ax=a.p[0], ay=a.p[1], az=a.p[2], qa=a.q.copy(),
                                                          bx=b.p[0], by=b.p[1], bz=b.p[2], qb=b.q.copy())}


def test_segment_start_binding_mismatch_records_fatal(monkeypatch):
    env = runtime_env(monkeypatch)
    env._check_segment_start(0)
    assert env._xhard_fatal["error_type"] == "SwapBindingError"
    assert env._xhard_fatal["stage"] == "segment_start"
    assert len(env._xhard_fatal["detail"]["distances"]) == 3


def test_segment_start_rejects_third_object_crossing(monkeypatch):
    actors = [state(0, (-.02, 0)), state(1, (.02, 0)), state(2, (0, .07))]
    env = runtime_env(monkeypatch, actors)
    cache_endpoints(env)
    assert bc.check_bin_layout(actors)[1] is None
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "sweep_actual"
    assert env._xhard_fatal["rejection"]["object_b"] == "bin_2"
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True


def test_segment_start_endpoint_evidence_and_mismatch(monkeypatch):
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    cache_endpoints(env)
    env._check_segment_start(0)
    assert env._xhard_fatal is None
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True
    env._two_lane_swaps[next(iter(env._two_lane_swaps))]["ax"] += .001
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "endpoint_binding"


def test_mixin_records_fatal_without_raising(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 10
    assert env.step("结果") == "结果"
    fatal = env._xhard_fatal
    assert fatal["error_type"] == "SwapBindingError"
    env._before_simulation_step()
    env._after_simulation_step()
    assert env.before_called and env.after_called
    assert env._xhard_fatal is fatal
    assert len(env._xhard_runtime_checks) == 1


@pytest.mark.parametrize("stage", ["substep_before", "substep_after"])
def test_substep_failure_never_raises(monkeypatch, stage):
    env = runtime_env(monkeypatch, [state(0, (0, 0)), state(1, (0, 0))])
    getattr(env, "_before_simulation_step" if stage == "substep_before" else "_after_simulation_step")()
    assert env._xhard_fatal["error_type"] == "SwapCollisionError"
    assert env._xhard_fatal["stage"] == stage


def test_runtime_guard_records_unexpected_check_exception(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 10
    def broken(k):
        raise RuntimeError("无法读取端点")
    env._check_segment_start = broken
    assert env.step(3) == 3
    assert env._xhard_fatal["check"] == "uncertified"


def test_segment_start_uses_refreshed_schedule_and_current_step(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 30
    seen = []
    def step(parent_self, action):
        parent_self.swap_schedule = [(env.actors[0], env.actors[1], 30, 40)]
        parent_self.static_flag = True
        return original_step(parent_self, action)
    original_step = Parent.step
    env.static_flag = False
    monkeypatch.setattr(Parent, "step", step)
    env._check_segment_start = lambda k: seen.append((k, env.elapsed_steps))
    env.step(1)
    assert seen == [(0, 30)]


def test_control_hook_once_before_physics_shared_boundary_and_no_state(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 10
    env.swap_schedule = [(env.actors[0], env.actors[1], 10, 11),
                         (env.actors[1], env.actors[0], 11, 12)]
    events = []
    env._check_segment_start = lambda k: events.append(("start", k, env.elapsed_steps))
    env._substep_check = lambda stage: events.append((stage, env.elapsed_steps))
    monkeypatch.setattr(Parent, "_before_control_step", lambda self: events.append(("parent", self.elapsed_steps)))
    keys = set(vars(env))
    env.step(None)
    env.step(None)
    assert [r for r in events if r[0] == "start"] == [("start", 0, 10), ("start", 1, 11)]
    assert events[:3] == [("parent", 10), ("start", 0, 10), ("substep_before", 10)]
    assert events[8:11] == [("parent", 11), ("start", 1, 11), ("substep_before", 11)]
    assert set(vars(env)) - keys == set()
    assert "step" not in sp.SwapCollisionMixin.__dict__
    assert "reset" not in sp.SwapCollisionMixin.__dict__
    assert "_initialize_episode" not in sp.SwapCollisionMixin.__dict__


def test_small_quaternion_difference_rejected_and_step_evidence(monkeypatch, tmp_path):
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    env.elapsed_steps = 10
    cache_endpoints(env)
    env.actors[0].q[1] += 1e-12
    env.step(None)
    assert env._xhard_fatal["check"] == "endpoint_binding"
    assert env._xhard_fatal["control_step"] == 10
    assert all(r["control_step"] == 10 and r["phase"] == "before_physics" for r in env._xhard_runtime_checks)
    assert "a_q" in env._xhard_runtime_checks[-1]["endpoints"]["mismatches"]
    path = tmp_path / "tiny-q.json"
    evidence = dict(env._xhard_runtime_checks[-1], git_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[3], text=True).strip())
    path.write_text(json.dumps(evidence), encoding="utf-8")
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored["git_commit"] == evidence["git_commit"] and len(restored["git_commit"]) == 40
    endpoints = restored["endpoints"]
    assert endpoints == env._xhard_runtime_checks[-1]["endpoints"]
    assert endpoints["actual_raw_q"]["a"] != endpoints["cached_raw_q"]["a"]
    assert endpoints["delta"]["a_q"][1] != 0
    assert set(endpoints["delta"]) == {"a_p", "a_q", "b_p", "b_q"}


def test_real_check_before_integrating_pose_and_shared_cache(monkeypatch):
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    env.elapsed_steps = 10
    a, b = env.actors
    env.swap_schedule = [(a, b, 10, 11), (b, a, 11, 12)]
    env.swap_pair2_idx1, env.swap_pair2_idx2 = b, a
    events = []
    original_step = Parent.step
    def refresh_and_step(self, action):
        # 模拟父类先落定上一段，再捕获新段端点并应用 alpha=0。
        if self.elapsed_steps == 11:
            a.p[:2], b.p[:2] = b.p[:2].copy(), a.p[:2].copy()
            a.q[1] = b.q[1] = 0
            events.append("落定上一段")
        first, second, start, end = self.swap_schedule[self.elapsed_steps - 10]
        self._two_lane_swaps[(id(first), id(second), start, end)] = dict(
            ax=first.p[0], ay=first.p[1], az=first.p[2], qa=first.q.copy(),
            bx=second.p[0], by=second.p[1], bz=second.p[2], qb=second.q.copy())
        events.append("捕获本段")
        return original_step(self, action)
    def integrate(self):
        # 第一个物理子步修改位姿，若段起点检查后移就会逐位失败。
        a.p[2] += 1e-5
        a.q[1] += 1e-12
        events.append("物理积分")
    env._two_lane_swaps = {}
    monkeypatch.setattr(Parent, "step", refresh_and_step)
    monkeypatch.setattr(Parent, "_after_simulation_step", integrate)
    monkeypatch.setattr(env, "_substep_check", lambda stage: None)
    keys = set(vars(env))
    env.step(None)
    assert env._xhard_fatal is None
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True
    # 同一份真实检查在积分后必拒，证明它不能移到 step 返回后。
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "endpoint_binding"
    env._xhard_fatal = None
    env._xhard_runtime_checks = env._xhard_runtime_checks[:2]
    env.step(None)
    assert env._xhard_fatal is None
    sweeps = [r for r in env._xhard_runtime_checks if r["kind"] == "swap_sweep"]
    assert [(r["sweep_index"], r["control_step"]) for r in sweeps] == [(0, 10), (1, 11)]
    assert all(r["endpoint_match"] and r["phase"] == "before_physics" for r in sweeps)
    assert events[:2] == ["捕获本段", "物理积分"]
    assert events[4:6] == ["落定上一段", "捕获本段"]
    assert set(vars(env)) == keys


def test_outside_window_does_not_read_geometry(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 1
    env._states = lambda: pytest.fail("交换窗外不应读取几何")
    env._before_simulation_step()
    env._after_simulation_step()
    assert env._xhard_runtime_checks == []


def test_repick_placeholder_does_not_enter_window(monkeypatch):
    env = runtime_env(monkeypatch)
    env.static_flag = False
    env.elapsed_steps = 400
    env.swap_schedule = [(env.actors[0], env.actors[1], 400, 450)]
    env._states = lambda: pytest.fail("演示结束前不应读取交换几何")
    env._before_simulation_step()
    assert env._swap_segment_index_at(400) is None
    assert env._xhard_runtime_checks == []


@pytest.mark.parametrize("method", ["step", "_before_control_step", "_before_simulation_step", "_after_simulation_step"])
def test_parent_exception_is_not_swallowed(monkeypatch, method):
    env = runtime_env(monkeypatch)
    def broken(*args):
        raise ValueError("父类自身错误")
    env.elapsed_steps = 1
    monkeypatch.setattr(Parent, method, broken)
    with pytest.raises(ValueError, match="父类自身错误"):
        env.step(1)
    assert env._xhard_fatal is None


# ── 方案 X′：段起点期望四元数重放父类 float32 归一化 ─────────────────────────────
class PoseActor:
    """只提供父类 swap_flat_two_lane 用到的 pose 读取与 set_pose，记录真实写入。"""

    def __init__(self, name, p, q, shapes):
        self.name, self.shapes = name, shapes
        self.p = np.asarray(p, dtype=np.float32)
        self.q = np.asarray(q, dtype=np.float32)
        self.written = []

    @property
    def pose(self):
        return SimpleNamespace(p=self.p.copy(), q=self.q.copy())

    def set_pose(self, pose):
        self.written.append(np.asarray(pose.q, np.float32))
        self.p = np.asarray(pose.p, dtype=np.float32)
        self.q = np.asarray(pose.q, dtype=np.float32)


# 非平凡偏航四元数，float32 范数恰为 1；[1,0,0,0] 加一个刻度在 float64 正规化后会被抹平，区分不出。
QA_UNIT = np.array([0.989905059337616, 0.0, 0.0, 0.14173220098018646], dtype=np.float32)
QB_YAW = np.array([np.cos(0.3), 0, 0, np.sin(0.3)], dtype=np.float32)


def parent_q_cases():
    """范数恰为 1、首分量多一个 float32 刻度、少一个刻度三组缓存 qa。"""
    assert np.linalg.norm(QA_UNIT) == np.float32(1)
    up = QA_UNIT.copy()
    up[0] = np.nextafter(up[0], np.float32(2))
    down = QA_UNIT.copy()
    down[0] = np.nextafter(down[0], np.float32(0))
    return {"unit": QA_UNIT.copy(), "up": up, "down": down}


def run_parent_start(qa, qb, env=None):
    """在 cur_step == start_step < end_step 下调用真实父类函数一次。"""
    from robomme.robomme_env.utils.statechange import swap_flat_two_lane
    shapes = bc.cube_shape_specs(0.005)
    a = PoseActor("bin_0", [-.05, 0, .005], qa, shapes)
    b = PoseActor("bin_1", [.05, 0, .005], qb, shapes)
    env = env if env is not None else SimpleNamespace()
    swap_flat_two_lane(env, a, b, start_step=10, end_step=20, cur_step=10)
    return env, a, b


@pytest.mark.parametrize("case", ["unit", "up", "down"])
def test_parent_start_q_matches_real_parent_write(case):
    qa = parent_q_cases()[case]
    env, a, b = run_parent_start(qa, QB_YAW)
    cache = env._two_lane_swaps[(id(a), id(b), 10, 20)]
    assert cache["qa"].dtype == np.float32
    assert len(a.written) == len(b.written) == 1
    assert np.array_equal(sp.parent_start_q(cache["qa"], cache["qb"]), a.written[0])
    assert np.array_equal(sp.parent_start_q(cache["qb"], cache["qa"]), b.written[0])
    assert sp.parent_start_q(cache["qa"], cache["qb"]).dtype == np.float32


def test_parent_start_q_distinguishes_one_ulp_from_cache():
    qa = parent_q_cases()["up"]
    env, a, b = run_parent_start(qa, QB_YAW)
    cache = env._two_lane_swaps[(id(a), id(b), 10, 20)]
    assert not np.array_equal(sp.parent_start_q(cache["qa"], cache["qb"]), cache["qa"])
    # 判据 float64 正规化后，旧期望（缓存原值）同样与真实写入不同，即方案 X 的误报来源。
    assert not np.array_equal(bc.ObjectState("a", [0, 0, 0], cache["qa"], ()).q,
                              bc.ObjectState("a", [0, 0, 0], a.written[0], ()).q)


def parent_runtime_env(monkeypatch):
    """端到端：父类在 env 上真实捕获缓存并写入段起点，再交给 mixin 比较。"""
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    env.elapsed_steps = 10
    _, a, b = run_parent_start(parent_q_cases()["up"], QB_YAW, env)
    env.actors = [a, b]
    env.swap_pair1_idx1, env.swap_pair1_idx2 = a, b
    env.swap_schedule = [(a, b, 10, 20)]
    return env, a, b


def test_endpoint_evidence_accepts_parent_replay(monkeypatch):
    env, a, b = parent_runtime_env(monkeypatch)
    actual = [bc.object_state_from_actor(x, f"bin_{i}") for i, x in enumerate((a, b))]
    match, evidence = env._endpoint_evidence(0, *actual)
    assert match is True and evidence["mismatches"] == []
    assert evidence["expected_start_raw_q"]["a"] == a.written[0].tolist()
    assert evidence["expected_start_raw_q"]["b"] == b.written[0].tolist()
    assert evidence["cached_raw_q"]["a"] != evidence["expected_start_raw_q"]["a"]
    assert {"actual", "cached", "mismatches", "delta", "actual_raw_q", "cached_raw_q",
            "phase", "expected_start_raw_q"} <= set(evidence)
    env._check_segment_start(0)
    assert env._xhard_fatal is None
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True


@pytest.mark.parametrize("kind", ["position", "extra_ulp"])
def test_endpoint_evidence_rejects_real_difference_after_replay(monkeypatch, kind):
    env, a, b = parent_runtime_env(monkeypatch)
    if kind == "position":
        a.p = a.p.astype(np.float64)
        a.p[2] += 1e-6
        key = "a_p"
    else:
        # 归一化解释不了的额外一个 float32 刻度。
        a.q = a.q.copy()
        a.q[3] = np.nextafter(a.q[3], np.float32(1))
        key = "a_q"
    actual = [bc.object_state_from_actor(x, f"bin_{i}") for i, x in enumerate((a, b))]
    match, evidence = env._endpoint_evidence(0, *actual)
    assert match is False and evidence["mismatches"] == [key]
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "endpoint_binding"


def test_parent_start_q_verdict_line(capsys):
    """三组锁定用例汇总成判定行。"""
    passed = 0
    for qa in parent_q_cases().values():
        env, a, b = run_parent_start(qa, QB_YAW)
        cache = env._two_lane_swaps[(id(a), id(b), 10, 20)]
        passed += int(np.array_equal(sp.parent_start_q(cache["qa"], cache["qb"]), a.written[0]) and
                      np.array_equal(sp.parent_start_q(cache["qb"], cache["qa"]), b.written[0]))
    assert passed == 3
    with capsys.disabled():
        print(f"\nXHARD_PARENT_START_Q=PASS cases={passed}")
